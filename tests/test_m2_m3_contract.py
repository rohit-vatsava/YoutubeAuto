import copy
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch
from tech_uncovered.intelligence.entry_contract import assess
from tech_uncovered.intelligence.editorial import eligible
from tech_uncovered.intelligence.models import TranscriptResult
from tech_uncovered.intelligence.extraction import extract
from tech_uncovered.intelligence.generation import DeterministicIdeaGenerator
from tech_uncovered.intelligence.clustering import cluster_stories
from tech_uncovered.intelligence.scoring import apply_readiness
from tech_uncovered.database import Database
from tech_uncovered.scripting.selection import select_ideas
from tests.test_metadata_subject_resolution import video
from tests.intelligence_helpers import config,NOW
from tests.script_helpers import selected,config as script_config


def idea(**changes):
    i=dict(canonical_subject='Orbit compiler',topic='Orbit compiler',subject_type='PRODUCT',named_entities=['Orbit compiler'],alleged_event='release',story_type='EVENT_STORY',angle_type='implications',audience_question='What changes in a workflow using Orbit compiler?',one_sentence_premise='Investigate documented workflow consequences.',story_context=[],risk_flags=[],category='RECOMMENDED FOR RESEARCH',similarity_status='CLEAR',idea_score=80)
    i.update(changes);return i


class EntryContractTests(unittest.TestCase):
    def generated(self,title):
        v=video(title);b=extract(v,TranscriptResult(),config())
        c=cluster_stories([b],[v],config(),NOW)[0]
        return DeterministicIdeaGenerator().generate(b,c)

    def test_person_never_gets_use_template(self):
        ideas=self.generated('Jensen Huang at the summit')
        self.assertTrue(ideas)
        for i in ideas:
            self.assertEqual(i.subject_type,'PERSON')
            self.assertNotIn('use Jensen Huang',i.audience_question)
            self.assertNotIn('test of Jensen Huang',i.audience_question)
            self.assertNotIn('INVALID_ANGLE_FOR_SUBJECT_TYPE',assess(i.to_dict())['m3_entry_blockers'])

    def test_company_mechanism_has_business_semantics(self):
        mechanism=next(i for i in self.generated('Anthropic researchers are quitting') if i.proposed_angle=='mechanism')
        self.assertNotIn('inside Anthropic',mechanism.audience_question)
        self.assertIn('business process',mechanism.audience_question)
        self.assertNotIn('INVALID_ANGLE_FOR_SUBJECT_TYPE',assess(mechanism.to_dict())['m3_entry_blockers'])

    def test_product_workflow_templates_allowed(self):
        self.assertTrue(assess(idea())['m3_entry_ready'])
        for i in self.generated('GPT-6 Astra released'):
            self.assertEqual(i.subject_type,'MODEL')
        implication=next(i for i in self.generated('GPT-6 Astra released') if i.proposed_angle=='implications')
        self.assertIn('workflow to use GPT-6 Astra',implication.audience_question)

    def test_persisted_malformed_wording_is_blocked(self):
        for kind,name,question in [('PERSON','Jensen Huang','How can we use Jensen Huang?'),('COMPANY','Anthropic','What happens inside Anthropic, step by step?')]:
            r=assess(idea(subject_type=kind,topic=name,canonical_subject=name,named_entities=[name],audience_question=question))
            self.assertFalse(r['m3_entry_ready']);self.assertIn('INVALID_ANGLE_FOR_SUBJECT_TYPE',r['m3_entry_blockers'])

    def test_event_missing_blocks_requirement(self):
        r=assess(idea(alleged_event=None,risk_flags=['NO_IDENTIFIABLE_EVENT']))
        self.assertFalse(r['story_requirement_satisfied']);self.assertIn('NO_IDENTIFIABLE_EVENT',r['m3_entry_blockers'])

    def test_missing_event_blocks_recommendation_without_rescoring(self):
        i=next(i for i in self.generated('GPT-6 Astra released') if i.proposed_angle=='implications')
        i.alleged_event=None;i.risk_flags=['NO_IDENTIFIABLE_EVENT'];i.source_opportunities=[{'production_fit':'GOOD'}]
        i.idea_researchability_score=99;i.idea_score=91;i.scores={'EvidenceQuality':0};i.similarity_status='CLEAR'
        before=copy.deepcopy(i.scores)
        apply_readiness(i,config())
        self.assertEqual(i.category,'BACKLOG');self.assertFalse(i.story_requirement_satisfied)
        self.assertEqual(i.scores,before);self.assertEqual(i.idea_score,91)

    def test_evergreen_semantic_requirement_passes_without_event(self):
        r=assess(idea(angle_type='explanation',story_type='EVERGREEN_TOPIC',alleged_event=None))
        self.assertTrue(r['story_requirement_satisfied']);self.assertEqual(r['story_requirement'],'EVERGREEN_OK')
        self.assertEqual(r['story_resolution_mode'],'EVERGREEN_SUBJECT')
        self.assertNotIn('NO_IDENTIFIABLE_EVENT',r['m3_entry_blockers'])
        self.assertFalse(r['m3_entry_ready'])
        self.assertEqual(r['m3_entry_blockers'],['STORY_RESOLUTION_MODE_NOT_SUPPORTED'])

    def test_evergreen_requires_concrete_technical_subject(self):
        r=assess(idea(canonical_subject=None,subject_type='UNKNOWN',named_entities=[],angle_type='explanation',story_type='EVERGREEN_TOPIC',alleged_event=None))
        self.assertFalse(r['story_requirement_satisfied']);self.assertIn('INSUFFICIENT_SUBJECT_IDENTITY',r['m3_entry_blockers'])

    def test_comparison_context_required_and_mode_not_claimed_supported(self):
        i=idea(angle_type='comparison');r=assess(i)
        self.assertFalse(r['story_requirement_satisfied']);self.assertIn('COMPARISON_CONTEXT_MISSING',r['m3_entry_blockers'])
        i['comparison_context']={'subjects':['Orbit','Nacre'],'criterion':'local storage boundary'}
        r=assess(i);self.assertTrue(r['story_requirement_satisfied'])
        self.assertEqual(r['story_resolution_mode'],'COMPARISON');self.assertFalse(r['m3_entry_ready'])

    def test_motive_speculation_excluded(self):
        r=assess(idea(audience_question='Why did the researchers resign?'))
        self.assertIn('MOTIVE_SPECULATION_REQUIRED',r['m3_entry_blockers'])

    def test_modes_and_optional_event(self):
        self.assertEqual(assess(idea(alleged_event='breach'))['story_resolution_mode'],'SECURITY_EVENT')
        self.assertEqual(assess(idea(alleged_event='lawsuit'))['story_resolution_mode'],'BUSINESS_EVENT')
        r=assess(idea(angle_type='mechanism'));self.assertEqual(r['story_requirement'],'EVENT_OPTIONAL');self.assertTrue(r['m3_entry_ready'])

    def test_default_excludes_and_debug_keeps_blocked(self):
        i=idea(alleged_event=None)
        self.assertFalse(eligible(i));self.assertTrue(eligible(i,include_backlog=True))
        i['category']='REJECTED / REVIEW REQUIRED';self.assertFalse(eligible(i,include_backlog=True))

    def test_contract_does_not_mutate_scores_or_snapshot(self):
        i=idea(scores={'DemandSignal':72});before=copy.deepcopy(i)
        self.assertEqual(assess(i),assess(i));self.assertEqual(i,before)


class ContractBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'test.db';self.db=Database(self.path)
        self.c=selected(self.db)
    def tearDown(self):self.db.close();self.tmp.cleanup()
    def block(self):
        i=self.c['idea'];i.update(alleged_event=None,story_context=[],story_type='EVERGREEN_TOPIC',angle_type='explanation')
        self.db.connection.execute('UPDATE idea_candidates SET payload=?',(json.dumps(i),));self.db.connection.commit()
        return i

    def test_readonly_preview_contract_and_backlog_labels(self):
        from tech_uncovered.cli import main
        i=self.block();before=self.path.read_bytes()
        with self.assertRaises(ValueError):select_ideas(self.db,i['intelligence_run_id'],prefer_researchable=True)
        c=select_ideas(self.db,i['intelligence_run_id'],prefer_researchable=True,include_backlog=True)[0]
        self.assertFalse(c['m3_entry_ready']);self.assertEqual(c['idea'],i)
        out=io.StringIO()
        with redirect_stdout(out):
            code=main(['script','--preview','--include-backlog','--db',str(self.path),'--intelligence-run-id',i['intelligence_run_id']])
        self.assertEqual(code,0);self.assertIn('"m3_entry_ready": false',out.getvalue());self.assertIn('STORY_RESOLUTION_MODE_NOT_SUPPORTED',out.getvalue())
        self.assertEqual(before,self.path.read_bytes())

    def test_debug_flag_cannot_trigger_paid_entry(self):
        from tech_uncovered.cli import main
        i=self.block()
        self.db.connection.execute("UPDATE intelligence_runs SET mode='offline'");self.db.connection.commit()
        with patch('dotenv.load_dotenv'),patch('tech_uncovered.scripting.cli.configuration',return_value=script_config()),patch('tech_uncovered.scripting.providers.openai_live.OpenAIModel',side_effect=AssertionError('No model')) as model,redirect_stdout(io.StringIO()) as out:
            code=main(['script','--include-backlog','--idea-id',i['idea_id'],'--intelligence-run-id',i['intelligence_run_id'],'--db',str(self.path)])
        self.assertEqual(code,1);model.assert_not_called();self.assertIn('M3 entry blocked',out.getvalue())

    def test_new_m2_run_persists_contract_fields(self):
        from tests.intelligence_helpers import seed,load
        from tech_uncovered.intelligence.pipeline import run_intelligence
        from tech_uncovered.intelligence.providers import LocalTranscriptProvider
        seed(self.db)
        result=run_intelligence(self.db,config(),NOW,radar_run_id='radar-intelligence-fiction-v1',transcript_provider=LocalTranscriptProvider(load('context.json')['videos']))
        self.assertTrue(result['ideas'])
        for i in result['ideas']:
            for field in ('subject_type','story_requirement','story_requirement_satisfied','story_resolution_mode','m3_entry_ready','m3_entry_blockers','m3_entry_contract_version'):
                self.assertIn(field,i)
            row=json.loads(self.db.connection.execute('SELECT payload FROM idea_candidates WHERE intelligence_run_id=? AND idea_id=?',(result['intelligence_run_id'],i['idea_id'])).fetchone()[0])
            self.assertEqual(row,i)

    def test_stale_persisted_ready_boolean_cannot_bypass_current_contract(self):
        i=self.block();i['m3_entry_ready']=True;i['m3_entry_blockers']=[]
        self.db.connection.execute('UPDATE idea_candidates SET payload=?',(json.dumps(i),));self.db.connection.commit()
        with self.assertRaises(ValueError):select_ideas(self.db,i['intelligence_run_id'],prefer_researchable=True)
