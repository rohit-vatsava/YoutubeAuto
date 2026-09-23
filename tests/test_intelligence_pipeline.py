import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from datetime import timedelta
from tech_uncovered.cli import main
from tech_uncovered.database import Database
from tech_uncovered.intelligence.pipeline import run_intelligence
from tech_uncovered.intelligence.providers import LocalTranscriptProvider,ManualResearchProvider
from tech_uncovered.intelligence.reports import export,markdown,expire_reports
from tech_uncovered.intelligence.storage import expire
from tests.intelligence_helpers import config,seed,load,NOW,FIXTURES


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name)
        self.db=Database(self.path/'test.db');seed(self.db)
    def tearDown(self):
        self.db.close();self.temp.cleanup()

    def run_it(self,**kwargs):
        options=dict(radar_run_id='radar-intelligence-fiction-v1',top=9,offline=True,
                     transcript_provider=LocalTranscriptProvider(load('context.json')['videos']),
                     research_provider=ManualResearchProvider(load('evidence.json')))
        options.update(kwargs)
        return run_intelligence(self.db,config(),NOW,**options)

    def test_end_to_end_counts_provenance_and_components(self):
        result=self.run_it()
        self.assertEqual(result['metadata']['status'],'complete')
        self.assertEqual(len(result['trend_clusters']),3)
        self.assertEqual(len(result['ideas']),36)
        self.assertEqual(sum(i['duplicate_of'] is not None for i in result['ideas']),24)
        self.assertFalse(any(i['production_ready'] for i in result['ideas']))
        run=result['intelligence_run_id']
        self.assertEqual(self.db.connection.execute('SELECT count(*) FROM story_briefs WHERE intelligence_run_id=?',(run,)).fetchone()[0],9)
        stored=dict(self.db.connection.execute('SELECT * FROM idea_scores WHERE intelligence_run_id=? LIMIT 1',(run,)).fetchone())
        self.assertIn('evidence_quality',stored)
        self.assertIn('saturation_risk',stored)
        self.assertEqual(result['ideas'][0]['radar_run_id'],result['radar_run_id'])
        self.assertTrue(result['ideas'][0]['story_context'])
        self.assertTrue(result['ideas'][0]['provider_versions'])

    def test_history_not_overwritten_deterministic_order(self):
        a=self.run_it();b=self.run_it(refresh=True)
        self.assertNotEqual(a['intelligence_run_id'],b['intelligence_run_id'])
        self.assertEqual([(i['idea_id'],i['idea_score'],i['category']) for i in a['ideas']],
                         [(i['idea_id'],i['idea_score'],i['category']) for i in b['ideas']])
        self.assertEqual(self.db.connection.execute('SELECT count(*) FROM intelligence_runs').fetchone()[0],2)
        export(a,self.path/'reports');export(b,self.path/'reports')
        self.assertTrue((self.path/'reports/runs'/a['intelligence_run_id']/'ideas.json').exists())
        with self.assertRaises(ValueError):export(a,self.path/'reports')

    def test_bad_video_provider_does_not_abort(self):
        class Broken(LocalTranscriptProvider):
            def retrieve(self,candidate,**kwargs):
                if candidate['video_id']=='fiction-0-10':raise ValueError('secret provider details')
                return super().retrieve(candidate,**kwargs)
        result=self.run_it(transcript_provider=Broken(load('context.json')['videos']))
        self.assertEqual(result['metadata']['status'],'partial')
        self.assertEqual(len(result['story_briefs']),9)
        self.assertEqual(result['transcripts']['fiction-0-10']['transcript_status'],'ERROR')
        self.assertNotIn('secret provider details',str(result['metadata']['partial_failures']))
        self.assertTrue(result['ideas'])

    def test_invalid_structured_context_falls_back(self):
        entries=load('context.json')['videos'];entries['fiction-0-10']['context']['claims']='invalid'
        result=self.run_it(transcript_provider=LocalTranscriptProvider(entries))
        self.assertEqual(result['metadata']['status'],'partial')
        brief=next(b for b in result['story_briefs'] if b['video_id']=='fiction-0-10')
        self.assertIn('CONTEXT_LIMITED',brief['flags'])

    def test_research_failure_keeps_unverified_ideas(self):
        class Broken:
            name='broken';version='1'
            def research(self,*args,**kwargs):raise RuntimeError('No research')
        result=self.run_it(research_provider=Broken())
        self.assertEqual(len(result['metadata']['partial_failures']),9)
        self.assertTrue(all(i['scores']['EvidenceQuality']==0 for i in result['ideas']))
        self.assertTrue(all(not i['production_ready'] for i in result['ideas']))

    def test_metadata_only_never_ready(self):
        result=self.run_it(transcript_provider=None,research_provider=None)
        self.assertTrue(all('CONTEXT_LIMITED' in b['flags'] for b in result['story_briefs']))
        self.assertTrue(all(not i['production_ready'] for i in result['ideas']))
        self.assertFalse(any(i['category']=='READY FOR SCRIPTING' for i in result['ideas']))

    def test_report_sections(self):
        output=markdown(self.run_it())
        for section in ['RECOMMENDED FOR RESEARCH','READY FOR SCRIPTING','BACKLOG','REJECTED / REVIEW REQUIRED','Source evidence','Strongest trend clusters']:
            self.assertIn(section,output)
        self.assertIn('FICTIONAL FIXTURE',output)
        self.assertIn('Production ready: **false**',output)

    def test_offline_cli_without_network(self):
        with patch('socket.socket',side_effect=AssertionError('Network prohibited')),contextlib.redirect_stdout(io.StringIO()) as output:
            code=main(['intelligence','--offline','--fixture',str(FIXTURES/'radar.json'),
                       '--context-file',str(FIXTURES/'context.json'),'--evidence-file',str(FIXTURES/'evidence.json'),
                       '--db',str(self.path/'cli.db'),'--reports-dir',str(self.path/'reports'),'--top','9'])
        self.assertEqual(code,0)
        self.assertIn('Candidates analyzed: 9',output.getvalue())
        self.assertEqual(len(list((self.path/'reports').glob('*.json'))),3)

    def test_retention_keeps_receipt_expires_payloads(self):
        result=self.run_it();run=result['intelligence_run_id']
        # Simulate a non-synthetic run for retention; fixture data is ordinarily exempt.
        self.db.connection.execute("UPDATE intelligence_runs SET mode='offline' WHERE intelligence_run_id=?",(run,))
        self.db.connection.commit()
        export(result,self.path/'reports')
        ids=expire(self.db,NOW+timedelta(days=31))
        self.assertEqual(ids,[run])
        self.assertEqual(self.db.connection.execute('SELECT count(*) FROM idea_candidates').fetchone()[0],0)
        self.assertEqual(self.db.connection.execute('SELECT expired FROM intelligence_runs').fetchone()[0],1)
        expire_reports(self.path/'reports',ids)
        self.assertFalse((self.path/'reports/ideas.json').exists())
        self.assertFalse((self.path/'reports/runs'/run).exists())

    def test_replacement_generator_with_resolved_research_can_be_ready(self):
        from tech_uncovered.intelligence.generation import DeterministicIdeaGenerator
        class ReviewedGenerator(DeterministicIdeaGenerator):
            name='reviewed-fixture-generator'
            def generate(self,brief,cluster):
                rows=super().generate(brief,cluster)
                for row in rows:row.required_research=[]
                return rows
        result=self.run_it(generator=ReviewedGenerator())
        ready=[i for i in result['ideas'] if i['production_ready']]
        self.assertTrue(ready)
        self.assertTrue(all(i['similarity_status']=='CLEAR' and i['scores']['EvidenceQuality']>=60 and not i['required_research'] for i in ready))
        self.assertTrue(all(i['category']=='READY FOR SCRIPTING' for i in ready))
        self.assertFalse(any(i['production_ready'] for i in result['ideas'] if i['scores']['EvidenceQuality']<60))

    def test_expired_run_not_silently_replaced(self):
        fixture=load('radar.json');fixture['run_id']='expired-live';fixture['metadata']['mode']='live'
        self.db.save_run(fixture)
        with self.assertRaisesRegex(ValueError,'expired'):
            run_intelligence(self.db,config(),NOW+timedelta(days=31),radar_run_id='expired-live',offline=True)

    def test_empty_candidate_pool_is_valid_report(self):
        fixture=load('radar.json');fixture['run_id']='empty';fixture['videos']=[];fixture['baselines']=[];fixture['topics']=[]
        self.db.save_run(fixture)
        result=self.run_it(radar_run_id='empty')
        self.assertEqual(result['ideas'],[])
        self.assertEqual(result['metadata']['status'],'complete')
        self.assertIn('None.',markdown(result))

    def test_partial_cli_returns_two(self):
        bad=load('context.json');bad['videos']['fiction-0-10']['context']['claims']='bad'
        path=self.path/'bad-context.json';path.write_text(json.dumps(bad))
        with contextlib.redirect_stdout(io.StringIO()):
            code=main(['intelligence','--offline','--fixture',str(FIXTURES/'radar.json'),
                       '--context-file',str(path),'--db',str(self.path/'partial.db'),
                       '--reports-dir',str(self.path/'partial'),'--top','9'])
        self.assertEqual(code,2)
        self.assertTrue((self.path/'partial/intelligence.md').exists())

    def test_invalid_weights_fail_before_persisting(self):
        cfg=config();cfg['weights']['EvidenceQuality']=-1
        with self.assertRaises(ValueError):
            run_intelligence(self.db,cfg,NOW,radar_run_id='radar-intelligence-fiction-v1')
        self.assertEqual(self.db.connection.execute('SELECT count(*) FROM intelligence_runs').fetchone()[0],0)
