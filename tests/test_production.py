import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from tech_uncovered.database import Database
from tests.m3_golden import setup,execute
from tech_uncovered.production.planning import build
from tech_uncovered.production.qa import check
from tech_uncovered.production.cli import execute as produce
from types import SimpleNamespace

class ProductionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        p=patch('socket.socket.connect',side_effect=AssertionError('No network'));p.start();self.addCleanup(p.stop)
        db=Database(self.root/'test.db');self.addCleanup(db.close)
        bundle,cfg,choice=setup(db);self.result=execute(db,bundle,cfg,choice)
        self.draft=self.result['draft'];self.packet=self.result['packet'];self.readiness=self.result['readiness']
        self.spec=build(self.draft,self.packet,self.readiness,self.root/'video',selected=choice).to_dict()
    def qa(self,spec=None):return check(spec or self.spec,self.draft,self.packet,self.root/'video')
    def test_complete_plan(self):
        self.assertTrue(self.qa()['passed']);self.assertEqual(self.spec['fps'],30)
        self.assertEqual(self.spec['scenes'][-1]['end_frame'],round(self.draft['estimated_duration']*30))
        self.assertEqual(' '.join(c['text'] for s in self.spec['scenes'] for c in s['caption_segments']),self.draft['full_script'])
    def test_requires_explicit_preview_for_unapproved(self):
        with self.assertRaises(ValueError):build(self.draft,self.packet,{'status':'EDITORIAL_REVIEW'},self.root/'reject')
        spec=build(self.draft,self.packet,{'status':'EDITORIAL_REVIEW'},self.root/'preview',preview=True)
        self.assertEqual(spec.production_status,'PREVIEW_ONLY')
    def test_overlap_and_missing_scene_fail(self):
        spec=copy.deepcopy(self.spec);spec['scenes'][1]['start_frame']-=1
        self.assertIn('SCENE_GAP_OR_OVERLAP',self.qa(spec)['errors'])
        spec['scenes'].pop();self.assertFalse(self.qa(spec)['passed'])
    def test_missing_asset_and_tamper_fail(self):
        asset=self.root/'video/assets/grid.svg';asset.write_text('changed')
        self.assertIn('ASSET_HASH',self.qa()['errors']);asset.unlink()
        self.assertIn('UNRESOLVED_ASSET',self.qa()['errors'])
    def test_visual_provenance_and_invented_text_fail(self):
        spec=copy.deepcopy(self.spec);spec['scenes'][0]['on_screen_text'][0]['text']='Unsupported performance claim'
        self.assertIn('NEW_FACTUAL_VISUAL_TEXT',self.qa(spec)['errors'])
        spec=copy.deepcopy(self.spec);spec['scenes'][0]['on_screen_text'][0]['claim_ids']=[]
        self.assertIn('ALTERED_claim_ids',self.qa(spec)['errors'])
    def test_caption_gap_fails(self):
        spec=copy.deepcopy(self.spec);spec['scenes'][0]['caption_segments'][0]['start_frame']+=1
        self.assertIn('CAPTION_TIMING',self.qa(spec)['errors'])
    def test_cli_fixture_export(self):
        fixture=self.root/'fixture.json';fixture.write_text(json.dumps({'synthetic':True,'draft':self.draft,'packet':self.packet,'readiness':self.readiness,'selected':{}}))
        out=self.root/'export'
        with patch('builtins.print'):self.assertEqual(produce(SimpleNamespace(output=out,fixture=fixture,preview=True)),0)
        self.assertTrue((out/'captions.srt').is_file());self.assertEqual(json.loads((out/'render-props.json').read_text())['spec']['video_id'],self.spec['video_id'])
    def test_creative_dna_and_voice_contract(self):
        dna=self.spec['creative_dna']
        for key in ('topic','cohort','story_type','angle_type','hook_type','hook_text','word_count','duration','scene_count','scene_archetypes','CTA_type','visual_density','spoken_list_count','payoff_timestamp'):self.assertIn(key,dna)
        self.assertEqual(self.spec['voice_timing']['status'],'ESTIMATED')
        self.assertIsNone(self.spec['voice_timing']['audio_path'])
