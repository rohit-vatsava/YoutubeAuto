import csv
import io
import json
from pathlib import Path
from ..reports import atomic_write

CATEGORIES = ('RECOMMENDED FOR RESEARCH','READY FOR SCRIPTING','BACKLOG','REJECTED / REVIEW REQUIRED')
FILENAMES = ('ideas.csv','ideas.json','trend_clusters.json','story_briefs.json','intelligence.md')


def clean(text):
    return str(text).replace('\n', ' ').replace('|','\\|').replace('<','&lt;').replace('>','&gt;')


def markdown(result):
    meta = result['metadata']
    lines = ['# Tech Uncovered — Intelligence Brief','',
             f"Run: `{result['intelligence_run_id']}` | Radar: `{result['radar_run_id']}`",'',
             f"Mode: **{meta['mode']}** | Status: **{meta['status']}** | As of: {result['generated_at']}",'',
             'Scores prioritize editorial investigation; they are not viral probabilities. Production readiness is evaluated separately.','']
    if meta['mode'] == 'synthetic':
        lines += ['**FICTIONAL FIXTURE — no real-world facts or channel recommendations.**','']
    lines += ['## Best opportunities right now','']
    for category in CATEGORIES:
        lines += ['### '+category,'']
        members = [i for i in result['ideas'] if i['category']==category][:10]
        if not members:
            lines += ['None.','']
        for idea in members:
            lines += [f"**{idea['rank'] or '—'}. {clean(idea['audience_question'])}** — {idea['idea_score']:.2f}",
                      f"- Premise: {clean(idea['one_sentence_premise'])}",
                      f"- Why now (context/inference): {clean(idea['why_now'])}",
                      f"- Researchability — M2 (radar-context-v1): {idea.get('idea_researchability_score', 0):.0f}; preview (context-resolvability-v1): {idea.get('preview_researchability_score')}; Radar source: {idea.get('source_researchability_score')}. Status: {idea.get('review_status', idea['category'])}.",
                      f"- Evidence: {idea['scores']['EvidenceQuality']:.0f}/100; claim IDs: {', '.join(idea['material_claim_ids']) or 'none'}.",
                      f"- Source trend: {clean(idea['topic'])} (`{idea['cluster_id']}`).",
                      f"- Originality: {idea['similarity_status']}; {clean(idea['originality_notes'])}",
                      f"- Production difficulty: low-cost diagrams/screens assumed; approximately {idea['estimated_short_length']} seconds.",
                      f"- Research status: {', '.join(idea['risk_flags']) or 'no remaining review flags'}.",
                      f"- Production ready: **{str(idea['production_ready']).lower()}**."]
            lines += ['- Required research: '+clean(x) for x in idea['required_research']]
            lines.append('')
    lines += ['## Strongest trend clusters','']
    for cluster in result['trend_clusters']:
        lines += [f"### {clean(cluster['canonical_topic'])}",'',
                  'Supporting channels: '+', '.join(clean(c) for c in cluster['supporting_channels']),
                  f"Supporting eligible videos: {len(cluster['supporting_video_ids'])}; median/max adjusted Radar signal: {cluster['median_outlier_score']:.2f}/{cluster['max_velocity_score']:.2f}.",
                  f"Saturation: {cluster['saturation_level']} ({cluster['saturation_score']:.1f}/100).",
                  'Angles unobserved in this sample: '+', '.join(cluster['missing_angles'])+'.',
                  cluster['opportunity_notes'],'']
    lines += ['## Avoid / low-confidence topics','']
    flagged = [i for i in result['ideas'] if i['risk_flags']]
    for idea in flagged:
        lines.append(f"- {clean(idea['topic'])} / {idea['proposed_angle']}: {', '.join(idea['risk_flags'])}.")
    if not flagged:
        lines.append('None flagged by the baseline; human editorial judgment is still required.')
    lines += ['', '## Source evidence','']
    for candidate in result['candidates']:
        url = candidate['url']
        if not url.startswith(('https://','http://')):
            url = '#'
        url = url.replace(')', '%29').replace('(', '%28')
        lines.append(f"- [{clean(candidate['channel'])} / {candidate['video_id']}]({url}) — competitor framing and demand observation, not factual corroboration.")
    evidence = {e['evidence_id']:e for b in result['story_briefs'] for e in b['source_evidence'] if e.get('source_type') != 'COMPETITOR'}
    for eid,e in sorted(evidence.items()):
        ref = e['reference']
        label = f"[{clean(eid)}]({ref})" if ref.startswith(('https://','http://')) and ')' not in ref else clean(eid)+' — '+clean(ref)
        lines.append(f"- {label}: {clean(e['publisher'])}; {e['source_type']}; manually supplied evidence, not fetched or independently verified by this tool.")
    lines += ['', '## Partial failures','']
    lines += [f"- {f['stage']} / {f['video_id'] or 'unknown'}: {f['reason']}" for f in meta['partial_failures']] or ['None.']
    lines += ['', '## Data notes',''] + ['- '+clean(w) for w in meta['warnings']]
    return '\n'.join(lines)+'\n'


