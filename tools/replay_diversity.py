"""Offline diversity replay on a read-only source database and disposable copy.

python tools/replay_diversity.py --db data/intelligence.sqlite3 --run-id <M2 ID>
Reports only: never replaces the latest production M2 run.
"""
import argparse
import json
import sqlite3
import sys
import tempfile
from collections import Counter
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tech_uncovered.database import Database
from tech_uncovered.intelligence.pipeline import run_intelligence
from tech_uncovered.intelligence.selection import select_candidates
from tech_uncovered.intelligence.editorial import story_fields
from tech_uncovered.scripting.selection import select_ideas
from tech_uncovered.scripting.resolution import assess_researchability
from tech_uncovered.settings import parse_time


def legacy_preview(db, run_id):
    # Frozen pre-fix behavior for comparison only, including its category bug.
    ideas=[json.loads(r[0]) for r in db.connection.execute('SELECT payload FROM idea_candidates WHERE intelligence_run_id=?',(run_id,))]
    choices=[]
    for i in ideas:
        if i.get('category')=='REJECTED' or i.get('status')=='REJECTED' or i.get('duplicate_of') or i.get('similarity_status')=='REJECT' or 'REJECT_NEAR_DUPLICATE' in i.get('risk_flags',[]):continue
        refs=[json.loads(db.connection.execute('SELECT payload FROM intelligence_candidates WHERE intelligence_run_id=? AND source_video_id=?',(run_id,v)).fetchone()[0]) for v in i['source_video_ids']]
        c={'idea':i,'competitor_references':refs,**story_fields(i)}
        c.update(assess_researchability(c));choices.append(c)
    ordered=[]
    while choices:
        high=max(c['idea']['idea_score'] for c in choices)
        band=[c for c in choices if c['idea']['idea_score']>=high-7]
        winner=min(band,key=lambda c:(-c['researchability_score'],-c['idea']['idea_score'],c['idea']['idea_id']))
        ordered.append(winner);choices.remove(winner)
    return ordered


def snapshot(db,run_id):
    out={}
    for key,table in [('candidates','intelligence_candidates'),('ideas','idea_candidates'),('trend_clusters','trend_clusters')]:
        out[key]=[json.loads(r[0]) for r in db.connection.execute(f'SELECT payload FROM {table} WHERE intelligence_run_id=?',(run_id,))]
    return out


def describe(result,choices):
    selected=choices[:10];selected_ids={c['idea']['idea_id'] for c in selected}
    def compact(c):
        i=c['idea']
        return dict(idea_id=i['idea_id'],topic=i['topic'],angle=i['proposed_angle'],canonical_story_id=c['canonical_story_id'],idea_score=i['idea_score'],category=i['category'],m2_researchability_score=i.get('idea_researchability_score'),preview_researchability_score=c.get('preview_researchability_score',c.get('researchability_score')),cohorts=sorted({s['market_cohort'] for s in i.get('source_opportunities',[]) if s.get('market_cohort')}))
    excluded=sorted([i for i in result['ideas'] if i['idea_id'] not in selected_ids and not i.get('duplicate_of')],key=lambda i:(-i['idea_score'],i['idea_id']))
    return dict(intake_cohorts=dict(Counter(v.get('market_cohort','UNASSIGNED') for v in result['candidates'])),
        unique_canonical_stories=len({story_fields(i)['canonical_story_id'] for i in result['ideas']}),
        clusters=len(result['trend_clusters']),generated_ideas=len(result['ideas']),recommended_ideas=sum(i['category']=='RECOMMENDED FOR RESEARCH' for i in result['ideas']),
        preview=[compact(c) for c in selected],distinct_preview_stories=len({c['canonical_story_id'] for c in selected}),distinct_preview_topics=len({c['idea']['topic'] for c in selected}),distinct_preview_cohorts=len({s['market_cohort'] for c in selected for s in c['idea'].get('source_opportunities',[]) if s.get('market_cohort')}),lowest_included_idea_score=min((c['idea']['idea_score'] for c in selected),default=None),
        highest_excluded=[dict(idea_id=i['idea_id'],topic=i['topic'],angle=i['proposed_angle'],idea_score=i['idea_score'],category=i['category']) for i in excluded[:10]])


