import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from tech_uncovered.database import Database
from tech_uncovered.intelligence.models import TranscriptResult
from tech_uncovered.intelligence.extraction import extract
from tech_uncovered.intelligence.generation import DeterministicIdeaGenerator
from tech_uncovered.intelligence.clustering import cluster_stories
from tech_uncovered.intelligence.opportunities import enrich_idea
from tech_uncovered.intelligence.pipeline import run_intelligence
from tech_uncovered.intelligence.preview import preview
from tech_uncovered.intelligence.selection import select_candidates
from tests.intelligence_helpers import load, config, NOW, seed


def candidate(**changes):
    v = dict(load('radar.json')['videos'][0])
    v.update(title='Acme Vector V12 production racks are here', named_entity_hints=['Acme', 'Vector'],
             event_hints=['production'], researchability_score=80, researchability_reasons=['named product'],
             opportunity_score=80, normalized_radar_signal=70, production_fit='GOOD',
             production_fit_reason='diagrams', commercial_value_tag='INFRASTRUCTURE',
             market_cohort='COMPUTING', source_role='vendor_official', cross_cohort_support=55,
             canonical_topics=['identifier:vector-v12'])
    v.update(changes)
    return v


class OpportunityTests(unittest.TestCase):
    def brief(self, v=None):
        return extract(v or candidate(), TranscriptResult(), config())

    def test_concrete_subject_and_provenance(self):
        b = self.brief()
        self.assertIn('Vector V12', b.canonical_subject)
        self.assertEqual(b.alleged_event, 'production')
        self.assertIn('CONTEXT_LIMITED', b.flags)
        self.assertEqual(b.factual_claims, [])
        self.assertEqual(b.field_provenance['canonical_subject']['type'], 'INFERENCE')

    def test_broad_suppression(self):
        b = self.brief(candidate(named_entity_hints=['ai'], title='AI changes everything'))
        self.assertIsNone(b.canonical_subject)
        self.assertEqual(DeterministicIdeaGenerator().generate(b, {}), [])

    def test_metadata_persisted_exactly_and_recommended(self):
        with tempfile.TemporaryDirectory() as d:
            db=Database(Path(d)/'test.db'); seed(db)
            v=candidate(); rid=load('radar.json')['run_id']
            db.connection.execute('UPDATE video_scores SET payload=? WHERE run_id=? AND video_id=?',
                                  (json.dumps(v),rid,v['video_id'])); db.connection.commit()
            result=run_intelligence(db,config(),NOW,radar_run_id=rid,top=1)
            selected=result['candidates'][0]
            for k in ('named_entity_hints','event_hints','source_role','researchability_reasons','opportunity_score'):
                self.assertEqual(selected[k],v[k])
            stored=json.loads(db.connection.execute('SELECT payload FROM idea_candidates LIMIT 1').fetchone()[0])
            self.assertEqual(stored['source_opportunities'][0]['opportunity_score'],80)
            self.assertTrue(any(i['review_status']=='RECOMMENDED_FOR_RESEARCH' for i in result['ideas']))
            self.assertTrue(all(not i['production_ready'] for i in result['ideas']))
            db.close()

    def test_ordering_and_legacy(self):
        with tempfile.TemporaryDirectory() as d:
            db=Database(Path(d)/'test.db');seed(db);rid=load('radar.json')['run_id']
            legacy=select_candidates(db,rid,20)['candidates']
            self.assertEqual(legacy, sorted(legacy,key=lambda v:(-v['velocity_adjusted_score'],-v['outlier_ratio'],v['video_id'])))
            for index,old in enumerate(legacy[:2]):
                v=dict(old);v.update(opportunity_score=90+index, researchability_score=50,production_fit='GOOD')
                db.connection.execute('UPDATE video_scores SET payload=? WHERE run_id=? AND video_id=?',(json.dumps(v),rid,v['video_id']))
            self.assertEqual(select_candidates(db,rid,1)['candidates'][0]['video_id'],legacy[1]['video_id'])
            self.assertEqual(select_candidates(db,rid,1,['velocity_adjusted_score'])['candidates'][0]['video_id'],legacy[0]['video_id'])
            db.close()

    def test_same_product_merges_but_versions_do_not(self):
        a=candidate();b=candidate(video_id='another',channel_id='other');c=candidate(video_id='third',canonical_topics=['identifier:vector-v13'])
        clusters=cluster_stories([self.brief(v) for v in [a,b,c]],[a,b,c],config(),NOW)
        self.assertEqual(len(clusters),2)
        self.assertEqual(clusters[0]['vendor_channel_count'],2)

    def test_roundup_not_merged(self):
        a=candidate();b=candidate(video_id='roundup',title='Vector V12 arrives, Acme tools and other news')
        self.assertEqual(len(cluster_stories([self.brief(a),self.brief(b)],[a,b],config(),NOW)),2)

    def test_researchability_and_propagation(self):
        v=candidate();b=self.brief(v);cluster=cluster_stories([b],[v],config(),NOW)[0]
        i=DeterministicIdeaGenerator().generate(b,cluster)[0];enrich_idea(i,[v])
        self.assertEqual(i.source_researchability_score,80)
        self.assertEqual(i.idea_researchability_score,80) # 40 source +20 subject+5 entity+15 event
        self.assertIn('Vector V12',i.audience_question)
        self.assertEqual(i.named_entities,b.named_entities)
        self.assertEqual(i.alleged_event,'production')

    def test_preview_zero_calls_and_no_mutation(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'test.db';db=Database(path);seed(db)
            run_intelligence(db,config(),NOW,radar_run_id=load('radar.json')['run_id']);db.close()
            before=path.read_bytes()
            with patch('socket.socket',side_effect=AssertionError('network')), patch('tech_uncovered.intelligence.pipeline.run_intelligence',side_effect=AssertionError('pipeline')):
                text=preview(path)
            self.assertIn('Source researchability',text)
            self.assertEqual(before,path.read_bytes())

    def test_poor_fit_not_recommended(self):
        from tech_uncovered.intelligence.scoring import apply_readiness
        v=candidate(production_fit='POOR');b=self.brief(v);cl=cluster_stories([b],[v],config(),NOW)[0]
        i=DeterministicIdeaGenerator().generate(b,cl)[0];enrich_idea(i,[v]);i.similarity_status='CLEAR';i.scores={'EvidenceQuality':0};i.idea_score=100
        apply_readiness(i,config())
        self.assertEqual(i.category,'BACKLOG')

    def test_preview_cli_bypasses_pipeline_and_providers(self):
        import argparse
        import contextlib
        import io
        from tech_uncovered.intelligence.cli import add_parser, execute
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'test.db';db=Database(path);seed(db)
            run_intelligence(db,config(),NOW,radar_run_id=load('radar.json')['run_id']);db.close()
            parser=argparse.ArgumentParser();add_parser(parser.add_subparsers())
            args=parser.parse_args(['intelligence','--preview-researchability','--db',str(path)])
            with patch('socket.socket',side_effect=AssertionError('network')), patch('tech_uncovered.intelligence.cli.run_intelligence',side_effect=AssertionError('pipeline')), patch('tech_uncovered.intelligence.cli.LocalTranscriptProvider',side_effect=AssertionError('provider')), contextlib.redirect_stdout(io.StringIO()) as out:
                self.assertEqual(execute(args),0)
            self.assertIn('Canonical subject',out.getvalue())

    def test_identical_product_different_event_not_merged(self):
        a=candidate();b=candidate(video_id='other',event_hints=['recall'])
        self.assertEqual(len(cluster_stories([self.brief(a),self.brief(b)],[a,b],config(),NOW)),2)
