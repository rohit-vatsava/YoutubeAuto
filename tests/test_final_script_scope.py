import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch,Mock
from tech_uncovered.scripting.generation import scope_propositions
from tech_uncovered.scripting.pivot_scope import validate_candidate,classify
from tech_uncovered.scripting.hook_scope import validate_hooks,apply_report
from tech_uncovered.scripting.hooks import score_hooks

class FinalScriptScopeTests(unittest.TestCase):
    def setUp(self):
        data=json.loads((Path(__file__).parent/'fixtures/scope/hooks.json').read_text())
        self.packet=data['packet'];self.raw=data['candidate']['raw_generated_content']
    def validate(self):
        return validate_candidate({'propositions':scope_propositions(self.raw)},self.packet,'script_generation','fixture')
    def test_exact_saved_script_passes_unchanged(self):
        before=copy.deepcopy(self.raw)
        self.assertEqual(self.validate()['result'],'PASS');self.assertEqual(self.raw,before)
    def test_canonical_classifier_used(self):
        from tech_uncovered.scripting import pivot_scope
        with patch.object(pivot_scope,'classify',wraps=classify) as c:
            self.validate();self.assertGreaterEqual(c.call_count,len(scope_propositions(self.raw)))
    def test_inherited_sentence_mappings(self):
        p=self.validate()['propositions'][0]
        for atom in p['atomic_units']:
            self.assertTrue(atom['claim_ids'] and atom['passage_ids'] and atom['evidence_ids'])
    def test_title_and_display_framing(self):
        rows={r['surface']:r for r in self.validate()['propositions']}
        self.assertEqual(rows['title']['classification'],'NONFACTUAL_EDITORIAL')
        self.assertEqual(rows['on_screen_text/0']['classification'],'NONFACTUAL_EDITORIAL')
    def test_caution_safe_positive_blocked(self):
        for text in ('Listed tool support does not show that a tool is enabled, appropriate, or reliable in every deployment.',
                     'Listed support ≠ guaranteed availability, appropriateness, reliability, or workflow payoff.'):
            self.assertEqual(classify({'text':text},self.packet)['classification'],'NONFACTUAL_EDITORIAL')
        self.assertEqual(classify({'text':'The model is reliable.'},self.packet)['classification'],'FORBIDDEN_CATEGORY')
    def test_unrelated_evidence_cannot_support_list(self):
        item=self.raw['sections'][1]['sentences'][0]
        item['evidence_passage_ids']=['passage-beac863116ee521a']
        self.assertEqual(self.validate()['result'],'FAIL')
    def test_new_fact_fails(self):
        self.raw['sections'][0]['sentences'][0]['text']+=' It reads minds.'
        self.assertEqual(self.validate()['result'],'FAIL')
    def test_visual_claim_cannot_hide_in_instruction(self):
        self.raw['visual_notes'][0]='Open on a restrained card reading “The model is reliable.”'
        self.assertEqual(self.validate()['result'],'FAIL')
    def test_unknown_caption_fails(self):
        self.raw['captions']=['It improves productivity by 50%.']
        self.assertEqual(self.validate()['result'],'FAIL')
    def test_no_repair_invents_facts(self):
        item=self.raw['on_screen_text'][2];item['text']=item['text'].replace('max','unlimited')
        self.assertEqual(self.validate()['result'],'FAIL')
    def test_selected_hook_unchanged(self):
        hooks=self.raw['hook_candidates']
        apply_report(hooks,validate_hooks(hooks,self.packet,'fixture'))
        self.assertEqual(score_hooks(hooks,self.packet)['hook_id'],'hook-5')
    def test_resume_first_call_fact_check(self):
        from tech_uncovered.scripting.pipeline import generate_from_packet
        from tech_uncovered.scripting.costs import Budget
        from tests.script_helpers import config
        cfg=config();packet=copy.deepcopy(self.packet)
        packet.setdefault('research_packet_id','fixture-packet')
        selected={'idea':{'proposed_angle':'saved'}}
        angle={'evidence_basis':['claim-api-capabilities'],'originality_status':'REVIEW'}
        result=dict(packet=packet,selected=selected,script_id='fixture',scope_contract_version=2,
                    resume_metadata={'stages_executed':[]},revisions=[])
        gen=Mock();check=Mock();review=Mock()
        check.check.side_effect=RuntimeError('STOP_AT_FACT_CHECK')
        with patch('tech_uncovered.scripting.storage.generation_checkpoint'),patch('tech_uncovered.scripting.storage.save_draft'):
            with self.assertRaisesRegex(RuntimeError,'STOP_AT_FACT_CHECK'):
                generate_from_packet(None,result,cfg,gen,check,review,Budget(cfg,offline=True),'2026-09-22T00:00:00+00:00',
                    reused_angle=angle,reused_outline={'beats':[]},reused_generation=self.raw)
        gen.refine.assert_not_called();gen.outline.assert_not_called();gen.generate.assert_not_called()
        check.check.assert_called_once();review.review.assert_not_called()
        self.assertEqual(result['resume_metadata']['stages_executed'],['script_fact_check'])
        self.assertEqual(result['draft']['selected_hook_id'],'hook-5')
