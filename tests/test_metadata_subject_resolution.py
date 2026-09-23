import copy
import unittest
from tech_uncovered.intelligence.subject_resolution import MetadataSubjectResolver
from tech_uncovered.intelligence.extraction import extract
from tech_uncovered.intelligence.generation import DeterministicIdeaGenerator
from tech_uncovered.intelligence.models import TranscriptResult
from tech_uncovered.intelligence.clustering import cluster_stories
from tech_uncovered.intelligence.opportunities import enrich_idea
from tests.intelligence_helpers import config, NOW
from tests.test_intelligence_opportunities import candidate


def video(title, **kw):
    return candidate(title=title, named_entity_hints=[], event_hints=[],canonical_topics=kw.pop('canonical_topics',[]),
                     market_cohort=kw.pop('market_cohort','DEV_SOFTWARE'), **kw)


class MetadataSubjectTests(unittest.TestCase):
    def resolve(self,title,**kw):return MetadataSubjectResolver().resolve(video(title,**kw))
    def brief(self,title,**kw):return extract(video(title,**kw),TranscriptResult(),config())

    def test_meta_legal_no_case_or_outcome_invented(self):
        r=self.resolve('Meta’s Legal Troubles Are Worse than You Think')
        self.assertEqual(r['canonical_subject'],'Meta');self.assertEqual(r['subject_type'],'COMPANY')
        self.assertEqual(r['event_or_change'],'legal troubles');self.assertEqual(r['story_type'],'EVENT_STORY')
        self.assertEqual(r['named_entities'],['Meta']);self.assertIn('Specific case and outcome are unnamed',r['unresolved_reasons'])

    def test_apple_no_phone_model_invented(self):
        r=self.resolve('Before the Foldable, Apple Copied This Phone')
        self.assertEqual(r['canonical_subject'],'Apple');self.assertEqual(r['named_entities'],['Apple'])
        self.assertEqual(r['event_or_change'],'historical product/design comparison')
        self.assertEqual(r['product_or_project'],[]);self.assertEqual(r['version_or_generation'],[])

    def test_product_extraction(self):
        r=self.resolve('VS Code explained')
        self.assertEqual(r['product_or_project'],['VS Code']);self.assertEqual(r['subject_type'],'PRODUCT')
        self.assertEqual(r['story_type'],'EVERGREEN_TOPIC')

    def test_version_and_temporal_marker(self):
        r=self.resolve('GPT-6 Astra is here in 2026')
        self.assertIn('GPT-6 Astra',r['version_or_generation']);self.assertIn('2026',r['temporal_marker'])
        self.assertEqual(r['event_or_change'],'release/announcement');self.assertEqual(r['subject_type'],'MODEL')

    def test_cve_extraction_does_not_invent_affected_product(self):
        r=self.resolve('CVE-2026-12345 explained')
        self.assertEqual(r['canonical_subject'],'CVE-2026-12345');self.assertEqual(r['subject_type'],'SECURITY_EVENT')
        self.assertEqual(r['named_entities'],['CVE-2026-12345'])

    def test_generic_programming_is_not_a_news_event(self):
        r=self.resolve('The End of Programming')
        self.assertEqual(r['canonical_subject'],'programming');self.assertEqual(r['subject_type'],'DEVELOPER_TOPIC')
        self.assertEqual(r['story_type'],'EVERGREEN_TOPIC');self.assertIsNone(r['event_or_change'])
        self.assertEqual(r['product_or_project'],[]);self.assertEqual(r['version_or_generation'],[])
        self.assertEqual(r['confidence'],'MEDIUM')

    def test_engineer_channel_context_disambiguates_not_subject(self):
        r=self.resolve('How to be a good engineer in 2026',channel='The PrimeTime')
        self.assertEqual(r['canonical_subject'],'software engineering');self.assertNotIn('The PrimeTime',r['named_entities'])
        self.assertIsNone(r['event_or_change'])
        self.assertEqual(self.resolve('How to be a good engineer in 2026',market_cohort='UNKNOWN')['story_type'],'INSUFFICIENT_CONTEXT')

    def test_no_channel_as_subject(self):
        r=self.resolve("you can't be serious",channel='NVIDIA',source_role='vendor_official')
        self.assertIsNone(r['canonical_subject']);self.assertEqual(r['channel_context']['source_owner'],'NVIDIA')
        self.assertEqual(r['story_context_status'],'INSUFFICIENT_CONTEXT')

    def test_ambiguous_event_without_subject(self):
        r=self.resolve('It just launched!')
        self.assertIsNone(r['canonical_subject']);self.assertIsNone(r['event_or_change'])
        self.assertEqual(r['confidence'],'LOW')

    def test_alias_normalization(self):
        for first,second,name in [('AMD','Advanced Micro Devices','AMD'),('Nvidia','NVIDIA','NVIDIA'),('Github','GitHub','GitHub'),('Meta Platforms','Meta','Meta')]:
            a=self.resolve(first+' announced an update');b=self.resolve(second+' announced an update')
            self.assertEqual(a['canonical_subject'],name);self.assertEqual(a['canonical_subject'],b['canonical_subject'])
        self.assertNotIn('Meta',self.resolve('Meta-analysis explained')['named_entities'])

    def test_missing_business_actor_stays_unresolved(self):
        r=self.resolve('How to lose $35 Billion Dollars Betting on AI',market_cohort='TECH_BUSINESS',channel='ColdFusion')
        self.assertEqual(r['story_type'],'INSUFFICIENT_CONTEXT');self.assertIsNone(r['canonical_subject'])
        self.assertIsNone(r['event_or_change'])

    def test_exxon_does_not_invent_an_incident(self):
        r=self.resolve('Exxon’s Office Fling',market_cohort='TECH_BUSINESS')
        self.assertEqual(r['canonical_subject'],'Exxon');self.assertIsNone(r['event_or_change'])
        self.assertEqual(r['story_type'],'INSUFFICIENT_CONTEXT')

    def test_gpu_identifiers_no_manufacturer_guesses(self):
        r=self.resolve('The GPU Madness Has Come To This - 9070 XT vs. 5060 Ti 16GB',market_cohort='HARDWARE_CHIPS')
        self.assertEqual(set(r['version_or_generation']),{'9070 XT','5060 Ti 16GB'})
        self.assertNotIn('AMD',r['named_entities']);self.assertNotIn('NVIDIA',r['named_entities'])
        self.assertEqual(r['event_or_change'],'comparison')

    def test_evergreen_templates_no_why_now(self):
        b=self.brief('The End of Programming');v=video('The End of Programming')
        c=cluster_stories([b],[v],config(),NOW)[0];ideas=DeterministicIdeaGenerator().generate(b,c)
        self.assertEqual({i.proposed_angle for i in ideas},{'explanation','practical lesson','misconception','mechanism'})
        self.assertTrue(all(i.alleged_event is None and 'Evergreen educational' in i.why_now for i in ideas))

    def test_unresolved_does_not_generate_event_angles(self):
        self.assertEqual(DeterministicIdeaGenerator().generate(self.brief('Exxon’s Office Fling'),{}),[])

    def test_company_event_cluster_and_evergreen_separation(self):
        vs=[video('Meta’s Legal Troubles Are Worse than You Think',video_id='a'),
            video('Meta Platforms legal troubles',video_id='b'),
            video('The End of Programming',video_id='c'),video('VS Code released',video_id='d')]
        bs=[extract(v,TranscriptResult(),config()) for v in vs]
        groups=cluster_stories(bs,vs,config(),NOW)
        self.assertEqual(len(groups),3)
        self.assertIn(['a','b'],[g['supporting_video_ids'] for g in groups])

    def test_researchability_formula_and_source_scores_preserved(self):
        v=video('Meta legal troubles');before=copy.deepcopy(v)
        b=extract(v,TranscriptResult(),config());c=cluster_stories([b],[v],config(),NOW)[0]
        idea=DeterministicIdeaGenerator().generate(b,c)[0];enrich_idea(idea,[v])
        self.assertEqual(idea.idea_researchability_score,.5*v['researchability_score']+20+5+15)
        self.assertEqual(v,before)
        self.assertEqual(idea.source_opportunities[0]['opportunity_score'],v['opportunity_score'])
        self.assertEqual(b.confidence,.2);self.assertEqual(b.factual_claims,[])

    def test_event_comparison_not_invented(self):
        b=self.brief('Meta legal troubles');c=cluster_stories([b],[video('Meta legal troubles')],config(),NOW)[0]
        self.assertNotIn('comparison',{i.proposed_angle for i in DeterministicIdeaGenerator().generate(b,c)})

    def test_unanchored_version_not_a_story(self):
        self.assertEqual(self.resolve('V2 is here')['story_context_status'],'INSUFFICIENT_CONTEXT')

    def test_educational_list_is_not_a_news_roundup(self):
        r=self.resolve('Essential Skills for Becoming an AI Engineer: RAG, AI Agents, & More',market_cohort='AI_TOOLS_SOFTWARE')
        self.assertEqual(r['story_type'],'EVERGREEN_TOPIC');self.assertIsNone(r['event_or_change'])

    def test_resolution_deterministic_and_local_description_not_assumed(self):
        v=video('The End of Programming');v['description']='A claim about an unnamed product launch'
        a=MetadataSubjectResolver().resolve(v);b=MetadataSubjectResolver().resolve(v)
        self.assertEqual(a,b);self.assertIsNone(a['event_or_change'])

    def test_product_evergreen_grouping_ignores_optional_company_label(self):
        vs=[video('OpenAI GPT-6 Astra explained',video_id='a'),video('GPT-6 Astra explained',video_id='b')]
        bs=[extract(v,TranscriptResult(),config()) for v in vs]
        groups=cluster_stories(bs,vs,config(),NOW)
        self.assertEqual(len(groups),1)
        ideas=[DeterministicIdeaGenerator().generate(b,groups[0]) for b in bs]
        self.assertEqual(ideas[0][0].topic,ideas[1][0].topic)

    def test_resolved_event_separates_release_from_breach(self):
        vs=[video('Windows 12 released',video_id='a',canonical_topics=['identifier:windows-12']),video('Windows 12 breach',video_id='b',canonical_topics=['identifier:windows-12'])]
        bs=[extract(v,TranscriptResult(),config()) for v in vs]
        self.assertEqual(len(cluster_stories(bs,vs,config(),NOW)),2)

    def test_additional_title_patterns(self):
        cases=[('AMD vs NVIDIA','comparison','CONCRETE_STORY'),('ChatGPT just changed','unspecified change','CONCRETE_STORY'),('Why Linux matters',None,'EVERGREEN_TOPIC'),('What happened to Exxon',None,'INSUFFICIENT_CONTEXT'),('Another Great Day of Software Engineering #ad',None,'EVERGREEN_TOPIC')]
        for title,event,status in cases:
            with self.subTest(title=title):
                r=self.resolve(title);self.assertEqual(r['event_or_change'],event);self.assertEqual(r['story_context_status'],status)

    def test_resolver_does_not_change_intake_order(self):
        import tempfile
        from pathlib import Path
        from tech_uncovered.database import Database
        from tech_uncovered.intelligence.selection import select_candidates
        from tests.intelligence_helpers import seed
        with tempfile.TemporaryDirectory() as tmp:
            db=Database(Path(tmp)/'test.db');seed(db)
            before=select_candidates(db,'radar-intelligence-fiction-v1')
            for v in before['candidates']:MetadataSubjectResolver().resolve(v)
            self.assertEqual(before,select_candidates(db,'radar-intelligence-fiction-v1'))
            db.close()

    def test_resolution_metadata_does_not_change_preview_diversity(self):
        from tests.test_editorial_diversity import choice
        from tech_uncovered.intelligence.editorial import story_first
        rows=[choice(1,'a','AF',90),choice(2,'a','AF',89),choice(3,'b','DEV',85)]
        before=copy.deepcopy(rows)
        for c in rows:c['idea']['metadata_subject_resolution']=self.resolve('The End of Programming')
        self.assertEqual([c['idea']['idea_id'] for c in story_first(rows,3)],[c['idea']['idea_id'] for c in story_first(before,3)])
        self.assertEqual([c['idea']['idea_score'] for c in rows],[c['idea']['idea_score'] for c in before])

    def test_idea_weights_unchanged(self):
        self.assertEqual(config()['weights'],{'DemandSignal':.22,'Freshness':.15,'Originality':.15,'AudienceFit':.15,'ProductionFit':.1,'EvidenceQuality':.1,'Expandability':.08,'SaturationRisk':.05})

    def test_unanchored_radar_hint_cannot_invent_an_event(self):
        v=video('Meta explained');v['event_hints']=['acquisition']
        r=MetadataSubjectResolver().resolve(v)
        self.assertIsNone(r['event_or_change']);self.assertEqual(r['story_type'],'EVERGREEN_TOPIC')
