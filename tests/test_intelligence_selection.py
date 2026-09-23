import json
import tempfile
import unittest
from pathlib import Path
from tech_uncovered.database import Database
from tech_uncovered.intelligence.selection import select_candidates
from tests.intelligence_helpers import seed, load


class SelectionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.db=Database(Path(self.temp.name)/'test.db')
        seed(self.db)
    def tearDown(self):
        self.db.close(); self.temp.cleanup()

    def test_exact_run_and_top_n(self):
        selected=select_candidates(self.db,'radar-intelligence-fiction-v1',3)
        self.assertEqual(len(selected['candidates']),3)
        self.assertTrue(all(v['radar_run_id']=='radar-intelligence-fiction-v1' for v in selected['candidates']))
        self.assertTrue(all('snapshot_hash' in v for v in selected['candidates']))
        self.assertEqual(selected['candidates'][0]['velocity_adjusted_score'],max(v['velocity_adjusted_score'] for v in load('radar.json')['videos']))

    def test_no_mutable_table_leakage(self):
        before=select_candidates(self.db,'radar-intelligence-fiction-v1',1)['candidates'][0]
        changed={**before,'title':'Changed after Radar snapshot','views':0}
        self.db.save_videos([changed])
        after=select_candidates(self.db,'radar-intelligence-fiction-v1',1)['candidates'][0]
        self.assertEqual(before,after)

    def test_default_latest_complete_live_only(self):
        fixture=load('radar.json')
        with self.assertRaises(ValueError): select_candidates(self.db)
        for run,mode,status in [('live-old','live','complete'),('live-new','live','complete'),('partial','live','partial'),('offline','offline','complete')]:
            fixture['run_id']=run
            fixture['metadata']['mode']=mode
            fixture['metadata']['status']=status
            self.db.save_run(fixture)
        self.assertEqual(select_candidates(self.db)['radar_run_id'],'live-new')
        self.assertEqual(select_candidates(self.db,'partial')['metadata']['status'],'partial')
        with self.assertRaises(ValueError):select_candidates(self.db,'missing')

    def test_excludes_provisional_and_ineligible(self):
        result=load('radar.json')
        result['run_id']='exclusions'
        result['videos'][0]['provisional']=True
        result['videos'][1]['eligibility_reason']='insufficient_baseline_sample'
        self.db.save_run(result)
        selected=select_candidates(self.db,'exclusions',100)['candidates']
        self.assertNotIn(result['videos'][0]['video_id'],[v['video_id'] for v in selected])
        self.assertNotIn(result['videos'][1]['video_id'],[v['video_id'] for v in selected])

    def test_old_topic_membership_not_reclassified(self):
        result=load('radar.json'); result['run_id']='legacy'
        for v in result['videos']:v.pop('radar_topics',None)
        result['topics']=[]
        self.db.save_run(result)
        selected=select_candidates(self.db,'legacy',2)['candidates']
        self.assertTrue(all(v['radar_topics']==[] for v in selected))

    def test_bad_record_does_not_abort_selection(self):
        self.db.connection.execute("UPDATE video_scores SET payload='{}' WHERE rowid=(SELECT min(rowid) FROM video_scores)")
        self.db.connection.commit()
        self.assertTrue(select_candidates(self.db,'radar-intelligence-fiction-v1')['candidates'])

    def test_invalid_title_is_skipped_not_allowed_to_crash_extraction(self):
        row=self.db.connection.execute('SELECT rowid,payload FROM video_scores LIMIT 1').fetchone()
        video=json.loads(row['payload']);video['title']=17
        self.db.connection.execute('UPDATE video_scores SET payload=? WHERE rowid=?',(json.dumps(video),row['rowid']))
        self.db.connection.commit()
        selected=select_candidates(self.db,'radar-intelligence-fiction-v1')
        self.assertEqual(len(selected['failures']),1)
        self.assertTrue(selected['candidates'])
