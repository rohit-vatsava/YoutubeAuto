import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from dataclasses import asdict
from tech_uncovered.production.creative import *
from tech_uncovered.production.planning import build
from tech_uncovered.production.narration import NarrationResult
from tech_uncovered.production.assets import AvatarAsset
from tech_uncovered.production.qa import check

class CreativeDirectorTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
  p=patch('socket.socket.connect',side_effect=AssertionError('No network'));p.start();self.addCleanup(p.stop)
  self.fixture=json.loads(Path('fixtures/production/astra-revision-7/fixture.json').read_text())
  f=self.fixture
  self.spec=build(f['draft'],f['packet'],f['readiness'],self.root,preview=True,selected=f['selected'],
   narration=NarrationResult.from_dict(f['narration']),avatar=AvatarAsset('placeholder')).to_dict()
  self.context=input_from_spec(self.spec,f['draft'])
  self.plan=DeterministicCreativeDirector().direct(self.context)
 def test_schema_roundtrip(self):
  result=LLMCreativeDirector(lambda c,s:json.dumps(self.plan.to_dict())).direct(self.context)
  self.assertEqual(result.to_dict(),self.plan.to_dict())
 def test_deterministic(self):
  self.assertEqual(self.plan.to_dict(),DeterministicCreativeDirector().direct(self.context).to_dict())
 def test_full_coverage(self):
  self.assertEqual([i for s in self.plan.scenes for i in s.narration_sentence_ids], [s['sentence_id'] for s in self.context.sentences])
 def test_missing_narration_rejected(self):
  self.plan.scenes[2].narration_sentence_ids=[]
  with self.assertRaises(ValueError):validate(self.plan,self.context)
 def test_overlap_rejected(self):
  self.plan.scenes[1].start-=.5
  with self.assertRaises(ValueError):validate(self.plan,self.context)
 def test_provenance_preserved(self):
  for s,b in zip(self.plan.scenes,self.spec['narration_beats']):
   self.assertEqual(s.claim_provenance[0]['evidence_passage_ids'],b['evidence_passage_ids'])
 def test_mapping_tamper_rejected(self):
  self.plan.scenes[1].claim_provenance[0]['claim_ids']=[]
  with self.assertRaises(ValueError):validate(self.plan,self.context)
 def test_factual_generation_rejected(self):
  self.plan.asset_generation_requests[1].preferred_provider='HF_LTX';self.plan.scenes[1].provider_preference='HF_LTX'
  with self.assertRaises(ValueError):validate(self.plan,self.context)
 def test_factual_relabel_rejected(self):
  s=self.plan.scenes[1];a=self.plan.asset_generation_requests[1]
  s.visual_type=s.factuality_class='CREATIVE_METAPHOR';a.must_be_factual=False;a.generation_allowed=True
  s.generation_prompt=a.prompt=metaphor_prompt(self.context,s)
  with self.assertRaises(ValueError):validate(self.plan,self.context)
 def test_prompt_safety(self):
  a=next(a for a in self.plan.asset_generation_requests if a.prompt)
  for text in ('9:16','No readable text','no logos','no watermarks','not a real software interface'):self.assertIn(text,a.prompt)
 def test_unsupported_prompt_rejected(self):
  s=next(s for s in self.plan.scenes if s.generation_prompt);s.generation_prompt='GPT is faster and reliable'
  with self.assertRaises(ValueError):validate(self.plan,self.context)
 def test_avatar_six_seconds(self):
  self.assertEqual(self.plan.retention_plan['avatar_screen_time'],6)
  self.assertEqual(len(self.plan.avatar_plan),2)
 def test_no_avatar_available(self):
  context=copy.deepcopy(self.context);context.avatar_availability='UNAVAILABLE'
  plan=DeterministicCreativeDirector().direct(context)
  self.assertFalse(plan.avatar_plan);self.assertFalse(plan.hero_shot.avatar_usage)
 def test_avatar_outside_scene_rejected(self):
  self.plan.avatar_plan[0]['end']=99
  with self.assertRaises(ValueError):validate(self.plan,self.context)
 def test_hook_and_cadence(self):
  self.assertLessEqual(self.plan.retention_plan['first_visual_change_time'],1.2)
  self.assertEqual(self.plan.retention_plan['hook_end_time'],3)
  self.assertLessEqual(self.plan.retention_plan['max_static_hold'],5)
 def test_static_hold_rejected(self):
  self.plan.scenes[0].choreography=self.plan.scenes[0].choreography[:1]
  with self.assertRaises(ValueError):validate(self.plan,self.context)
 def test_payoff(self):
  self.assertEqual(self.plan.scenes[-1].editorial_heading,'FEATURE LIST ≠ DEPLOYMENT DECISION')
  self.assertEqual(self.plan.retention_plan['payoff_start_time'],self.plan.scenes[-1].start)
 def test_no_payoff_rejected(self):
  self.plan.scenes[-1].retention_role='setup'
  with self.assertRaises(ValueError):validate(self.plan,self.context)
 def test_provider_fallback(self):
  a=next(a for a in self.plan.asset_generation_requests if a.prompt)
  self.assertEqual(a.preferred_provider,'HF_LTX');self.assertEqual(a.acceptable_fallback,['AGNES','LOCAL_MOTION_GRAPHIC'])
 def test_unknown_archetype_rejected(self):
  self.plan.scenes[2].scene_archetype='SomeNewProvider'
  with self.assertRaises(ValueError):validate(self.plan,self.context)
 def test_malformed_llm_output_rejected(self):
  for raw in ('not-json',{}, {'shell':'rm -rf /'}):
   with self.subTest(raw=raw),self.assertRaises(ValueError):LLMCreativeDirector(lambda *args:raw).direct(self.context)
 def test_extra_llm_controls_rejected(self):
  raw=self.plan.to_dict();raw['output_path']='/tmp/untrusted'
  with self.assertRaises(ValueError):LLMCreativeDirector(lambda *args:raw).direct(self.context)
 def test_upstream_display_unchanged(self):
  self.plan.scenes[1].on_screen_text[0]['text']='A made-up benchmark'
  with self.assertRaises(ValueError):validate(self.plan,self.context)
 def test_astra_golden(self):
  self.assertEqual(self.plan.revision,7);self.assertEqual(self.plan.creative_concept,'DOCUMENTATION VS DEPLOYMENT')
  self.assertEqual(len(self.plan.scenes),9);self.assertEqual(self.context.target_duration,57.2)
  self.assertEqual(self.plan.retention_plan['timing_basis'],'SYNTHETIC_TIMESTAMPS')
 def test_handoff_qa_and_no_upstream_mutation(self):
  before=copy.deepcopy(self.spec)
  out=apply_plan(self.spec,self.plan,self.context)
  self.assertEqual(self.spec,before)
  self.assertEqual(out['narration_beats'],before['narration_beats'])
  self.assertEqual(out['voice_timing'],before['voice_timing'])
  self.assertTrue(check(out,self.fixture['draft'],self.fixture['packet'],self.root)['passed'])
  self.assertEqual(out['retention_metadata']['generated_media_screen_time'],0)
 def test_readiness_required(self):
  spec=copy.deepcopy(self.spec);spec['provenance']['m3_readiness']='EDITORIAL_REVIEW'
  with self.assertRaises(ValueError):input_from_spec(spec,self.fixture['draft'])
 def test_unknown_asset_rejected(self):
  self.plan.scenes[1].asset_requirements=['not-present']
  with self.assertRaises(ValueError):validate(self.plan,self.context)
 def test_metrics_tamper_rejected(self):
  self.plan.retention_plan['generated_media_screen_time']=9
  with self.assertRaises(ValueError):validate(self.plan,self.context)
