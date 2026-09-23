import unittest
from tech_uncovered.intelligence.providers import LocalTranscriptProvider, UnavailableTranscriptProvider, ManualResearchProvider, NoOpResearchProvider
from tech_uncovered.intelligence.extraction import extract,ground
from tests.intelligence_helpers import load,config,NOW


class ContextTests(unittest.TestCase):
    def setUp(self):
        self.candidate=next(v for v in load('radar.json')['videos'] if v['video_id']=='fiction-0-10')
        self.kwargs=dict(offline=True,refresh=False,now=NOW.isoformat())

    def test_unavailable_metadata_limited(self):
        transcript=UnavailableTranscriptProvider().retrieve(self.candidate,**self.kwargs)
        self.assertEqual(transcript.transcript_status,'UNAVAILABLE')
        self.assertIsNone(transcript.text)
        brief=extract(self.candidate,transcript,config())
        self.assertIn('CONTEXT_LIMITED',brief.flags)
        self.assertIsNone(brief.core_event)
        self.assertTrue(all(c['status']=='UNVERIFIED' for c in brief.uncertain_claims))

    def test_supplied_transcript_and_manual_grounding(self):
        provider=LocalTranscriptProvider(load('context.json')['videos'])
        transcript=provider.retrieve(self.candidate,**self.kwargs)
        self.assertEqual(transcript.transcript_status,'AVAILABLE')
        self.assertTrue(transcript.content_hash)
        brief=extract(self.candidate,transcript,config())
        self.assertEqual(brief.factual_claims,[])
        result=ManualResearchProvider(load('evidence.json')).research(brief,**self.kwargs)
        ground(brief,result)
        self.assertEqual(brief.factual_claims[0]['status'],'VERIFIED')
        self.assertEqual(brief.factual_claims[0]['statement_type'],'FACT')
        self.assertNotIn('CONTEXT_LIMITED',brief.flags)

    def test_link_alone_does_not_verify(self):
        brief=extract(self.candidate,LocalTranscriptProvider(load('context.json')['videos']).retrieve(self.candidate,**self.kwargs),config())
        evidence=load('evidence.json')
        evidence['sources']['evidence-0'].pop('excerpt')
        ground(brief,ManualResearchProvider(evidence).research(brief,**self.kwargs))
        self.assertEqual(brief.factual_claims,[])
        self.assertEqual(brief.uncertain_claims[0]['status'],'UNVERIFIED')

    def test_claim_text_must_match(self):
        brief=extract(self.candidate,LocalTranscriptProvider(load('context.json')['videos']).retrieve(self.candidate,**self.kwargs),config())
        evidence=load('evidence.json'); evidence['assessments']['claim-0']['claim_text']='Different claim'
        ground(brief,ManualResearchProvider(evidence).research(brief,**self.kwargs))
        self.assertEqual(brief.factual_claims,[])

    def test_rights_provenance_required(self):
        provider=LocalTranscriptProvider({self.candidate['video_id']:{'text':'Some text'}})
        with self.assertRaises(ValueError):provider.retrieve(self.candidate,**self.kwargs)

    def test_transcript_alone_not_understood(self):
        entry={'text':'A claim in a transcript','source':'user','provenance_note':'Permission supplied'}
        t=LocalTranscriptProvider({self.candidate['video_id']:entry}).retrieve(self.candidate,**self.kwargs)
        brief=extract(self.candidate,t,config())
        self.assertIn('CONTEXT_LIMITED',brief.flags)
        self.assertIn('TRANSCRIPT_REQUIRES_CONTEXT_REVIEW',brief.flags)

    def test_disputed_evidence_remains_uncertain(self):
        brief=extract(self.candidate,LocalTranscriptProvider(load('context.json')['videos']).retrieve(self.candidate,**self.kwargs),config())
        evidence=load('evidence.json'); evidence['sources']['evidence-0']['relation']='CONTRADICTS'
        ground(brief,ManualResearchProvider(evidence).research(brief,**self.kwargs))
        self.assertEqual(brief.uncertain_claims[0]['status'],'DISPUTED')

    def test_provider_cannot_verify_without_evidence(self):
        from tech_uncovered.intelligence.models import ResearchResult
        brief=extract(self.candidate,LocalTranscriptProvider(load('context.json')['videos']).retrieve(self.candidate,**self.kwargs),config())
        claim=brief.uncertain_claims[0]
        ground(brief,ResearchResult(assessments={claim['claim_id']:{'status':'VERIFIED'}}))
        self.assertEqual(brief.factual_claims,[])
        self.assertEqual(brief.uncertain_claims[0]['status'],'UNVERIFIED')
