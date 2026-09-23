import argparse
import json
import os
from pathlib import Path

from .database import Database
from .reports import export, summary
from .research import analyze, collect
from .settings import Settings, parse_time, utcnow
from .topics import DictionaryTopicClassifier
from .youtube import Usage, YouTubeClient

ROOT = Path(__file__).resolve().parent.parent


def main(argv=None):
    parser = argparse.ArgumentParser(description="Tech Uncovered — Module 1: Radar")
    sub = parser.add_subparsers(dest="command", required=True)
    from .intelligence.cli import add_parser, execute
    add_parser(sub)
    from .scripting.cli import add_parser as add_script_parser, execute as execute_script
    add_script_parser(sub)
    research = sub.add_parser("research", help="Collect competitor metadata and rank outliers")
    mode = research.add_mutually_exclusive_group()
    mode.add_argument("--offline", action="store_true", help="Analyze stored observations without network")
    mode.add_argument("--fixture", type=Path, help="Analyze a synthetic JSON fixture without network")
    research.add_argument("--refresh", action="store_true", help="Bypass live API cache")
    research.add_argument("--db", type=Path)
    research.add_argument("--reports-dir", type=Path)
    research.add_argument("--channels", type=Path, default=ROOT / "config/channels.json")
    research.add_argument("--themes", type=Path, default=ROOT / "config/themes.json")
    research.add_argument("--max-uploads", type=int)
    research.add_argument("--lookback-days", type=int)
    research.add_argument("--cohort")
    research.add_argument("--opportunities",action="store_true")
    research.add_argument("--resolve-channels",action="store_true")
    research.add_argument("--cohorts",type=Path,default=ROOT/"config/cohorts.json")
    research.add_argument("--radar-rules",type=Path,default=ROOT/"config/radar_rules.json")
    research.add_argument("--min-sample", type=int, default=10)
    research.add_argument("--request-budget", type=int, default=100)
    args = parser.parse_args(argv)
    if args.command == "script":
        return execute_script(args)
    if args.command == "intelligence":
        return execute(args)
    if args.refresh and (args.offline or args.fixture):
        parser.error("--refresh is only valid for live collection")
    synthetic = args.fixture is not None
    db_path = args.db or ROOT / "data" / ("demo.sqlite3" if synthetic else "intelligence.sqlite3")
    reports_path = args.reports_dir or ROOT / "reports" / ("demo" if synthetic else "")
    db = None
    try:
        settings = Settings(max_uploads=args.max_uploads if args.max_uploads is not None else 100, lookback_days=args.lookback_days if args.lookback_days is not None else 90,
                            min_sample=args.min_sample, request_budget=args.request_budget)
        from .competitors import parse_config,effective_settings,resolve
        cohorts=json.loads(args.cohorts.read_text());rules=json.loads(args.radar_rules.read_text())
        raw_config=json.loads(args.channels.read_text())
        if args.fixture:
            fixture_config=json.loads(args.fixture.read_text()).get('competitor_config')
            if fixture_config:raw_config=fixture_config
        watchlist=parse_config(raw_config,cohorts)
        if args.cohort:
            if args.cohort not in cohorts['cohorts']:raise ValueError('Unknown cohort: '+args.cohort)
            watchlist=dict(watchlist,channels=[c for c in watchlist['channels'] if c['cohort']==args.cohort])
        configs=[]
        for c in watchlist['channels']:
            if not c['enabled']:continue
            profile=effective_settings(c,cohorts,settings,args.max_uploads,args.lookback_days)
            configs.append(dict(c,market_cohort=c['cohort'],max_uploads=profile.max_uploads,window_days=profile.lookback_days))
        if args.resolve_channels and (args.offline or args.fixture):raise ValueError('--resolve-channels requires live official API access')
        classifier = DictionaryTopicClassifier(json.loads(args.themes.read_text()))
        usage = Usage().to_dict()
        failures, warnings = [], []
        now = utcnow()
        if synthetic:
            fixture = json.loads(args.fixture.read_text())
            if fixture.get("synthetic") is not True:
                raise ValueError("Fixture must be explicitly marked synthetic")
            now = parse_time(fixture["observed_at"])
            videos, channels = fixture["videos"], fixture["channels"]
            mode_name = "synthetic"
        elif args.offline:
            mode_name = "offline"
        else:
            mode_name = "live"
            from dotenv import load_dotenv
            load_dotenv(ROOT / ".env")
            key = os.getenv("YOUTUBE_API_KEY", "").strip()
            if not key:
                raise ValueError("Set YOUTUBE_API_KEY in .env (see .env.example) or use --fixture/--offline")
        db = Database(db_path)
        if not synthetic:
            db.prune_cache(now)
        if args.resolve_channels:
            client=YouTubeClient(key,db,settings,refresh=args.refresh)
            resolutions=[resolve(client,c) for c in watchlist['channels']]
            for r in resolutions:print(json.dumps(r,ensure_ascii=False))
            from .reports import atomic_write
            atomic_write(reports_path/'channel_resolution.json',json.dumps({'channels':resolutions,'usage':client.usage.to_dict()},indent=2)+'\n')
            print('Quota: '+json.dumps(client.usage.to_dict()))
            return 2 if any(r['status']=='UNRESOLVED' for r in resolutions) else 0
        if synthetic:
            if args.cohort or fixture.get('competitor_config'):
                ids={c['channel_id'] for c in configs if c.get('channel_id')}
                channels=[c for c in channels if c['channel_id'] in ids];videos=[v for v in videos if v['channel_id'] in ids]
            for channel in channels:
                db.save_channel(channel)
            db.save_videos(videos)
        elif args.offline:
            channels = [c for c in db.load_channels() if any(
                conf.get("channel_id") == c["channel_id"] or
                (conf.get("handle") and conf["handle"].lower() == (c["handle"] or "").lower())
                for conf in configs)]
            stored = db.load_videos({c["channel_id"] for c in channels})
            videos = []
            for channel in channels:
                recent = sorted((r for r in stored if r["channel_id"] == channel["channel_id"]),
                                key=lambda r: r["published_at"], reverse=True)
                conf=next(c for c in configs if c.get('channel_id')==channel['channel_id'] or (c.get('handle') and c['handle'].lower()==(channel.get('handle') or '').lower()))
                channel.update({k:conf[k] for k in ('market_cohort','source_role','max_uploads','window_days','weight')})
                videos.extend(recent[:channel['max_uploads']])
            if not videos:
                raise ValueError("No retained observations available. Collect live data or run --fixture.")
            warnings.append("Offline replay: scores use statistics observation times, not the current time")
        else:
            client = YouTubeClient(key, db, settings, refresh=args.refresh)
            videos, channels, failures, warnings = collect(client, db, configs)
            usage = client.usage.to_dict()
        result = analyze(videos, channels, settings, classifier, now, mode_name, usage, failures, warnings)
        from .market import enrich
        result=enrich(result,watchlist,cohorts,rules)
        db.save_run(result)
        export(result, reports_path)
        from .market_reports import export_market
        export_market(result,reports_path)
        run_path=reports_path/'runs'/result['run_id']
        export(result,run_path);export_market(result,run_path)
        if args.opportunities:
            print('Top 20 editorial opportunities (not predictions):')
            for r in result['opportunities'][:20]:print(f"{r['opportunity_rank']:2d} | {r['opportunity_score']:.2f} | {r['market_cohort']} | {r['source_role']} | {r['title']}")
        print(summary(result))
        print(f"Reports: {reports_path.resolve()}")
        return 2 if failures else 0
    except (OSError, ValueError, KeyError, ImportError) as exc:
        # Do not print arbitrary exceptions containing HTTP request URLs/credentials.
        if isinstance(exc, ImportError):
            message = "Missing dependency: run python -m pip install -e ."
        elif isinstance(exc, (KeyError, json.JSONDecodeError)):
            message = "Invalid configuration or fixture schema"
        else:
            message = str(exc)
        print(f"Radar error: {message}")
        return 1
    finally:
        if db:
            db.close()
