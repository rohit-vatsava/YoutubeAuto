import json
import os
import math
import sqlite3
from pathlib import Path
from datetime import datetime, timezone
from ..database import Database
from ..intelligence.storage import persist
from .selection import select_ideas
from .costs import Budget
from .models import digest
from .pipeline import run
from .reports import export, expire_reports
from .storage import cached_result

ROOT=Path(__file__).resolve().parents[2]


def add_parser(sub):
    parser=sub.add_parser('script',help='Module 3: evidence-first research and one Short script')
    parser.add_argument('--top',type=int,default=1)
    parser.add_argument('--preview',action='store_true',help='Read-only top 10 eligible ideas; no network or API key')
    parser.add_argument('--include-backlog', action='store_true', help='Include visibly labelled BACKLOG research leads; never review/rejected ideas')
    parser.add_argument('--idea-id')
    parser.add_argument('--resume',metavar='SCRIPT_ID',help='Revalidate saved angle and continue at outline generation')
    parser.add_argument('--accept-pivot',action='store_true',help='Accept a compatible saved evidence pivot; skip all research')
    parser.add_argument('--pivot-dir',type=Path,help='Explicit saved pivot artifact directory')
    parser.add_argument('--dry-run',action='store_true',help='Offline pivot acceptance and cost/stage projection only')
    parser.add_argument('--intelligence-run-id')
    parser.add_argument('--offline',action='store_true')
    parser.add_argument('--research-file',type=Path)
    parser.add_argument('--refresh-research',action='store_true')
    parser.add_argument('--reports-dir',type=Path)
    parser.add_argument('--db',type=Path)
    parser.add_argument('--config',type=Path,default=ROOT/'config/script.json')


def configuration(path):
    cfg=json.loads(path.read_text())
    for key in ('model_provider','model_name','research_provider'):
        cfg[key]=os.getenv(key.upper(),cfg[key])
    for key in ('max_search_calls','max_sources','max_model_cost_usd','max_research_seconds'):
        if key.upper() in os.environ:cfg[key]=float(os.environ[key.upper()]) if key in ('max_model_cost_usd','max_research_seconds') else int(os.environ[key.upper()])
    pricekeys={'MODEL_INPUT_USD_PER_MILLION':'input_per_million','MODEL_CACHED_INPUT_USD_PER_MILLION':'cached_input_per_million','MODEL_OUTPUT_USD_PER_MILLION':'output_per_million','SEARCH_USD_PER_CALL':'search_per_call'}
    if any(k in os.environ for k in pricekeys):
        if not all(k in os.environ for k in pricekeys):raise ValueError('Set all four pricing overrides together')
        cfg['pricing']={v:float(os.environ[k]) for k,v in pricekeys.items()};cfg['pricing']['model_name']=cfg['model_name'];cfg['pricing']['source']='environment override'
    for k in ('max_search_calls','max_sources','max_output_tokens','max_attempts','script_word_min','script_word_max','max_page_bytes','max_source_chars'):
        if not isinstance(cfg[k],int) or isinstance(cfg[k],bool) or cfg[k]<1:raise ValueError('Invalid positive integer configuration: '+k)
    if cfg['max_revision_attempts'] not in (0,1):raise ValueError('At most one editorial revision supported')
    for k in ('max_model_cost_usd','max_research_seconds','request_timeout_seconds','words_per_minute'):
        if not math.isfinite(cfg[k]) or cfg[k]<=0:raise ValueError('Invalid positive limit: '+k)
    if not 0<=cfg['quality_threshold']<=100 or cfg['script_word_min']>cfg['script_word_max']:raise ValueError('Invalid quality or length bounds')
    if any(not isinstance(v,(int,float)) or not math.isfinite(v) or v<0 for k,v in cfg['pricing'].items() if k.endswith('million') or k=='search_per_call'):raise ValueError('Invalid price')
    for key,ceiling in (('preflight_max_cost_usd',.08),('preflight_max_seconds',45)):
        value=cfg.get(key,ceiling)
        if not isinstance(value,(int,float)) or not math.isfinite(value) or not 0<value<=ceiling:raise ValueError('Invalid preflight bound: '+key)
    for key in ('source_topic_relevance_threshold','researchability_score_window'):
        value=cfg.get(key,70 if key.startswith('source') else 7)
        if not isinstance(value,(int,float)) or not math.isfinite(value) or not 0<=value<=100:raise ValueError('Invalid configuration: '+key)
    return cfg


