import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from tech_uncovered.database import Database
from tests.intelligence_helpers import ROOT


class MigrationTests(unittest.TestCase):
    def legacy(self,path):
        c=sqlite3.connect(path)
        c.executescript((ROOT/'tech_uncovered/schema.sql').read_text())
        c.execute('INSERT INTO research_runs VALUES (?,?,?)',('legacy','2026-09-20T00:00:00+00:00','{"mode":"live"}'))
        c.commit();c.close()

    def test_migration_preserves_records_and_backup(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'old.db';self.legacy(path)
            db=Database(path)
            self.assertEqual(db.connection.execute('PRAGMA user_version').fetchone()[0],4)
            row=dict(db.connection.execute('SELECT * FROM research_runs').fetchone())
            self.assertEqual(row['run_id'],'legacy');self.assertIsNone(row['created_at'])
            db.close()
            self.assertTrue(Path(str(path)+'.pre-v2.bak').exists())
            db=Database(path)
            self.assertEqual(db.connection.execute('SELECT count(*) FROM research_runs').fetchone()[0],1)
            self.assertEqual(db.connection.execute('PRAGMA foreign_keys').fetchone()[0],1)
            db.close()

    def test_failed_migration_rolls_back(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'old.db';self.legacy(path)
            original=Path.read_text
            def broken(p,*a,**kw):
                if p.name=='002_intelligence.sql':return 'ALTER TABLE research_runs ADD COLUMN test_column TEXT; INVALID SQL;'
                return original(p,*a,**kw)
            with patch.object(Path,'read_text',broken):
                with self.assertRaises(sqlite3.Error):Database(path)
            c=sqlite3.connect(path)
            self.assertEqual(c.execute('PRAGMA user_version').fetchone()[0],1)
            self.assertNotIn('test_column',[r[1] for r in c.execute('PRAGMA table_info(research_runs)')])
            c.close()

    def test_newer_schema_rejected_without_downgrade(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'new.db';self.legacy(path)
            c=sqlite3.connect(path);c.execute('PRAGMA user_version=99');c.close()
            with self.assertRaises(ValueError):Database(path)
            c=sqlite3.connect(path);self.assertEqual(c.execute('PRAGMA user_version').fetchone()[0],99);c.close()
