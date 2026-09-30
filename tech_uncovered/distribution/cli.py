import json
from pathlib import Path
from .storage import Store
from .adapters import YouTubeAnalyticsAdapter,InstagramAnalyticsAdapter

def add_parser(sub):
    p=sub.add_parser('performance',help='M5 offline metric import and Creative DNA joins; never publishes')
    p.add_argument('--spec',type=Path,required=True);p.add_argument('--fixture',type=Path,required=True)
    p.add_argument('--db',type=Path,default=Path('data/production.sqlite3'));p.add_argument('--output',type=Path,required=True)

def execute(args):
    store=None
    try:
        data=json.loads(args.fixture.read_text());spec=json.loads(args.spec.read_text())
        if data.get('synthetic') is not True:raise ValueError('Use an explicit synthetic fixture for this offline command')
        store=Store(args.db);store.save_production(spec)
        for row in data['measurements']:
            if row['platform'] not in ('youtube','instagram'):raise ValueError('Unknown platform')
            adapter=YouTubeAnalyticsAdapter() if row['platform']=='youtube' else InstagramAnalyticsAdapter()
            store.save_performance(adapter.normalize(spec['video_id'],row['metrics'],row['measurement_window'],row['measured_at']))
        args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps({'synthetic':True,'records':store.joined()},indent=2)+'\n')
        print(json.dumps({'status':'OFFLINE_ONLY','records':len(store.joined()),'database':str(args.db),'output':str(args.output)}));return 0
    except (ValueError,OSError,KeyError) as exc:print('Performance error: '+str(exc));return 2
    finally:
        if store:store.close()