def execute(args):
    db=None
    try:
        if getattr(args,'resume',None):return execute_resume(args)
        if getattr(args,'accept_pivot',False):return execute_pivot(args)
        if getattr(args,'dry_run',False) or getattr(args,'pivot_dir',None):raise ValueError('--dry-run and --pivot-dir require --accept-pivot')
        if args.preview:return preview(args)
        if args.top<1:raise ValueError('--top must be positive')
        if bool(args.research_file)!=bool(args.offline):raise ValueError('Offline mode requires both --offline and --research-file; no automatic live fallback')
        if args.offline and args.refresh_research:raise ValueError('--refresh-research is live-only')
        if not args.offline:
            from dotenv import load_dotenv
            load_dotenv(ROOT/'.env')
        cfg=configuration(args.config)
        bundle=None;now=datetime.now(timezone.utc).isoformat()
        db_path=args.db or ROOT/'data'/('scripts-demo.sqlite3' if args.offline else 'intelligence.sqlite3')
        if args.offline:
            if db_path.resolve()==(ROOT/'data/intelligence.sqlite3').resolve():raise ValueError('Use a separate database for fictional fixtures')
            bundle=json.loads(args.research_file.read_text())
            if bundle.get('synthetic') is not True:raise ValueError('Offline fixtures must be explicitly fictional')
            seed=json.loads((args.research_file.parent/bundle['intelligence_file']).read_text())
            if seed.get('synthetic') is not True or seed['metadata']['mode']!='synthetic':raise ValueError('Intelligence seed must be synthetic')
            now=bundle['as_of']
        db=Database(db_path)
        if bundle:
            old=db.connection.execute('SELECT payload FROM idea_candidates WHERE intelligence_run_id=?',(seed['intelligence_run_id'],)).fetchall()
            if not old:persist(db,seed)
            elif sorted(digest(json.loads(r[0])) for r in old)!=sorted(digest(i) for i in seed['ideas']):raise ValueError('Existing fixture idea differs; use a fresh demo database')
        else:
            db.prune(datetime.now(timezone.utc))
            expire_reports(args.reports_dir or ROOT/'reports/scripts',datetime.now(timezone.utc))
        selected=select_ideas(db,args.intelligence_run_id or (seed['intelligence_run_id'] if bundle else None),args.idea_id,args.top,prefer_researchable=not bool(bundle),score_window=cfg.get('researchability_score_window',7),include_backlog=getattr(args,'include_backlog',False))
        failures=0
        for choice in selected:
            if not bundle and not choice['m3_entry_ready']:
                raise ValueError('M3 entry blocked: '+', '.join(choice['m3_entry_blockers']))
            print('Selected idea: '+choice['idea']['idea_id']+' — '+choice['idea']['proposed_angle'],flush=True)
            if choice.get('selection_reason'):print(choice['selection_reason'])
            if not bundle and choice['mode']=='synthetic':raise ValueError('Live mode cannot consume fictional ideas')
            if not bundle and not args.refresh_research:
                cache=cached_result(db,choice,cfg,now)
                if cache:print('Cached READY result: '+cache+' (no API requests; use --refresh-research to repeat)');continue
            budget=Budget(cfg,offline=bool(bundle))
            if bundle:
                from .providers.fixtures import FixtureResearchProvider,FixtureResearchSynthesizer,FixtureScriptGenerator,FixtureScriptFactChecker,FixtureQualityReviewer
                provider,synth,generator,checker,reviewer=(cls(bundle) for cls in (FixtureResearchProvider,FixtureResearchSynthesizer,FixtureScriptGenerator,FixtureScriptFactChecker,FixtureQualityReviewer))
            else:
                if cfg['model_provider']!='openai' or cfg['research_provider']!='openai_web':raise ValueError('Configured live provider is not implemented')
                key=os.getenv('OPENAI_API_KEY','').strip()
                if not key:raise ValueError('Set OPENAI_API_KEY in .env before explicitly running live mode')
                from .providers.openai_live import OpenAIModel,WebResearchProvider,ModelResearchSynthesizer,ModelScriptGenerator,ModelScriptFactChecker,ModelScriptQualityReviewer
                model=OpenAIModel(key,cfg,budget);provider=WebResearchProvider(model,cfg,budget,now)
                synth,generator,checker,reviewer=(cls(model) for cls in (ModelResearchSynthesizer,ModelScriptGenerator,ModelScriptFactChecker,ModelScriptQualityReviewer))
            result=run(db,choice,cfg,provider,synth,generator,checker,reviewer,budget,now,'synthetic' if bundle else 'live')
            folder=export(result,args.reports_dir or ROOT/'reports'/('scripts-demo' if bundle else 'scripts'))
            print('Story resolution: '+result.get('story_resolution',{}).get('status','UNRESOLVED'))
            print('Status: '+result['readiness']['status']);print('Reports: '+str(folder.resolve()))
            print('Cost record: '+json.dumps(result['cost'],sort_keys=True))
            if result['failures']:failures+=1;print('Partial failures: '+str(len(result['failures'])))
        return 2 if failures else 0
    except (ValueError,KeyError,OSError,ImportError,sqlite3.Error) as exc:
        print('Script error: '+(str(exc) if isinstance(exc,ValueError) and not isinstance(exc,json.JSONDecodeError) else type(exc).__name__));return 1
    finally:
        if db:db.close()


