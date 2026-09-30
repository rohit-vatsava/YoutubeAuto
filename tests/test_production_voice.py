import copy,json,math,tempfile,unittest
from pathlib import Path
from tests import test_production as base
from tech_uncovered.production.narration import MockNarrationProvider,NarrationResult,ExternalNarrationAdapter,validate
from tech_uncovered.production.assets import AvatarAsset,AssetRouter
from tech_uncovered.production.audio import AudioMix,SoundEffect
from tech_uncovered.production.planning import build
from tech_uncovered.production.qa import check
from tech_uncovered.production.timing import phrase_groups

class VoiceProductionTests(unittest.TestCase):
    def setUp(self):
        base.ProductionTests.setUp(self)
        self.narration=MockNarrationProvider().narrate(self.draft,self.root/'mock.wav')
    def make(self,avatar=None,narration=True):
        root=self.root/'aligned'
        spec=build(self.draft,self.packet,self.readiness,root,preview=True,narration=self.narration if narration else None,avatar=avatar or AvatarAsset('host')).to_dict()
        return spec,check(spec,self.draft,self.packet,root)
    def test_timestamp_round_trip(self):
        parsed=NarrationResult.from_dict(self.narration.to_dict())
        self.assertEqual(validate(parsed,self.draft),self.narration)
        self.assertTrue(parsed.provenance['synthetic'])
    def test_alignment_rejects_wrong_words_and_provenance(self):
        for mutation in (lambda r:setattr(r.words[0],'text','invented'),lambda r:r.provenance.update(script_sha256='bad'),lambda r:setattr(r.words[0],'start_seconds',float('nan')),lambda r:setattr(r.words[1],'start_seconds',0),lambda r:setattr(r,'duration_seconds',50)):
            result=copy.deepcopy(self.narration);mutation(result)
            with self.assertRaises(ValueError):validate(result,self.draft)
    def test_audio_drives_beats_and_captions(self):
        # Nonuniform timing with pauses and leading silence, not the estimate formula.
        for word in self.narration.words:
            word.start_seconds=.3+word.start_seconds*.98;word.end_seconds=.3+word.end_seconds*.98
        for sentence in self.narration.sentences:
            sentence.start_seconds=.3+sentence.start_seconds*.98;sentence.end_seconds=.3+sentence.end_seconds*.98
        spec,qa=self.make();self.assertTrue(qa['passed'],qa)
        self.assertEqual(spec['scenes'][1]['start_frame'],round(self.narration.sentences[1].start_seconds*30))
        self.assertEqual(spec['scenes'][0]['caption_segments'][0]['start_frame'],9)
        self.assertEqual(spec['scenes'][-1]['end_frame'],math.ceil(self.narration.duration_seconds*30))
    def test_estimated_fallback(self):
        spec,qa=self.make(narration=False)
        self.assertEqual(spec['voice_timing']['status'],'ESTIMATED');self.assertTrue(qa['passed'],qa)
    def test_avatar_all_positions_and_no_collision(self):
        for position in ('left','right','center'):
            for size in (.2,.3,.4):
                with self.subTest(position=position,size=size):
                    spec,qa=self.make(AvatarAsset('host',position=position,width_fraction=size))
                    self.assertTrue(qa['passed'],qa);self.assertEqual(spec['scenes'][0]['scene_type'],'AvatarHost')
        with self.assertRaises(ValueError):AvatarAsset('host',width_fraction=.6).bounds()
    def test_collision_is_detected(self):
        spec,_=self.make();spec['scenes'][0]['avatar']['bounds']['y']=1300
        qa=check(spec,self.draft,self.packet,self.root/'aligned')
        self.assertIn('CAPTION_AVATAR_COLLISION',qa['errors'])
    def test_phrase_length_and_emphasis(self):
        self.narration.words[0].emphasis=True
        spec,qa=self.make();self.assertTrue(qa['passed'])
        caps=[c for s in spec['scenes'] for c in s['caption_segments']]
        self.assertTrue(all(1<=len(c['text'].split())<=6 for c in caps))
        self.assertEqual(caps[0]['emphasis_words'],[0])
        self.assertEqual(' '.join(c['text'] for c in caps),self.draft['full_script'])
    def test_mappings_and_identity_preserved(self):
        spec,_=self.make();source={r['sentence_id']:r for s in self.draft['sections'] for r in s['sentences']}
        for beat in spec['narration_beats']:
            for key in ('claim_ids','source_ids','evidence_passage_ids'):self.assertEqual(beat[key],source[beat['sentence_id']][key])
        self.assertEqual(spec['script_id'],self.draft['script_id']);self.assertEqual(spec['revision'],self.draft['revision'])
    def test_retention_metadata(self):
        spec,_=self.make();r=spec['retention_metadata']
        self.assertAlmostEqual(r['avatar_screen_time'],6)
        self.assertEqual(r['hook_end_time'],spec['narration_beats'][0]['end_frame']/30)
        self.assertEqual(r['scene_change_times'],[s['start_frame']/30 for s in spec['scenes'][1:]])
        self.assertEqual(r['visual_change_count'],sum(len(s['visual_events']) for s in spec['scenes']))
        self.assertEqual(spec['creative_dna']['payoff_start_time'],r['payoff_start_time'])
    def test_asset_sources_and_no_provider(self):
        router=AssetRouter()
        for source in ('avatar','official_documentation','official_screenshot','local_graphic','generated_image','generated_video','stock_licensed'):
            self.assertEqual(router.route('future',source,provenance={'source':'fixture'}).status,'PLACEHOLDER')
        asset=router.route('local','local_graphic',self.root/'video/assets/grid.svg',provenance={'created_by':'fixture'},output=self.root/'routed',license='original')
        self.assertTrue(asset.sha256);self.assertEqual(asset.license,'original')
        with self.assertRaises(ValueError):router.route('remote','avatar','https://example.invalid/avatar.png',provenance={'source':'user'})
        with self.assertRaises(NotImplementedError):ExternalNarrationAdapter().narrate(self.draft,self.root/'none')
    def test_audio_mix_validation(self):
        self.assertEqual(AudioMix().validate(57).status,'MIX_CONTRACT_ONLY')
        for mix in (AudioMix(master_limiter_db=5),AudioMix(normalization_lufs=float('nan')),AudioMix(sound_effects=[SoundEffect('boom',60)])):
            with self.assertRaises(ValueError):mix.validate(57)
    def test_revision_seven_fixture_and_storyboard(self):
        fixture=json.loads(Path('fixtures/production/astra-revision-7/fixture.json').read_text())
        voice=NarrationResult.from_dict(fixture['narration'])
        spec=build(fixture['draft'],fixture['packet'],fixture['readiness'],self.root/'astra',preview=True,narration=voice,avatar=AvatarAsset('host'),selected=fixture['selected']).to_dict()
        qa=check(spec,fixture['draft'],fixture['packet'],self.root/'astra')
        self.assertTrue(qa['passed'],qa);self.assertEqual(spec['revision'],7);self.assertEqual(spec['duration_target'],57.2)
        self.assertEqual(spec['scenes'][0]['on_screen_text'][0]['source_sentence_id'],'selected-hook')
        tool=next(s for s in spec['scenes'] if s['beat_ids']==['beat-s2'])
        self.assertEqual(tool['on_screen_text'][0]['source_sentence_id'],'ost-2')
        self.assertTrue(all(e['focus']['item_end']-e['focus']['item_start']<=3 for e in tool['visual_events'] if e['type']=='LIST_GROUP'))
        self.assertEqual(spec['scenes'][0]['avatar']['end_frame'],90)
    def test_timestamp_caption_drift_detected(self):
        spec,_=self.make();spec['scenes'][0]['caption_segments'][0]['start_frame']+=3
        qa=check(spec,self.draft,self.packet,self.root/'aligned')
        self.assertIn('CAPTION_AUDIO_ALIGNMENT',qa['errors'])