def export(result, directory):
    directory = Path(directory)
    run_dir = directory/'runs'/result['intelligence_run_id']
    if run_dir.exists():
        raise ValueError('Refusing to overwrite a historical Intelligence report')
    envelope = {k:result[k] for k in ('schema_version','module','scoring_version','intelligence_run_id','radar_run_id','generated_at','metadata')}
    serialized = {
        'ideas.json': json.dumps({**envelope,'ideas':result['ideas']},indent=2,ensure_ascii=False,allow_nan=False)+'\n',
        'trend_clusters.json':json.dumps({**envelope,'trend_clusters':result['trend_clusters']},indent=2,ensure_ascii=False,allow_nan=False)+'\n',
        'story_briefs.json':json.dumps({**envelope,'story_briefs':result['story_briefs'],'transcripts':result['transcripts']},indent=2,ensure_ascii=False,allow_nan=False)+'\n',
        'intelligence.md':markdown(result)}
    stream = io.StringIO(newline='')
    fields = ['rank','idea_id','topic','proposed_angle','audience_question','one_sentence_premise','idea_score',
              'production_ready','category','similarity_status','source_video_ids','risk_flags','required_research',
              'radar_run_id','intelligence_run_id','DemandSignal','Freshness','Originality','AudienceFit',
              'ProductionFit','EvidenceQuality','Expandability','SaturationRisk']
    writer = csv.DictWriter(stream,fieldnames=fields,extrasaction='ignore')
    writer.writeheader()
    for idea in result['ideas']:
        row = {**idea,**idea['scores']}
        for key,value in row.items():
            if isinstance(value,(list,dict)):
                row[key]=json.dumps(value,ensure_ascii=False)
            elif isinstance(value,str) and value.lstrip().startswith(('=','+','-','@')):
                row[key]="'"+value
        writer.writerow(row)
    serialized['ideas.csv']=stream.getvalue()
    for name,text in serialized.items():
        atomic_write(run_dir/name,text)
    for name,text in serialized.items():
        atomic_write(directory/name,text)


def expire_reports(directory, expired_ids):
    """Only remove known generated files with matching run IDs in this output directory."""
    directory=Path(directory)
    expired=set(expired_ids)
    for run_dir in (directory/'runs').glob('*'):
        if run_dir.name in expired and run_dir.is_dir() and not run_dir.is_symlink():
            for name in FILENAMES:
                (run_dir/name).unlink(missing_ok=True)
            if not list(run_dir.iterdir()):
                run_dir.rmdir()
    latest=directory/'ideas.json'
    if latest.exists():
        try:
            run_id=json.loads(latest.read_text())['intelligence_run_id']
        except (ValueError,KeyError):
            return
        if run_id in expired:
            for name in FILENAMES:
                (directory/name).unlink(missing_ok=True)


def summary(result, directory):
    ideas=result['ideas']
    clusters=result['trend_clusters']
    lines=[f"Intelligence | {result['metadata']['status']}",f"Radar run: {result['radar_run_id']}",
           f"Candidates analyzed: {len(result['story_briefs'])}",
           f"Transcripts available: {sum(t['transcript_status']=='AVAILABLE' for t in result['transcripts'].values())}",
           f"Trend clusters: {len(clusters)}",f"Ideas generated: {len(ideas)}",
           f"Ideas rejected as duplicates: {sum('REJECT_NEAR_DUPLICATE' in i['risk_flags'] for i in ideas)}",
           f"Ideas requiring research: {sum('RESEARCH_REQUIRED' in i['risk_flags'] for i in ideas)}",'', 'Top 5 opportunities:']
    top=[i for i in ideas if i['rank'] is not None][:5]
    lines += [f"{i['idea_score']:.2f} | {i['topic']} | {i['proposed_angle']} [{i['category']}]" for i in top] or ['None cleared the review gates.']
    if clusters:
        c=clusters[0]
        lines += ['',f"Strongest trend: {c['canonical_topic']}", 'Supporting channels: '+', '.join(c['supporting_channels']),
                  f"Median Radar score: {c['median_outlier_score']:.2f}"]
    lines += ['',f'Reports: {Path(directory).resolve()}',f"Partial failures: {len(result['metadata']['partial_failures'])}"]
    return '\n'.join(lines)
