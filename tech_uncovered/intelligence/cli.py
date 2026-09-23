import json
import sqlite3
from pathlib import Path

from ..database import Database
from ..settings import utcnow, parse_time
from .models import digest
from .pipeline import run_intelligence
from .providers import LocalTranscriptProvider, ManualResearchProvider
from .reports import export, expire_reports, summary
from .storage import expire

ROOT = Path(__file__).resolve().parents[2]


def add_parser(subparsers):
    p = subparsers.add_parser('intelligence', help='Module 2: evidence-labelled original content opportunities')
    p.add_argument('--preview-researchability', action='store_true', help='Read-only preview of latest persisted Intelligence run; zero network calls')
    p.add_argument('--top', type=int, help='Intake limit; defaults to configured intake_limit (30)')
    p.add_argument('--offline', action='store_true', help='Require providers to make no network calls; all V1 providers are local')
    p.add_argument('--refresh-context', action='store_true', help='Retrieve context anew into a new immutable run')
    p.add_argument('--run-id', help='Exact Radar run ID; no silent fallback')
    p.add_argument('--fixture', type=Path, help='Explicitly synthetic Radar export; isolated demo database by default')
    p.add_argument('--db', type=Path)
    p.add_argument('--reports-dir', type=Path)
    p.add_argument('--context-file', type=Path)
    p.add_argument('--evidence-file', type=Path)
    p.add_argument('--config', type=Path, default=ROOT/'config/intelligence.json')


def seed_fixture(db, result):
    if result.get('metadata',{}).get('mode') != 'synthetic' or result.get('schema_version') != '1.0':
        raise ValueError('Only explicitly synthetic Radar 1.0 fixtures can be imported')
    run_id = result['run_id']
    old = db.connection.execute('SELECT payload FROM research_runs WHERE run_id=?',(run_id,)).fetchone()
    if old:
        records = [json.loads(r[0]) for r in db.connection.execute('SELECT payload FROM video_scores WHERE run_id=?',(run_id,))]
        if (digest(sorted(records,key=lambda r:r['video_id'])) != digest(sorted(result['videos'],key=lambda r:r['video_id']))
                or json.loads(old[0]) != result['metadata']):
            raise ValueError('Fixture run ID already exists with different data')
        return
    db.save_run(result)


def execute(args):
    db = None
    try:
        if getattr(args, 'preview_researchability', False):
            from .preview import preview
            print(preview(args.db or ROOT/'data/intelligence.sqlite3', args.run_id, args.top or 20))
            return 0
        fixture = json.loads(args.fixture.read_text()) if args.fixture else None
        if fixture and args.run_id and args.run_id != fixture['run_id']:
            raise ValueError('--run-id must match the supplied fixture')
        path = args.db or ROOT/'data'/('intelligence-demo.sqlite3' if fixture else 'intelligence.sqlite3')
        if not fixture and not path.exists():
            raise ValueError('Radar database not found; run research first or use --fixture')
        config = json.loads(args.config.read_text())
        transcript = LocalTranscriptProvider(json.loads(args.context_file.read_text()).get('videos',{})) if args.context_file else None
        research = ManualResearchProvider(json.loads(args.evidence_file.read_text())) if args.evidence_file else None
        reports = args.reports_dir or ROOT/'reports'/('intelligence-demo' if fixture else 'intelligence')
        now = parse_time(fixture['generated_at']) if fixture else utcnow()
        db = Database(path)
        if fixture:
            # Never import fictional rows into a database that contains live Radar runs.
            if any(json.loads(r[0]).get('mode') == 'live' for r in db.connection.execute('SELECT payload FROM research_runs')):
                raise ValueError('Refusing to mix synthetic fixture with live Radar database')
            seed_fixture(db,fixture)
        expire(db,now)
        all_expired = [r[0] for r in db.connection.execute('SELECT intelligence_run_id FROM intelligence_runs WHERE expired=1')]
        expire_reports(reports,all_expired)
        result = run_intelligence(db,config,now,radar_run_id=fixture['run_id'] if fixture else args.run_id,
                                  top=args.top,offline=args.offline or bool(fixture),refresh=args.refresh_context,
                                  transcript_provider=transcript,research_provider=research)
        export(result,reports)
        print(summary(result,reports))
        return 2 if result['metadata']['partial_failures'] else 0
    except (ValueError,KeyError,TypeError,OSError,sqlite3.Error) as exc:
        print(f'Intelligence error: {exc}')
        return 1
    finally:
        if db:
            db.close()
