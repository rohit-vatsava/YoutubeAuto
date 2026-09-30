import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch,Mock

from tech_uncovered.database import Database
from tech_uncovered.scripting.editorial_revision import create,load,review
from tech_uncovered.scripting.reports import export
from tech_uncovered.scripting.costs import Budget
from tech_uncovered.scripting.providers.fixtures import FixtureScriptFactChecker,FixtureQualityReviewer
from tests.m3_golden import setup,execute,NOW

class EditorialRevisionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.db=Database(self.root/'test.db');self.addCleanup(self.db.close)
        for name in ('socket.create_connection','socket.socket.connect','tech_uncovered.scripting.providers.openai_live.OpenAIModel.request'):
            p=patch(name,side_effect=AssertionError('No live calls'));p.start();self.addCleanup(p.stop)
        self.bundle,self.cfg,self.choice=setup(self.db)
        self.bundle['draft']['visual_notes']=['End on a three-step frame: “Documented configuration → deployment test → measured result.”']
        self.bundle['draft']['pronunciation_notes']=['Example pronunciation']
        self.result=execute(self.db,self.bundle,self.cfg,self.choice)
        self.reports=self.root/'reports';self.folder=export(self.result,self.reports)
        self.sid=self.result['script_id']
        self.old=copy.deepcopy(self.result['draft'])
        row=next(s for sec in self.old['sections'] if sec['name']!='HOOK' for s in sec['sentences'])
        self.edits={row['sentence_id']:row['text'].rstrip('.')+'!'}
    def make(self):
        m,p=create(self.reports,self.sid,self.edits,self.db,NOW,self.cfg)
        return m,p,load(self.reports,self.sid,m['revision'],self.db,NOW,self.cfg)
    def test_revision_is_append_only_and_invalidates_reviews(self):
        before={p.name:p.read_bytes() for p in self.folder.iterdir() if p.is_file()}
        m,p,x=self.make()
        self.assertEqual(m['revision'],2)
        self.assertEqual(json.loads((p/'fact_check.json').read_text()),None)
        self.assertEqual(json.loads((p/'quality_review.json').read_text()),None)
        self.assertEqual(json.loads((p/'readiness.json').read_text())['status'],'AWAITING_FACT_CHECK')
        self.assertEqual(before,{p.name:p.read_bytes() for p in self.folder.iterdir() if p.is_file()})
        self.assertEqual(self.db.connection.execute('SELECT COUNT(*) FROM script_drafts WHERE script_run_id=?',(self.sid,)).fetchone()[0],2)
    def test_preserves_every_mapping_hook_and_research(self):
        _,_,x=self.make()
        for name in ('research_packet','sources','angle','outline'):
            self.assertEqual(x['data'][name],json.loads((self.folder/(name+'.json')).read_text()))
        for name in ('selected_hook','selected_hook_id','hook_candidates','research_packet_id','final_angle','on_screen_text'):
            self.assertEqual(x['draft'][name],self.old[name])
        for sec,oldsec in zip(x['draft']['sections'],self.old['sections']):
            for s,old in zip(sec['sentences'],oldsec['sentences']):
                self.assertEqual({k:v for k,v in s.items() if k!='text'},{k:v for k,v in old.items() if k!='text'})
    def test_hook_edits_rejected(self):
        with self.assertRaisesRegex(ValueError,'hook is locked'):
            create(self.reports,self.sid,{'selected-hook':'New hook'},self.db,NOW,self.cfg)
    def test_unsupported_edit_rejected_before_persistence(self):
        edits={next(iter(self.edits)):'The product is completely reliable.'}
        with self.assertRaisesRegex(ValueError,'scope validation'):
            create(self.reports,self.sid,edits,self.db,NOW,self.cfg)
        self.assertEqual(self.db.connection.execute('SELECT COUNT(*) FROM script_drafts WHERE script_run_id=?',(self.sid,)).fetchone()[0],1)
    def test_tamper_rejected(self):
        _,p,_=self.make();draft=json.loads((p/'script.json').read_text())
        draft['sections'][1]['sentences'][0]['claim_ids']=['invented']
        (p/'script.json').write_text(json.dumps(draft))
        with self.assertRaisesRegex(ValueError,'database'):
            load(self.reports,self.sid,2,self.db,NOW,self.cfg)
    def test_only_fact_check_then_quality(self):
        _,p,x=self.make()
        b=copy.deepcopy(self.bundle);b['approved_sentence_texts']+=list(self.edits.values())
        checker=Mock(wraps=FixtureScriptFactChecker(b));reviewer=Mock(wraps=FixtureQualityReviewer(b))
        events=[]
        checker.check.side_effect=lambda *a:(events.append('fact_check') or FixtureScriptFactChecker(b).check(*a))
        reviewer.review.side_effect=lambda *a:(events.append('quality') or FixtureQualityReviewer(b).review(*a))
        with patch('tech_uncovered.scripting.pipeline.collect',side_effect=AssertionError('Research forbidden')),patch('tech_uncovered.scripting.providers.fixtures.FixtureScriptGenerator.generate',side_effect=AssertionError('Generation forbidden')):
            result=review(x,self.db,checker,reviewer,Budget(self.cfg,offline=True),NOW,self.cfg)
        self.assertEqual(events,['fact_check','quality'])
        self.assertEqual(result['readiness']['status'],'READY_FOR_PRODUCTION')
        self.assertEqual(json.loads((p/'fact_check.json').read_text())['revision'],2)
        self.assertEqual(result['cost']['script_generation_cost']['model_calls'],0)
        self.assertEqual(result['cost']['search_calls'],0)
        self.assertEqual(result['cost']['fetch_attempts'],0)
        self.assertEqual(result['cost']['actual_cost_usd'],0)
    def test_reviewed_revision_cannot_be_overwritten(self):
        _,_,x=self.make();b=copy.deepcopy(self.bundle);b['approved_sentence_texts']+=list(self.edits.values())
        review(x,self.db,FixtureScriptFactChecker(b),FixtureQualityReviewer(b),Budget(self.cfg,offline=True),NOW,self.cfg)
        with self.assertRaisesRegex(ValueError,'already'):
            load(self.reports,self.sid,2,self.db,NOW,self.cfg)
    def test_explicit_revision_required_for_old_resume(self):
        from tech_uncovered.scripting.resume import load_resume
        with self.assertRaisesRegex(ValueError,'accepted-pivot|Minimal resume'):
            load_resume(self.reports,self.sid,self.db,NOW,self.cfg)

    def test_metadata_revision_from_explicit_base_preserves_content(self):
        m,p,x=self.make()
        before={f.name:f.read_bytes() for f in p.iterdir()}
        # Reviewed bases remain valid sources for a new append-only revision.
        b=copy.deepcopy(self.bundle);b['approved_sentence_texts']+=list(self.edits.values())
        review(x,self.db,FixtureScriptFactChecker(b),FixtureQualityReviewer(b),Budget(self.cfg,offline=True),NOW,self.cfg)
        before={f.name:f.read_bytes() for f in p.iterdir()}
        edits={'pronunciation_notes':[]}
        if x['draft'].get('visual_notes'):
            edits['visual_note_replacements']={'0':'Open on a restrained card reading “Documentation ≠ workflow guarantee.”'}
        else:
            self.fail('Fixture must contain visual notes')
        m2,p2=create(self.reports,self.sid,edits,self.db,NOW,self.cfg,base_revision=2)
        revised=load(self.reports,self.sid,3,self.db,NOW,self.cfg)
        self.assertEqual(m2['parent_revision'],2)
        self.assertEqual(m2['status'],'AWAITING_FACT_CHECK')
        self.assertEqual(m2['invalidated'],['fact_check','quality_review','readiness'])
        self.assertEqual(revised['scope_validation']['result'],'PASS')
        self.assertEqual(revised['draft']['pronunciation_notes'],[])
        self.assertEqual(revised['draft']['visual_notes'][0],edits['visual_note_replacements']['0'])
        for k,v in x['draft'].items():
            if k not in ('revision','visual_notes','pronunciation_notes'):self.assertEqual(revised['draft'][k],v,k)
        self.assertEqual(before,{f.name:f.read_bytes() for f in p.iterdir()})
        b['draft']['visual_notes']=revised['draft']['visual_notes']
        events=[]
        checker=Mock();checker.check.side_effect=lambda *a:(events.append('fact_check') or FixtureScriptFactChecker(b).check(*a))
        reviewer=Mock();reviewer.review.side_effect=lambda *a:(events.append('quality') or FixtureQualityReviewer(b).review(*a))
        with patch('tech_uncovered.scripting.pipeline.collect',side_effect=AssertionError('No research')),patch('tech_uncovered.scripting.providers.fixtures.FixtureScriptGenerator.generate',side_effect=AssertionError('No generation')):
            review(revised,self.db,checker,reviewer,Budget(self.cfg,offline=True),NOW,self.cfg)
        self.assertEqual(events,['fact_check','quality'])

    def test_metadata_invalid_inputs_rejected(self):
        for edits in ({'visual_note_replacements':{'-1':'x'}},{'visual_note_replacements':{'999':'x'}},
                      {'pronunciation_notes':'x'},{'pronunciation_notes':[None]},
                      {'hook_candidates':[]},{'visual_note_replacements':[]},
                      {'visual_note_replacements':{'0':''}}):
            with self.subTest(edits=edits),self.assertRaises(ValueError):
                create(self.reports,self.sid,edits,self.db,NOW,self.cfg)

    def test_base_revision_integrity_checked(self):
        _,p,_=self.make()
        draft=json.loads((p/'script.json').read_text());draft['word_count']=0
        (p/'script.json').write_text(json.dumps(draft))
        with self.assertRaisesRegex(ValueError,'database'):
            create(self.reports,self.sid,{'pronunciation_notes':[]},self.db,NOW,self.cfg,base_revision=2)

    def test_omitted_base_still_uses_original(self):
        self.make()
        edits={next(iter(self.edits)):next(iter(self.edits.values())).rstrip('!')+'?'}
        m,_=create(self.reports,self.sid,edits,self.db,NOW,self.cfg)
        self.assertEqual(m['parent_revision'],1)

    def test_metadata_scope_failure_does_not_persist(self):
        edits={'visual_note_replacements':{'0':'Show that Astra is reliable.'},'pronunciation_notes':[]}
        with self.assertRaisesRegex(ValueError,'scope validation'):
            create(self.reports,self.sid,edits,self.db,NOW,self.cfg)
        self.assertFalse((self.folder/'editorial-revisions').exists())

    def test_cli_forwards_base_revision(self):
        import argparse
        from tech_uncovered.scripting.cli import add_parser,execute_revise
        parser=argparse.ArgumentParser();add_parser(parser.add_subparsers())
        edits_path=self.root/'edits.json';edits_path.write_text(json.dumps({'pronunciation_notes':[]}))
        args=parser.parse_args(['script','--revise',self.sid,'--base-revision','4','--edits',str(edits_path)])
        with patch('tech_uncovered.scripting.cli.Database',return_value=Mock()),patch('tech_uncovered.scripting.cli.configuration',return_value=self.cfg),patch('tech_uncovered.scripting.editorial_revision.create',return_value=({'revision':5},self.root)) as mocked,patch('builtins.print'):
            self.assertEqual(execute_revise(args),0)
        self.assertEqual(mocked.call_args.kwargs['base_revision'],4)
