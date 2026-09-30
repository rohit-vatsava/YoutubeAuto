import json
from pathlib import Path
from .planning import build
from .qa import check

def add_parser(sub):
    p=sub.add_parser('produce',help='M4 offline production spec and render bundle')
    mode=p.add_mutually_exclusive_group(required=True)
    mode.add_argument('--fixture',type=Path);mode.add_argument('--script-id')
    p.add_argument('--revision',type=int);p.add_argument('--preview',action='store_true')
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--db',type=Path,default=Path('data/intelligence.sqlite3'))
    p.add_argument('--script-root',type=Path,default=Path('reports/scripts'))
    return p

def execute(args):
    try:
        if (args.output/'production-spec.json').exists():raise ValueError('Output already exists; choose a new directory')
        if args.fixture:
            data=json.loads(args.fixture.read_text())
            if data.get('synthetic') is not True:raise ValueError('Fixture must be explicitly synthetic')
            draft,packet,readiness,selected=(data[k] for k in ('draft','packet','readiness','selected'))
        else:
            if args.revision is None:raise ValueError('--revision is required')
            from ..database import Database
            from ..scripting.editorial_revision import source,saved_revision,read
            db=Database(args.db)
            try:
                data,payload=source(args.script_root,args.script_id,db)
                draft,_,folder=saved_revision(args.script_root,args.script_id,args.revision,db,data,payload)
                packet,selected=data['research_packet'],data['idea']
                reviewfolder=folder/'quality-continuation'
                readiness=read((reviewfolder if (reviewfolder/'readiness.json').exists() else folder)/'readiness.json')
            finally:db.close()
        spec=build(draft,packet,readiness,args.output,preview=args.preview,selected=selected).to_dict()
        qa=check(spec,draft,packet,args.output)
        if not qa['passed']:raise ValueError('Production QA failed: '+str(qa['errors']))
        for name,value in [('production-spec',spec),('render-props',{'spec':spec}),('qa',qa),('source-draft',draft),('source-packet',packet),('creative-dna',spec['creative_dna']),('storyboard',spec['scenes']),('asset-plan',spec['assets'])]:
            (args.output/(name+'.json')).write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n')
        # Portable frame timings for caption systems; SRT times are frame-derived.
        def stamp(frame):
            ms=round(frame/spec['fps']*1000);return f'{ms//3600000:02}:{ms//60000%60:02}:{ms//1000%60:02},{ms%1000:03}'
        caps=[c for s in spec['scenes'] for c in s['caption_segments']]
        (args.output/'captions.srt').write_text('\n\n'.join(f"{i}\n{stamp(c['start_frame'])} --> {stamp(c['end_frame'])}\n{c['text']}" for i,c in enumerate(caps,1))+'\n')
        print(json.dumps({'video_id':spec['video_id'],'status':spec['production_status'],'qa':qa,'output':str(args.output.resolve())},indent=2));return 0
    except (ValueError,OSError,KeyError) as exc:
        print('Production error: '+str(exc));return 2
