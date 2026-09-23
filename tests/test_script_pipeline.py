import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from tech_uncovered.database import Database
from tech_uncovered.cli import main
from tech_uncovered.scripting.selection import select_ideas
from tech_uncovered.scripting.costs import ProviderFailure
from tech_uncovered.scripting.providers.fixtures import FixtureScriptGenerator,FixtureResearchProvider
from tests.script_helpers import ROOT,fixture,selected,execute,config


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'test.db';self.db=Database(self.path);self.choice=selected(self.db)
    def tearDown(self):self.db.close();self.tmp.cleanup()
    def run_fixture(self,**kw):return execute(self.db,choice=self.choice,**kw)
    def test_exact_run_no_fallback(self):
        with self.assertRaises(ValueError):select_ideas(self.db,'missing')
    def test_explicit_idea_no_fallback(self):
        with self.assertRaises(ValueError):select_ideas(self.db,self.choice['intelligence_run_id'],'missing')
    def test_rejected_idea_not_selected(self):
        idea=self.choice['idea'];idea['similarity_status']='REJECT'
        with self.db.connection:self.db.connection.execute('UPDATE idea_candidates SET payload=?',(json.dumps(idea),))
        with self.assertRaises(ValueError):select_ideas(self.db,self.choice['intelligence_run_id'])
    def test_missing_provenance_rejected(self):
        with self.db.connection:self.db.connection.execute('DELETE FROM intelligence_candidates')
        with self.assertRaises(ValueError):select_ideas(self.db,self.choice['intelligence_run_id'])
    def test_mutated_provenance_rejected(self):
        idea=self.choice['idea'];idea['radar_run_id']='wrong'
        with self.db.connection:self.db.connection.execute('UPDATE idea_candidates SET payload=?',(json.dumps(idea),))
        with self.assertRaises(ValueError):select_ideas(self.db,self.choice['intelligence_run_id'])
    def test_insufficient_evidence_no_generator_calls(self):
        bundle=fixture();bundle['packet']['source_assessments']=[]
        gen=FixtureScriptGenerator(bundle)
        with patch.object(gen,'refine',side_effect=AssertionError('Must not generate')) as call:
            r=self.run_fixture(bundle=bundle,generator=gen)
            self.assertEqual(r['readiness']['status'],'RESEARCH_REQUIRED');self.assertIsNone(r['draft']);call.assert_not_called()
    def test_contradicted_no_script(self):
        r=self.run_fixture(bundle=fixture('contradictory_research.json'));self.assertEqual(r['readiness']['status'],'REJECTED');self.assertIsNone(r['draft'])
    def test_provider_failure_no_fabricated_packet(self):
        provider=FixtureResearchProvider(fixture())
        with patch.object(provider,'search',side_effect=ProviderFailure('unavailable')):
            r=self.run_fixture(provider=provider)
        self.assertIsNone(r['packet']);self.assertEqual(r['readiness']['status'],'RESEARCH_REQUIRED');self.assertTrue(r['failures'])
    def test_packet_committed_before_generation(self):
        generator=FixtureScriptGenerator(fixture());original=generator.refine
        def inspect(packet,choice):
            with sqlite3.connect(self.path) as c:self.assertEqual(c.execute('SELECT count(*) FROM research_packets').fetchone()[0],1)
            return original(packet,choice)
        with patch.object(generator,'refine',side_effect=inspect):self.run_fixture(generator=generator)
    def test_generation_failure_preserves_research(self):
        generator=FixtureScriptGenerator(fixture())
        with patch.object(generator,'generate',side_effect=ProviderFailure('failed')):r=self.run_fixture(generator=generator)
        self.assertEqual(r['packet']['research_status'],'SUFFICIENT');self.assertIsNone(r['draft'])
        self.assertEqual(self.db.connection.execute('SELECT count(*) FROM research_packets').fetchone()[0],1)
    def test_append_only_and_unique_runs(self):
        a=self.run_fixture();b=self.run_fixture();self.assertNotEqual(a['script_id'],b['script_id'])
        self.assertEqual(self.db.connection.execute('SELECT count(*) FROM script_drafts').fetchone()[0],2)
        with self.assertRaises(sqlite3.IntegrityError):self.db.connection.execute("UPDATE script_drafts SET payload='{}'")
    def test_one_bounded_editorial_revision(self):
        bundle=fixture();bundle['quality']['spoken_naturalness']['flags']=['NEEDS_READ_THROUGH']
        r=self.run_fixture(bundle=bundle);self.assertEqual(len(r['revisions']),2);self.assertEqual(r['readiness']['status'],'EDITORIAL_REVIEW')
        self.assertEqual(self.db.connection.execute('SELECT count(*) FROM script_drafts').fetchone()[0],2)
    def test_offline_no_network_and_zero_billing(self):
        with patch('socket.create_connection',side_effect=AssertionError('Network forbidden')),patch('urllib.request.urlopen',side_effect=AssertionError('Network forbidden')):r=self.run_fixture()
        self.assertEqual(r['cost']['model_calls'],0);self.assertEqual(r['cost']['estimated_model_cost_usd'],0);self.assertGreaterEqual(r['cost']['total_research_seconds'],0)
    def test_offline_cli_artifacts(self):
        reports=Path(self.tmp.name)/'reports'
        with patch('builtins.print'),patch('socket.create_connection',side_effect=AssertionError('No network')):
            code=main(['script','--offline','--research-file',str(ROOT/'fixtures/scripts/sufficient_research.json'),'--db',str(self.path),'--reports-dir',str(reports)])
        self.assertEqual(code,0);self.assertIn('FICTIONAL', (reports/'latest.md').read_text())
        folder=next(p for p in reports.iterdir() if p.is_dir())
        for name in ('idea','research_plan','research_packet','sources','claims','angle','hooks','script','fact_check','quality_review','costs'):self.assertTrue((folder/(name+'.json')).exists())
    def test_offline_requires_fixture(self):
        with patch('builtins.print'):self.assertEqual(main(['script','--offline']),1)
    def test_v3_migration_rollback(self):
        path=Path(self.tmp.name)/'v2.db';conn=sqlite3.connect(path)
        conn.executescript((ROOT/'tech_uncovered/schema.sql').read_text());conn.executescript((ROOT/'tech_uncovered/migrations/002_intelligence.sql').read_text());conn.execute('PRAGMA user_version=2');conn.close()
        original=Path.read_text
        def broken(path,*args,**kw):
            return 'CREATE TABLE should_rollback(x); INVALID SQL;' if path.name=='003_research_scripts.sql' else original(path,*args,**kw)
        with patch.object(Path,'read_text',broken):
            with self.assertRaises(sqlite3.Error):Database(path)
        conn=sqlite3.connect(path);self.assertEqual(conn.execute('PRAGMA user_version').fetchone()[0],2)
        self.assertFalse(conn.execute("SELECT name FROM sqlite_master WHERE name='should_rollback'").fetchall());conn.close()
    def test_retention_expires_module3_derived_payloads(self):
        from datetime import datetime,timezone
        from tech_uncovered.scripting.storage import expire
        r=self.run_fixture()
        with self.db.connection:self.db.connection.execute("UPDATE research_runs_v3 SET mode='live',source_observed_at='2026-01-01T00:00:00+00:00'")
        expire(self.db,datetime(2026,9,20,tzinfo=timezone.utc))
        self.assertEqual(self.db.connection.execute('SELECT count(*) FROM script_drafts').fetchone()[0],0)
        self.assertEqual(self.db.connection.execute('SELECT status FROM script_runs').fetchone()[0],'EXPIRED')
        self.assertEqual(self.db.connection.execute('SELECT selected_snapshot FROM research_runs_v3').fetchone()[0],'{}')
    def test_success_cache_requires_same_config_and_provenance(self):
        from tech_uncovered.scripting.storage import cached_result
        r=self.run_fixture()
        with self.db.connection:self.db.connection.execute("UPDATE research_runs_v3 SET mode='live'")
        self.assertEqual(cached_result(self.db,self.choice,config(),fixture()['as_of']),r['script_id'])
        cfg=config();cfg['quality_threshold']=90
        self.assertIsNone(cached_result(self.db,self.choice,cfg,fixture()['as_of']))
        choice=dict(self.choice,intelligence_run_id='other-run')
        self.assertIsNone(cached_result(self.db,choice,config(),fixture()['as_of']))
