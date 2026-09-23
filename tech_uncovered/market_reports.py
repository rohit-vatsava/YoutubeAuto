import csv
import io
import json
from pathlib import Path
from .reports import atomic_write

FIELDS=['opportunity_rank','video_id','title','channel','market_cohort','source_role','commercial_value_tag','published_at','current_age_days','cohort','baseline_sample_size','velocity_adjusted_score','normalized_radar_signal','researchability_score','cross_cohort_support','opportunity_score','named_entity_hints','event_hints','researchability_reasons','production_fit','production_fit_reason','url']


def export_market(result,directory):
    directory=Path(directory)
    envelope={k:result[k] for k in ('run_id','generated_at','competitor_config_version','cohort_config_version','scoring_version','metadata','cohort_summaries','cross_cohort_signals','opportunities')}
    atomic_write(directory/'opportunities.json',json.dumps(envelope,indent=2,ensure_ascii=False,allow_nan=False)+'\n')
    stream=io.StringIO(newline='');writer=csv.DictWriter(stream,fieldnames=FIELDS,extrasaction='ignore');writer.writeheader()
    for row in result['opportunities']:
        safe=dict(row)
        for k,v in safe.items():
            if isinstance(v,list):safe[k]=json.dumps(v,ensure_ascii=False)
            if isinstance(safe[k],str) and safe[k].lstrip().startswith(('=','+','-','@')):safe[k]="'"+safe[k]
        writer.writerow(safe)
    atomic_write(directory/'opportunities.csv',stream.getvalue())
    rows={r['video_id']:r for r in result['opportunities']}
    lines=['# Tech Uncovered — Market Radar','',f"Run: {result['run_id']} | {result['metadata']['mode']} | {result['metadata']['status']}",'',
           'Editorial heuristics, not view/revenue predictions. Vendor coverage is separately identified; it is not independent audience corroboration.',
           f"Current window: {result['metadata']['market_config']['current_window_days']} days. Baselines remain per channel and duration group; cohort medians give each channel its configured weight.",
           'Cross-cohort labels indicate subject overlap, not verified shared events. Source roles do not change opportunity scores.','']
    def show(items):
        if not items:lines.append('No qualifying entries.')
        for r in items:
            title=r['title'].replace('[','(').replace(']',')').replace('\n',' ')
            lines.append(f"- **{r['opportunity_score']:.1f}** | [{title}]({r['url']}) — {r['channel']} | {r['source_role']} | adjusted {r['velocity_adjusted_score']:.2f} | researchability {r['researchability_score']} | {r['production_fit']}")
        lines.append('')
    for c in result['cohort_summaries']:
        lines.extend(['## '+c['label'],'',f"Channels: {c['channels_monitored']} ({c['vendor_channels_monitored']} vendor) | baseline-eligible videos: {c['eligible_videos']} | current eligible: {c['current_eligible_videos']} | current outliers: {c['qualifying_outliers']} | researchable outliers: {c['researchable_outliers']}",f"Channel-balanced median adjusted score: {c['median_adjusted_score']} | max: {c['maximum_adjusted_score']} | median views/day: {c['median_views_per_day']}",f"Independent/media outliers: {c['independent_outliers']} | Vendor outliers: {c['vendor_outliers']} | Independent median: {c['independent_median_adjusted_score']} | Vendor median: {c['vendor_median_adjusted_score']}",f"Recent activity: {c['recent_activity']} | Commercial tag: {c['commercial_value']}",'Recurring subjects: '+(json.dumps(c['recurring_subjects']) if c['recurring_subjects'] else 'none meeting the multiple-channel threshold'),''])
        show([rows[v] for v in c['top_opportunities']])
        lines.extend(['Baseline samples (channel / duration group / n):','']+[f"- {b['channel_id']} / {b['cohort']} / {b['sample_size']}" for b in c['baseline_samples']]+[''])
    lines.extend(['## Cross-cohort signals',''])
    for s in result['cross_cohort_signals']:
        lines.append(f"- {s['canonical_topic']} | strength {s['signal_strength']:.1f} | {s['distinct_cohort_count']} cohorts | {s['independent_channel_count']} independent/media channels + {s['vendor_channel_count']} vendor channels | median adjusted {s['median_adjusted_score']:.2f}")
    if not result['cross_cohort_signals']:lines.append('No qualifying cross-cohort signals.')
    lines+=['','## Most researchable current stories',''];show(sorted([r for r in result['opportunities'] if r['researchability_score']>=result['metadata']['market_config']['cohorts']['researchable_threshold']],key=lambda r:(-r['researchability_score'],-r['opportunity_score'],r['video_id']))[:10])
    lines+=['## High-demand but low-researchability stories',''];show([r for r in result['opportunities'] if r['is_outlier'] and r['researchability_score']<40][:10])
    lines+=['## Poor production-fit stories',''];show([r for r in result['opportunities'] if r['production_fit']=='POOR'][:10])
    lines+=['## Collection and scope','','```json',json.dumps(result['metadata']['collection_samples'],indent=2),'```','', 'Partial failures: '+json.dumps(result['metadata']['partial_failures']),'', 'Scope: '+str(result['metadata']['market_config']['scope_cohorts'])]
    atomic_write(directory/'cohorts.md','\n'.join(lines)+'\n')