def preview(args):
    import sqlite3
    from types import SimpleNamespace
    path=(args.db or ROOT/'data/intelligence.sqlite3').resolve()
    connection=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)
    connection.row_factory=sqlite3.Row
    try:
        cfg=json.loads(args.config.read_text())
        choices=select_ideas(SimpleNamespace(connection=connection),args.intelligence_run_id,args.idea_id,10,
                             prefer_researchable=True,score_window=cfg.get('researchability_score_window',7),include_backlog=getattr(args,'include_backlog',False))
        print('Preview: '+str(len(choices))+' eligible ideas (up to 10); no network/model calls.')
        for rank,c in enumerate(choices,1):
            i=c['idea']
            print(json.dumps({'rank':rank,'idea_id':i['idea_id'],'idea_score':round(i['idea_score'],3),
                'topic':i['topic'],'audience_question':i['audience_question'],
                'source_video_titles':[r['title'] for r in c['competitor_references']],
                'source_channels':sorted({r['channel'] for r in c['competitor_references']}),
                'context_status':c['context_status'],
                **{k:c[k] for k in ('subject_type','story_requirement','story_requirement_satisfied','story_resolution_mode','m3_entry_ready','m3_entry_blockers','stored_editorial_state','editorial_state','canonical_story_id','canonical_story_label','angle_type','m2_researchability_score','m2_researchability_version','preview_researchability_score','preview_researchability_version')},
                **{k:c.get(k) for k in ('topic_rank','angle_rank_within_topic','preview_selection_phase')},
                'unresolved_flags':c['unresolved_flags'],'selection_reason':c.get('selection_reason')},ensure_ascii=False))
        return 0
    finally:connection.close()


