import copy
import json
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from unittest.mock import patch

from tech_uncovered.database import Database
from tech_uncovered.intelligence.editorial import eligible, story_fields, story_first, researchability_fields
from tech_uncovered.intelligence.selection import select_candidates
from tech_uncovered.intelligence.pipeline import run_intelligence
from tech_uncovered.scripting.selection import select_ideas
from tests.intelligence_helpers import seed, load
from tests.script_helpers import selected


def choice(n, story, cohort, score, research=60):
    idea = dict(idea_id=str(n), topic=story, cluster_id=story, proposed_angle=str(n),
                idea_score=score, category='RECOMMENDED FOR RESEARCH', similarity_status='CLEAR',
                source_opportunities=[{'market_cohort':cohort}])
    return {'idea':idea, **story_fields(idea), **researchability_fields(idea,research)}


class EditorialPolicyTests(unittest.TestCase):
    def test_story_first_before_extra_angles(self):
        rows=[choice(1,'a','AF',80),choice(2,'a','AF',79),choice(3,'b','SEC',74)]
        result=story_first(rows,3)
        self.assertEqual([r['idea']['idea_id'] for r in result],['1','3','2'])
        self.assertEqual(result[-1]['preview_selection_phase'],'SECONDARY_ANGLE_FILL')
        self.assertEqual(result[-1]['angle_rank_within_topic'],2)
        self.assertEqual(result[-1]['topic_rank'],1)

    def test_max_two_and_no_padding(self):
        result=story_first([choice(n,'same','AF',80-n) for n in range(4)],10)
        self.assertEqual(len(result),2)

    def test_cohort_tiebreak_within_band_only(self):
        rows=[choice(1,'a','AF',90),choice(2,'b','AF',89),choice(3,'c','SEC',85),choice(4,'d','BUS',60)]
        self.assertEqual([r['idea']['idea_id'] for r in story_first(rows,4)],['1','3','2','4'])

    def test_deterministic_and_scores_unchanged(self):
        rows=[choice(1,'a','AF',80),choice(2,'b','SEC',80),choice(3,'a','AF',79)]
        before=copy.deepcopy(rows)
        a=story_first(rows,3);b=story_first(list(reversed(copy.deepcopy(before))),3)
        self.assertEqual([r['idea']['idea_id'] for r in a],[r['idea']['idea_id'] for r in b])
        self.assertEqual([r['idea'] for r in rows],[r['idea'] for r in before])

    def test_cluster_identity_not_raw_topic(self):
        a=choice(1,'event1','AF',80);b=copy.deepcopy(a);b['idea']['topic']='Alternative spelling'
        self.assertEqual(story_fields(a['idea'])['canonical_story_id'],story_fields(b['idea'])['canonical_story_id'])
        b['idea']['cluster_id']='event2';b['idea']['topic']=a['idea']['topic']
        self.assertNotEqual(story_fields(a['idea'])['canonical_story_id'],story_fields(b['idea'])['canonical_story_id'])

    def test_editorial_states_normalized(self):
        for category in ['REJECTED','REVIEW_REQUIRED','REJECTED / REVIEW REQUIRED','REJECTED_REVIEW_REQUIRED']:
            i=choice(1,'a','AF',90)['idea'];i['category']=category
            self.assertFalse(eligible(i,include_backlog=True))
        i=choice(1,'a','AF',90)['idea'];i['similarity_status']='REVIEW'
        self.assertFalse(eligible(i,include_backlog=True))

    def test_backlog_is_explicit(self):
        i=choice(1,'a','AF',90)['idea'];i['category']='BACKLOG'
        self.assertFalse(eligible(i));self.assertTrue(eligible(i,include_backlog=True))

    def test_versioned_researchability_pair(self):
        i={'idea_researchability_score':57.5}
        r=researchability_fields(i,77)
        self.assertEqual(r['m2_researchability_score'],57.5)
        self.assertEqual(r['preview_researchability_score'],77)
        self.assertNotEqual(r['m2_researchability_version'],r['preview_researchability_version'])
        self.assertEqual(i,{'idea_researchability_score':57.5})


class IntakeDiversityTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.db=Database(Path(self.tmp.name)/'test.db')
    def tearDown(self):
        self.db.close();self.tmp.cleanup()
    def radar(self):
        r=load('radar.json');base=r['videos'][0];r['videos']=[]
        for n,(co,score) in enumerate([('AF',90),('AF',89),('AF',88),('DEV',85),('BUS',20)]):
            v=copy.deepcopy(base);v.update(video_id='v'+str(n),market_cohort=co,opportunity_score=score,researchability_score=60,production_fit='GOOD')
            r['videos'].append(v)
        self.db.save_run(r)
        return r['run_id']
    def test_coverage_then_global_fill_without_weak_quota(self):
        rid=self.radar();r=select_candidates(self.db,rid,3)['candidates']
        self.assertEqual([v['video_id'] for v in r],['v0','v3','v1'])
        self.assertEqual([v['selection_phase'] for v in r],['COHORT_COVERAGE','COHORT_COVERAGE','GLOBAL_FILL'])
        self.assertEqual([v['global_rank'] for v in r],[1,4,2])
        self.assertEqual([v['cohort_rank'] for v in r],[1,1,2])
        self.assertEqual([v['opportunity_score'] for v in r],[90,85,89])
        self.assertNotIn('BUS',{v['market_cohort'] for v in r})
    def test_intake_deterministic_and_band_validation(self):
        rid=self.radar()
        self.assertEqual(select_candidates(self.db,rid,3),select_candidates(self.db,rid,3))
        with self.assertRaises(ValueError):select_candidates(self.db,rid,3,quality_band=float('nan'))
    def test_reject_regression_and_backlog_label(self):
        c=selected(self.db);i=c['idea'];rid=i['intelligence_run_id']
        for category in ['REJECTED / REVIEW REQUIRED','REVIEW_REQUIRED']:
            i['category']=category
            self.db.connection.execute('UPDATE idea_candidates SET payload=?',(json.dumps(i),))
            with self.assertRaises(ValueError):select_ideas(self.db,rid,prefer_researchable=True)
        i['category']='BACKLOG';i['review_status']='BACKLOG'
        self.db.connection.execute('UPDATE idea_candidates SET payload=?',(json.dumps(i),))
        with self.assertRaises(ValueError):select_ideas(self.db,rid,prefer_researchable=True)
        r=select_ideas(self.db,rid,prefer_researchable=True,include_backlog=True)[0]
        self.assertEqual(r['editorial_state'],'BACKLOG')

    def test_new_snapshots_persist_selection_and_story_fields(self):
        from tests.intelligence_helpers import config, NOW
        from tech_uncovered.intelligence.models import digest
        seed(self.db)
        original={json.loads(r[0])['video_id']:json.loads(r[0]) for r in self.db.connection.execute('SELECT payload FROM video_scores')}
        from tech_uncovered.intelligence.providers import LocalTranscriptProvider
        r=run_intelligence(self.db,config(),NOW,radar_run_id='radar-intelligence-fiction-v1',transcript_provider=LocalTranscriptProvider(load('context.json')['videos']))
        self.assertTrue(r['ideas'])
        for v in r['candidates']:
            self.assertEqual(v['snapshot_hash'],digest(original[v['video_id']]))
            self.assertIn(v['selection_phase'],{'COHORT_COVERAGE','GLOBAL_FILL'})
            self.assertGreater(v['global_rank'],0);self.assertGreater(v['cohort_rank'],0)
        for idea in r['ideas']:
            self.assertTrue(idea['canonical_story_id']);self.assertTrue(idea['canonical_story_label'])
            self.assertEqual(idea['m2_researchability_score'],idea['idea_researchability_score'])
            self.assertIsInstance(idea['preview_researchability_score'],(int,float))
            stored=json.loads(self.db.connection.execute('SELECT payload FROM idea_candidates WHERE intelligence_run_id=? AND idea_id=?',(r['intelligence_run_id'],idea['idea_id'])).fetchone()[0])
            self.assertEqual(stored,idea)

    def test_old_snapshot_preview_preserves_payload_and_labels_pair(self):
        c=selected(self.db);rid=c['idea']['intelligence_run_id']
        before=list(self.db.connection.execute('SELECT payload FROM idea_candidates'))
        r=select_ideas(self.db,rid,prefer_researchable=True)[0]
        self.assertEqual([x[0] for x in before],[x[0] for x in self.db.connection.execute('SELECT payload FROM idea_candidates')])
        self.assertIn('m2_researchability_score',r);self.assertIn('preview_researchability_score',r)
        self.assertEqual(r['idea']['idea_score'],c['idea']['idea_score'])

    def test_intake_excludes_null_current_score_without_changing_score(self):
        rid=self.radar()
        row=self.db.connection.execute("SELECT rowid,payload FROM video_scores WHERE video_id='v4'").fetchone()
        v=json.loads(row['payload']);v['opportunity_score']=None
        self.db.connection.execute('UPDATE video_scores SET payload=? WHERE rowid=?',(json.dumps(v),row['rowid']))
        r=select_candidates(self.db,rid,50)['candidates']
        self.assertNotIn('v4',[v['video_id'] for v in r])

    def test_backlog_cli_label_and_no_network(self):
        import io
        from contextlib import redirect_stdout
        from tech_uncovered.cli import main
        c=selected(self.db);i=c['idea'];i.update(category='BACKLOG',review_status='BACKLOG')
        self.db.connection.execute('UPDATE idea_candidates SET payload=?',(json.dumps(i),));self.db.connection.commit()
        out=io.StringIO()
        with redirect_stdout(out),patch('socket.socket.connect',side_effect=AssertionError('No network')):
            code=main(['script','--preview','--include-backlog','--db',str(Path(self.tmp.name)/'test.db'),'--intelligence-run-id',i['intelligence_run_id']])
        self.assertEqual(code,0)
        self.assertIn('"editorial_state": "BACKLOG"',out.getvalue())
        self.assertIn('"preview_researchability_score"',out.getvalue())
