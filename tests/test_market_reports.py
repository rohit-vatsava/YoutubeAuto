import contextlib
import io
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from tech_uncovered.cli import main
from tech_uncovered.database import Database
from tech_uncovered.market import enrich
from tech_uncovered.market_reports import export_market
from tests.test_market_radar import data,ROOT

class MarketReportTests(unittest.TestCase):
    def test_offline_fixture_no_network_or_models(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)
            with patch('tech_uncovered.youtube.urlopen',side_effect=AssertionError('Network')),patch('tech_uncovered.scripting.providers.openai_live.OpenAIModel.request',side_effect=AssertionError('Model')),contextlib.redirect_stdout(io.StringIO()):
                code=main(['research','--fixture',str(ROOT/'tests/fixtures/market_radar.json'),'--db',str(path/'test.db'),'--reports-dir',str(path/'reports'),'--opportunities'])
            self.assertEqual(code,0)
            self.assertTrue((path/'reports/cohorts.md').exists());self.assertTrue((path/'reports/outliers.json').exists())
            result=json.loads((path/'reports/opportunities.json').read_text());self.assertEqual(len(result['cross_cohort_signals']),1)
            c=sqlite3.connect(path/'test.db');self.assertEqual(c.execute('select count(*) from radar_opportunities').fetchone()[0],36);c.close()
    def test_cohort_filter_scope(self):
        with tempfile.TemporaryDirectory() as tmp,contextlib.redirect_stdout(io.StringIO()):
            path=Path(tmp)
            code=main(['research','--fixture',str(ROOT/'tests/fixtures/market_radar.json'),'--cohort','AI_FRONTIER','--db',str(path/'test.db'),'--reports-dir',str(path/'reports')])
            r=json.loads((path/'reports/opportunities.json').read_text());self.assertEqual(code,0);self.assertEqual(r['cross_cohort_signals'],[])
            self.assertEqual(r['metadata']['market_config']['scope_cohorts'],['AI_FRONTIER'])
    def test_report_vendor_counts_and_csv_safety(self):
        r=enrich(*data());r['opportunities'][0]['title']='=HYPERLINK("bad")'
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);export_market(r,p)
            self.assertIn("'=HYPERLINK",(p/'opportunities.csv').read_text());self.assertIn('2 independent/media channels + 1 vendor',(p/'cohorts.md').read_text())
    def test_history_payload_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            db=Database(Path(tmp)/'test.db');old=data()[0];db.save_run(old)
            before=[tuple(r) for r in db.connection.execute('select * from video_scores order by video_id')]
            fresh=enrich(*data());db.save_run(fresh)
            self.assertEqual(before,[tuple(r) for r in db.connection.execute('select * from video_scores where run_id=? order by video_id',(old['run_id'],))]);db.close()
    def test_v4_migration_rollback(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'old.db';c=sqlite3.connect(path)
            for file in ('schema.sql','migrations/002_intelligence.sql','migrations/003_research_scripts.sql'):c.executescript((ROOT/'tech_uncovered'/file).read_text())
            c.execute('PRAGMA user_version=3');c.close();original=Path.read_text
            def broken(p,*a,**kw):return 'CREATE TABLE rollback_probe(x); INVALID SQL;' if p.name=='004_market_radar.sql' else original(p,*a,**kw)
            with patch.object(Path,'read_text',broken):
                with self.assertRaises(sqlite3.Error):Database(path)
            c=sqlite3.connect(path);self.assertEqual(c.execute('PRAGMA user_version').fetchone()[0],3)
            self.assertEqual(c.execute("SELECT count(*) FROM sqlite_master WHERE name='rollback_probe'").fetchone()[0],0);c.close()
    def test_disabled_channels_excluded(self):
        with tempfile.TemporaryDirectory() as tmp,contextlib.redirect_stdout(io.StringIO()):
            p=Path(tmp);fixture=json.loads((ROOT/'tests/fixtures/market_radar.json').read_text());fixture['competitor_config']['channels'][0]['enabled']=False
            (p/'fixture.json').write_text(json.dumps(fixture));code=main(['research','--fixture',str(p/'fixture.json'),'--db',str(p/'test.db'),'--reports-dir',str(p/'reports')])
            r=json.loads((p/'reports/outliers.json').read_text());self.assertEqual(code,0);self.assertEqual(len(r['videos']),24)