def execute_pivot(args):
    from .pivot_acceptance import load_latest, dry_run
    from .pipeline import run_accepted_pivot
    if not args.idea_id or args.top!=1:raise ValueError('--accept-pivot requires exactly one explicit --idea-id')
    if args.preview or args.refresh_research or args.research_file:raise ValueError('Pivot acceptance cannot be combined with preview or research options')
    if args.offline and not args.dry_run:raise ValueError('Offline pivot CLI requires --dry-run; no automatic live fallback')
    if not args.dry_run:
        from dotenv import load_dotenv
        load_dotenv(ROOT/'.env')
    cfg=configuration(args.config);now=datetime.now(timezone.utc).isoformat()
    candidate=load_latest(args.idea_id,ROOT/'reports',now,cfg,args.pivot_dir)
    if args.intelligence_run_id and args.intelligence_run_id!=candidate['selected']['intelligence_run_id']:
        raise ValueError('Pivot intelligence-run provenance mismatch')
    if args.dry_run:
        folder=args.reports_dir or ROOT/'reports/pivot-acceptance-dry-run'
        if folder.resolve()==Path(candidate['artifact_path']).resolve():raise ValueError('Dry-run output must not overwrite source artifacts')
        print(json.dumps(dry_run(candidate,cfg,now,folder),indent=2));print('Reports: '+str(folder.resolve()))
        return 0
    if candidate['selected'].get('mode')=='synthetic':raise ValueError('Live acceptance cannot use fictional research')
    if cfg['model_provider']!='openai':raise ValueError('Configured generation provider is not implemented')
    key=os.getenv('OPENAI_API_KEY','').strip()
    if not key:raise ValueError('Set OPENAI_API_KEY before explicitly triggering live pivot generation')
    db=Database(args.db or ROOT/'data/intelligence.sqlite3')
    try:
        row=db.connection.execute('SELECT selected_snapshot FROM research_runs_v3 WHERE research_run_id=?',
            (candidate['packet']['research_run_id'],)).fetchone()
        if not row or digest(json.loads(row[0]))!=digest(candidate['selected']):raise ValueError('Saved research selection does not match database provenance')
        saved=db.connection.execute('SELECT payload FROM research_packets WHERE research_run_id=?',
            (candidate['packet']['research_run_id'],)).fetchone()
        if not saved or digest(json.loads(saved[0]))!=candidate['original_packet_hash']:
            raise ValueError('Original research packet differs from database provenance')
        saved_sources=[json.loads(row[0]) for row in db.connection.execute('SELECT payload FROM research_sources WHERE research_run_id=?',
            (candidate['packet']['research_run_id'],))]
        if digest(sorted(saved_sources,key=lambda s:s['source_id']))!=digest(sorted(candidate['sources'],key=lambda s:s['source_id'])):
            raise ValueError('Fetched sources differ from database provenance')
        from .providers.openai_live import OpenAIModel,ModelScriptGenerator,ModelScriptFactChecker,ModelScriptQualityReviewer
        budget=Budget(cfg);model=OpenAIModel(key,cfg,budget)
        generator,checker,reviewer=(cls(model) for cls in (ModelScriptGenerator,ModelScriptFactChecker,ModelScriptQualityReviewer))
        result=run_accepted_pivot(db,candidate,cfg,generator,checker,reviewer,budget,now)
        folder=export(result,args.reports_dir or ROOT/'reports/scripts')
        print('Status: '+result['readiness']['status']);print('Reports: '+str(folder.resolve()))
        print('Cost record: '+json.dumps(result['cost'],sort_keys=True))
        return 2 if result['failures'] else 0
    finally:db.close()


def execute_resume(args):
    from .resume import load_resume,promote
    from .pipeline import run_accepted_pivot
    if any((args.accept_pivot,args.idea_id,args.intelligence_run_id,args.preview,args.refresh_research,args.research_file,args.pivot_dir,args.offline,args.dry_run)) or args.top!=1:
        raise ValueError('--resume cannot be combined with selection/research/offline options')
    from dotenv import load_dotenv
    load_dotenv(ROOT/'.env')
    cfg=configuration(args.config);now=datetime.now(timezone.utc).isoformat()
    root=args.reports_dir or ROOT/'reports/scripts'
    db=Database(args.db or ROOT/'data/intelligence.sqlite3')
    try:
        resume=load_resume(root,args.resume,db,now,cfg)  # wholly offline, before model construction
        if resume['run']['mode']!='live':raise ValueError('Live resume cannot consume fictional fixtures')
        if cfg['model_provider']!='openai':raise ValueError('Configured generation provider is not implemented')
        key=os.getenv('OPENAI_API_KEY','').strip()
        if not key:raise ValueError('Set OPENAI_API_KEY before explicitly triggering live resume')
        promote(resume)
        from .providers.openai_live import OpenAIModel,ModelScriptGenerator,ModelScriptFactChecker,ModelScriptQualityReviewer
        budget=Budget(cfg);model=OpenAIModel(key,cfg,budget)
        generator,checker,reviewer=(cls(model) for cls in (ModelScriptGenerator,ModelScriptFactChecker,ModelScriptQualityReviewer))
        result=run_accepted_pivot(db,{'selected':resume['selected']},cfg,generator,checker,reviewer,budget,now,resume=resume)
        folder=export(result,root)
        print('Status: '+result['readiness']['status']);print('Resumed from: '+args.resume)
        print('Reports: '+str(folder.resolve()));print('New-stage cost record: '+json.dumps(result['cost'],sort_keys=True))
        return 2 if result['failures'] else 0
    finally:db.close()
