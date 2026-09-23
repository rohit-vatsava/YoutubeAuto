"""Compare the unchanged pre-contract selector with the current entry contract.

Read-only production snapshots, zero network/model calls, no rescoring.
"""
import argparse
import hashlib
import json
import sqlite3
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tech_uncovered.intelligence.editorial import state
from tech_uncovered.intelligence.entry_contract import assess
from tech_uncovered.scripting.selection import select_ideas


def previous_eligible(idea,*,include_backlog=False):
    states={state(idea.get(k)) for k in ('category','review_status','status')}
    if any('REJECT' in s or 'REVIEW_REQUIRED' in s for s in states):return False
    if idea.get('duplicate_of') or idea.get('similarity_status') in {'REVIEW','REJECT'}:return False
    if set(idea.get('risk_flags',[])) & {'REJECT_NEAR_DUPLICATE','EDITORIAL_REVIEW_REQUIRED','FACTUAL_REVIEW_REQUIRED','ORIGINALITY_CONTEXT_LIMITED'}:return False
    return state(idea.get('category')) in {'RECOMMENDED_FOR_RESEARCH','READY_FOR_SCRIPTING'}


def replay(db_path,output):
    with sqlite3.connect(db_path.resolve().as_uri()+'?mode=ro',uri=True) as conn:
        conn.row_factory=sqlite3.Row;db=SimpleNamespace(connection=conn)
        # Restore only the old eligibility predicate. Scores, source snapshots,
        # story-first ordering and its cohort tie-break are exactly unchanged.
        with patch('tech_uncovered.intelligence.editorial.eligible',side_effect=previous_eligible):
            before=select_ideas(db,top=10,prefer_researchable=True)
        run_id=before[0]['intelligence_run_id']
        all_scores={json.loads(r[0])['idea_id']:json.loads(r[0])['idea_score'] for r in conn.execute('SELECT payload FROM idea_candidates WHERE intelligence_run_id=?',(run_id,))}
        try:after=select_ideas(db,run_id,top=10,prefer_researchable=True)
        except ValueError as exc:
            if str(exc)!='No eligible non-rejected idea in selected Intelligence run':raise
            after=[]
        def compact(c):
            i=c['idea'];return dict(idea_id=i['idea_id'],topic=i['topic'],subject_type=c['subject_type'],story_type=i.get('story_type'),angle_type=c['angle_type'],idea_score=i['idea_score'],stored_category=i['category'],story_requirement=c['story_requirement'],story_requirement_satisfied=c['story_requirement_satisfied'],story_resolution_mode=c['story_resolution_mode'],m3_entry_ready=c['m3_entry_ready'],m3_entry_blockers=c['m3_entry_blockers'],selection_reason=c.get('selection_reason'),audience_question=i['audience_question'])
        def test_candidate(i):
            return state(i.get('category'))=='RECOMMENDED_FOR_RESEARCH' and assess(i)['m3_entry_ready'] and assess(i)['story_requirement']!='COMPARISON_CONTEXT_REQUIRED'
        # Filter the pool first, then apply the existing ordering. No manual
        # preference or post-hoc skipping based on subject appeal.
        def test_eligible(i,**kwargs):return previous_eligible(i) and test_candidate(i)
        with patch('tech_uncovered.intelligence.editorial.eligible',side_effect=test_eligible):
            try:best=select_ideas(db,run_id,top=1,prefer_researchable=True)
            except ValueError as exc:
                if str(exc)!='No eligible non-rejected idea in selected Intelligence run':raise
                best=[]
        for c in before+after+best:assert c['idea']['idea_score']==all_scores[c['idea']['idea_id']]
        result=dict(intelligence_run_id=run_id,radar_run_id=before[0]['radar_run_id'],before=[compact(c) for c in before],after=[compact(c) for c in after],best_current_candidate=compact(best[0]) if best else None,network_calls=0,model_calls=0,api_calls=0,score_changes=0,
                    compatibility_note='EVERGREEN_SUBJECT and COMPARISON contracts are prepared but not executable by unchanged M3. Semantic requirement satisfied does not imply m3_entry_ready. EVENT, SECURITY_EVENT and BUSINESS_EVENT use its existing event contract.')
        output.mkdir(parents=True,exist_ok=True)
        (output/'replay.json').write_text(json.dumps(result,indent=2)+'\n')
        lines=['# M2 → M3 eligibility replay','',f"Production M2: `{run_id}`",'',result['compatibility_note'],'','## Original current top ten','','| ID | Topic | Subject type | Story type | Angle | Requirement | Satisfied | Entry ready | Blockers |','|---|---|---|---|---|---|---|---|---|']
        for r in result['before']:
            lines.append('| '+' | '.join(str(r[k]) for k in ['idea_id','topic','subject_type','story_type','angle_type','story_requirement','story_requirement_satisfied','m3_entry_ready','m3_entry_blockers'])+' |')
        lines+=['','## After contract filtering','','| ID | Topic | Angle | Score | Mode |','|---|---|---|---|---|']
        lines += [f"| {r['idea_id']} | {r['topic']} | {r['angle_type']} | {r['idea_score']:.3f} | {r['story_resolution_mode']} |" for r in result['after']]
        lines+=['','## Best current candidate','',json.dumps(result['best_current_candidate'],indent=2),'','Original idea payloads and scores were not modified. New template wording applies to future M2 runs; old malformed wording is blocked rather than silently repaired. The synthetic script fixture was augmented with its existing fictional Nacre release context, so offline tests satisfy the same entry checks without a production bypass.','', 'Entry readiness is a metadata/contract check, not verified story existence, evidence quality, or production readiness. The unchanged paid Story Resolution gate may still reject a candidate.']
        (output/'replay.md').write_text('\n'.join(lines)+'\n')
        return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--db',type=Path,default=Path('data/intelligence.sqlite3'));p.add_argument('--output',type=Path,default=Path('reports/entry-contract-replay'));args=p.parse_args()
    with patch('socket.socket.connect',side_effect=AssertionError('No network')),patch('socket.create_connection',side_effect=AssertionError('No network')):
        result=replay(args.db,args.output)
    print(json.dumps(result,indent=2))
