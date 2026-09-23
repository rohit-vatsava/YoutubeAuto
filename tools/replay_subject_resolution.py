"""Read-only source DB, fixed 30-input baseline, offline-only M2 resolution replay."""
import argparse
import json
import sqlite3
import sys
import tempfile
from collections import Counter
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tech_uncovered.database import Database
from tech_uncovered.settings import parse_time
from tech_uncovered.intelligence.pipeline import run_intelligence
from tech_uncovered.scripting.selection import select_ideas


def summarize(result):
    by_video={v['video_id']:v for v in result['candidates']}
    grouped={}
    for i in result['ideas']:
        key=i['canonical_story_id']
        grouped.setdefault(key,set()).update(by_video[v]['market_cohort'] for v in i['source_video_ids'])
    counts=Counter(co for cs in grouped.values() for co in cs)
    return dict(inputs=len(result['candidates']),usable_inputs=len({v for i in result['ideas'] for v in i['source_video_ids']}),
        generated_canonical_stories=len(grouped),generated_ideas=len(result['ideas']),
        recommended_ideas=sum(i['category']=='RECOMMENDED FOR RESEARCH' for i in result['ideas']),
        generated_story_cohorts=dict(counts))


def replay(db_path, baseline_path, output):
    before=json.loads(baseline_path.read_text())
    with sqlite3.connect(db_path.resolve().as_uri()+'?mode=ro',uri=True) as source,tempfile.TemporaryDirectory() as tmp:
        db=Database(Path(tmp)/'replay.db');source.backup(db.connection)
        after=run_intelligence(db,before['metadata']['config'],parse_time(before['generated_at']),
                              radar_run_id=before['radar_run_id'],top=len(before['candidates']),offline=True)
        assert before['candidates']==after['candidates'], 'Intake order or input snapshots changed; replay invalid'
        assert not after['metadata']['partial_failures'], after['metadata']['partial_failures']
        old_briefs={b['video_id']:b for b in before['story_briefs']};new_briefs={b['video_id']:b for b in after['story_briefs']}
        comparison=[]
        for v in before['candidates']:
            b=old_briefs[v['video_id']]
            if b['canonical_subject']:continue
            a=new_briefs[v['video_id']];resolution=a['metadata_subject_resolution']
            old_ideas=[i for i in before['ideas'] if v['video_id'] in i['source_video_ids']]
            new_ideas=[i for i in after['ideas'] if v['video_id'] in i['source_video_ids']]
            comparison.append(dict(video_id=v['video_id'],title=v['title'],channel=v['channel'],cohort=v['market_cohort'],old_subject=b['canonical_subject'],
                new_subject=a['canonical_subject'],subject_type=resolution['subject_type'],story_type=resolution['story_type'],confidence=resolution['confidence'],event_or_change=resolution['event_or_change'],
                radar_researchability_unchanged=v['researchability_score'],m2_researchability_before=max((i['idea_researchability_score'] for i in old_ideas),default=None),
                m2_researchability_after=max((i['idea_researchability_score'] for i in new_ideas),default=None),can_generate=bool(new_ideas),unresolved_reasons=resolution['unresolved_reasons']))
        try:choices=select_ideas(db,after['intelligence_run_id'],top=10,prefer_researchable=True)
        except ValueError as exc:
            if str(exc)!='No eligible non-rejected idea in selected Intelligence run':raise
            choices=[]
        preview=[dict(idea_id=c['idea']['idea_id'],topic=c['idea']['topic'],angle=c['idea']['proposed_angle'],story_type=c['idea']['story_type'],idea_score=c['idea']['idea_score'],m2_researchability_score=c['m2_researchability_score'],preview_researchability_score=c['preview_researchability_score'],category=c['editorial_state'],canonical_story_id=c['canonical_story_id']) for c in choices]
        all_inputs=[]
        for v in before['candidates']:
            a=new_briefs[v['video_id']];all_inputs.append({'video_id':v['video_id'],'title':v['title'],'old_subject':old_briefs[v['video_id']]['canonical_subject'],'resolution':a['metadata_subject_resolution'],'new_idea_count':sum(v['video_id'] in i['source_video_ids'] for i in after['ideas'])})
        report=dict(before=summarize(before),after=summarize(after),intake_unchanged=True,network_calls=0,model_calls=0,api_calls=0,
                    previously_unresolved=comparison,all_inputs=all_inputs,preview=preview,
                    researchability_note='Before/after is M2 idea researchability. NULL means no idea existed, not a zero score. Original Radar researchability is separately shown and unchanged. Same formulas operate on improved metadata.',
                    interpretation='Extraction confidence is not fact/evidence confidence. Context remains limited; no title allegation has been verified.')
        output.mkdir(parents=True,exist_ok=True)
        for name,data in [('replay.json',report),('before-intelligence.json',before),('after-intelligence.json',after)]:
            (output/name).write_text(json.dumps(data,indent=2,ensure_ascii=False)+'\n')
        def cell(x):return '—' if x is None else str(x).replace('|','\\|').replace('\n',' ')
        lines=['# Metadata subject resolution — offline replay','',report['researchability_note'],'',report['interpretation'],'','## Previously unresolved inputs','','| Title | Channel | Cohort | Old subject | New subject | Type | Story type | Confidence | Event/change | Radar researchability (unchanged) | M2 before | M2 after | Ideas possible |','|'+'---|'*13]
        for c in comparison:
            keys=['title','channel','cohort','old_subject','new_subject','subject_type','story_type','confidence','event_or_change','radar_researchability_unchanged','m2_researchability_before','m2_researchability_after','can_generate']
            lines.append('| '+' | '.join(cell(c[k]) for k in keys)+' |')
        lines+=['','## Counts','','| Metric | Before | After |','|---|---|---|']
        for k in ['inputs','usable_inputs','generated_canonical_stories','generated_ideas','recommended_ideas']:
            lines.append(f"| {k} | {report['before'][k]} | {report['after'][k]} |")
        lines+=['','## Generated story cohort memberships','','| Cohort | Before | After |','|---|---|---|']
        for k in sorted({v['market_cohort'] for v in before['candidates']}):
            lines.append(f"| {k} | {report['before']['generated_story_cohorts'].get(k,0)} | {report['after']['generated_story_cohorts'].get(k,0)} |")
        lines+=['','## Default preview','','| Idea ID | Topic / angle | Idea score | M2 researchability | Preview researchability |','|---|---|---|---|---|']
        lines += [f"| {p['idea_id']} | {cell(p['topic'])} / {p['angle']} | {p['idea_score']:.2f} | {p['m2_researchability_score']} | {p['preview_researchability_score']} |" for p in preview]
        lines+=['','## All selected input outcomes','','| Title | New subject | Story type | Generated ideas |','|---|---|---|---|']
        lines += [f"| {cell(x['title'])} | {cell(x['resolution']['canonical_subject'])} | {x['resolution']['story_type']} | {x['new_idea_count']} |" for x in all_inputs]
        lines+=['','Intake snapshots/order, selection policies, Radar scores, score weights and researchability formulas are unchanged. Production database was not modified. A lower recommended count can result from conservative context rejection and unsupported-comparison suppression.']
        (output/'replay.md').write_text('\n'.join(lines)+'\n');db.close();return report


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--db',type=Path,required=True);p.add_argument('--baseline',type=Path,required=True);p.add_argument('--output',type=Path,default=Path('reports/subject-resolution-replay'));a=p.parse_args()
    with patch('socket.socket.connect',side_effect=AssertionError('No network')),patch('socket.create_connection',side_effect=AssertionError('No network')):
        r=replay(a.db,a.baseline,a.output)
    print(json.dumps({k:r[k] for k in ['before','after','intake_unchanged','preview']},indent=2))