def replay(path,run_id,output):
    with sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True) as source, tempfile.TemporaryDirectory() as tmp:
        db=Database(Path(tmp)/'replay.sqlite3');source.backup(db.connection)
        row=db.connection.execute('SELECT * FROM intelligence_runs WHERE intelligence_run_id=?',(run_id,)).fetchone()
        if row is None:raise ValueError('Requested M2 run missing')
        cfg=json.loads(row['payload'])['config'];cfg.update(intake_limit=30,intake_quality_band=7,preview_score_window=7)
        now=parse_time(row['created_at']);old=snapshot(db,run_id);sizes=[];new=None
        for limit in (20,30,40,50):
            result=run_intelligence(db,cfg,now,radar_run_id=row['radar_run_id'],top=limit,offline=True)
            scores=[v['opportunity_score'] for v in result['candidates']]
            sizes.append(dict(limit=limit,unique_topics=len({i['topic'] for i in result['ideas']}),canonical_stories=len({i['canonical_story_id'] for i in result['ideas']}),cohorts=dict(Counter(v['market_cohort'] for v in result['candidates'])),expected_ideas=len(result['ideas']),recommended=sum(i['category']=='RECOMMENDED FOR RESEARCH' for i in result['ideas']),min_score=min(scores),max_score=max(scores),mean_score=sum(scores)/len(scores)))
            if limit==30:new=result
        new_id=new['intelligence_run_id']
        comparisons={
            'A_old':describe(old,legacy_preview(db,run_id)),
            'B_new_intake_only':describe(new,legacy_preview(db,new_id)),
            'C_new_preview_only':describe(old,select_ideas(db,run_id,top=10000,prefer_researchable=True)),
            'D_both':describe(new,select_ideas(db,new_id,top=10000,prefer_researchable=True))}
        for index, limit in enumerate(sizes):
            limit['mean_score_loss_vs_20']=sizes[0]['mean_score']-limit['mean_score']
            limit['marginal_mean_loss']=0 if index==0 else sizes[index-1]['mean_score']-limit['mean_score']
        backlog=describe(new,select_ideas(db,new_id,top=10000,prefer_researchable=True,include_backlog=True))
        payload=dict(source_intelligence_run_id=run_id,radar_run_id=row['radar_run_id'],as_of=now.isoformat(),network_calls=0,model_calls=0,api_calls=0,limits=sizes,comparisons=comparisons,explicit_backlog_preview=backlog,
                     note='Same Radar snapshot and M2 timestamp; no invented source candidates. Intake changes can naturally change cluster/similarity scores during M2 regeneration; selection never adjusts scores. Production database unchanged.')
        output.mkdir(parents=True,exist_ok=True)
        (output/'replay.json').write_text(json.dumps(payload,indent=2)+'\n')
        (output/'new-intelligence.json').write_text(json.dumps(new,indent=2)+'\n')
        lines=['# Offline diversity replay','',payload['note'],'','## Intake limits','','| Limit | Topics | Stories | Cohorts | Ideas | Recommended | Score range | Mean loss vs 20 |','|---|---|---|---|---|---|---|---|']
        for s in sizes:lines.append(f"| {s['limit']} | {s['unique_topics']} | {s['canonical_stories']} | {len(s['cohorts'])} | {s['expected_ideas']} | {s['recommended']} | {s['min_score']:.2f}–{s['max_score']:.2f} | {s['mean_score_loss_vs_20']:.2f} |")
        for name,r in comparisons.items():
            lines+=['',f'## {name}','',f"Intake: {r['intake_cohorts']}. Generated stories {r['unique_canonical_stories']}; ideas {r['generated_ideas']}; recommended {r['recommended_ideas']}; preview entries {len(r['preview'])}; stories {r['distinct_preview_stories']}; topics {r['distinct_preview_topics']}; cohorts {r['distinct_preview_cohorts']}.",'','| Idea ID | Topic / angle | Score | Category |','|---|---|---|---|']
            lines += [f"| {c['idea_id']} | {c['topic']} / {c['angle']} | {c['idea_score']:.2f} | {c['category']} |" for c in r['preview']]
            lines+=['',f"Lowest included idea score: {r['lowest_included_idea_score']}",'','Highest excluded:']+[f"- {c['idea_id']}: {c['topic']} / {c['angle']} — {c['idea_score']:.2f}, {c['category']}" for c in r['highest_excluded'][:3]]
        (output/'replay.md').write_text('\n'.join(lines)+'\n');db.close()
        return payload


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--db',type=Path,required=True);p.add_argument('--run-id',required=True);p.add_argument('--output',type=Path,default=Path('reports/diversity-replay'));args=p.parse_args()
    with patch('socket.socket.connect',side_effect=AssertionError('Replay forbids network')),patch('socket.create_connection',side_effect=AssertionError('Replay forbids network')):
        r=replay(args.db,args.run_id,args.output)
    print(json.dumps({'limits':r['limits'],'comparisons':{k:{x:v[x] for x in ['intake_cohorts','generated_ideas','recommended_ideas','distinct_preview_stories','distinct_preview_cohorts','lowest_included_idea_score']} for k,v in r['comparisons'].items()}},indent=2))
