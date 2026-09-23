"""Transparent metadata heuristics; neither fact verification nor revenue prediction."""
import math
import re
from collections import defaultdict,Counter
from statistics import median
from .settings import parse_time


def contains(text,term):return bool(re.search(r'(?<!\w)'+re.escape(term)+r'(?!\w)',text,re.I))
def normalize(score):return 100*min(math.log2(1+score)/math.log2(9),1)
def hints(title,rules):
    entities=[k for k,aliases in rules['entities'].items() if any(contains(title,a) for a in aliases)]
    products=[k for k,aliases in rules['products'].items() if any(contains(title,a) for a in aliases)]
    events=[k for k,aliases in rules['events'].items() if any(contains(title,a) for a in aliases)]
    exact=sorted(set(re.findall(r'\bCVE-\d{4}-\d{4,}\b|\b(?:GPT|RTX|RX|Ryzen|Claude|Gemini|Llama|Windows|iPhone|Python|Node|Bun|Deno|Linux|CUDA)[ -]?\d+(?:\.\d+)*(?:[ -]?(?:Pro|Max|Ti|Sonnet|Opus))?\b|\bv\d+\.\d+(?:\.\d+)?\b',title,re.I)))
    subject=bool(entities) or any(x.upper().startswith('CVE-') for x in exact)
    score=35*subject+25*bool(products)+20*bool(events)+20*bool(exact)
    reasons=[]
    for yes,label in ((subject,'+35 named company/person/project or CVE'),(products,'+25 named product/technology'),(events,'+20 identifiable event'),(exact,'+20 version/CVE/generation')):
        if yes:reasons.append(label)
    if any(contains(title,p) for p in rules['hype']):score-=20;reasons.append('-20 generic hype')
    if any(contains(title,p) for p in rules['vague']) and not (entities or products or exact):score-=20;reasons.append('-20 unnamed/vague subject')
    if not (entities or products or exact):score=min(score,25);reasons.append('No identifiable subject; capped at 25')
    fit,reason='MEDIUM','Metadata does not establish a low-cost production treatment'
    hardware_review=any(contains(title,p) for p in rules.get('hardware_terms',[])) and any(contains(title,p) for p in rules.get('hardware_review_markers',[]))
    if hardware_review or any(contains(title,p) for p in rules['poor_production']):fit,reason='POOR','Hands-on review/unboxing/original testing indicated'
    elif any(contains(title,p) for p in rules['medium_production']):fit,reason='MEDIUM','Personality-led opinion/reaction indicated'
    elif (entities or products or exact) and (events or products):fit,reason='GOOD','Identifiable software/product/event can support a visual explanation'
    topics=[]
    if exact:topics=['identifier:'+x.lower() for x in exact]
    elif products:topics=['product:'+x.lower()+(':'+sorted(events)[0] if events else '') for x in products]
    elif entities and events:topics=['subject:'+x.lower()+':'+e for x in entities for e in events]
    return dict(researchability_score=max(0,min(100,score)),researchability_reasons=reasons,named_entity_hints=sorted(set(entities+products+exact)),event_hints=events,
                production_fit=fit,production_fit_reason=reason,canonical_topics=topics)


def weighted_median(values):
    values=sorted(values);total=sum(w for _,w in values);cumulative=0
    for index,(value,weight) in enumerate(values):
        cumulative+=weight
        if cumulative>=total/2:
            return (value+values[index+1][0])/2 if cumulative==total/2 and index+1<len(values) else value


def balanced_median(rows,key,configs):
    channels=defaultdict(list)
    for r in rows:
        if r.get(key) is not None:channels[r['channel_id']].append(r[key])
    return weighted_median([(median(v),configs[c]['weight']) for c,v in channels.items()]) if channels else None


def balanced_top(rows,limit=5):
    groups=defaultdict(list)
    for r in sorted(rows,key=lambda r:(-r['opportunity_score'],r['video_id'])):groups[r['channel_id']].append(r)
    result=[]
    while groups and len(result)<limit:
        round_rows=sorted((v.pop(0) for v in groups.values()),key=lambda r:(-r['opportunity_score'],r['video_id']))
        result.extend(round_rows[:limit-len(result)]);groups={k:v for k,v in groups.items() if v}
    return result


def enrich(result,watchlist,cohorts,rules):
    configs={c['channel_id']:c for c in watchlist['channels'] if c.get('channel_id') and c['enabled']}
    window=cohorts['current_window_days'];threshold=cohorts['researchable_threshold'];now=parse_time(result['generated_at'])
    rows=result['videos']
    for r in rows:
        c=configs.get(r['channel_id'],{'cohort':'UNASSIGNED','source_role':'independent_creator','weight':1.0})
        configs.setdefault(r['channel_id'],c)
        r.update(hints(r['title'],rules));r.update(market_cohort=c['cohort'],source_role=c['source_role'],commercial_value_tag=cohorts['cohorts'].get(c['cohort'],{}).get('commercial_value','UNSPECIFIED'))
        current_age=(now-parse_time(r['published_at'])).total_seconds()/86400
        r.update(current_age_days=current_age,current_opportunity=bool(r['eligibility_reason']=='eligible' and 1<=current_age<=window),opportunity_score=None,normalized_radar_signal=None,cross_cohort_support=0.0)
    groups=defaultdict(list)
    for r in rows:
        if r['current_opportunity'] and r['is_outlier']:
            for topic in r['canonical_topics']:groups[topic].append(r)
    signals=[]
    for topic,members in sorted(groups.items()):
        channel_ids=sorted({r['channel_id'] for r in members});cohort_ids=sorted({r['market_cohort'] for r in members})
        if len(cohort_ids)<2:continue
        per_channel=[median([r['velocity_adjusted_score'] for r in members if r['channel_id']==cid]) for cid in channel_ids]
        age=median([min(r['current_age_days'] for r in members if r['channel_id']==cid) for cid in channel_ids]);score=median(per_channel)
        parts=dict(cohort_breadth=min((len(cohort_ids)-1)/2,1),channel_breadth=min((len(channel_ids)-1)/3,1),radar=normalize(score)/100,recency=2**(-age/14))
        strength=100*(.45*parts['cohort_breadth']+.20*parts['channel_breadth']+.25*parts['radar']+.10*parts['recency'])
        vendor=[cid for cid in channel_ids if configs[cid]['source_role']=='vendor_official'];independent=[cid for cid in channel_ids if cid not in vendor]
        signals.append(dict(canonical_topic=topic,supporting_video_ids=sorted(r['video_id'] for r in members),supporting_channels=channel_ids,supporting_cohorts=cohort_ids,
            distinct_channel_count=len(channel_ids),distinct_cohort_count=len(cohort_ids),independent_channel_count=len(independent),vendor_channel_count=len(vendor),
            independent_channels=independent,vendor_channels=vendor,median_adjusted_score=score,maximum_adjusted_score=max(r['velocity_adjusted_score'] for r in members),
            recency={'median_channel_newest_age_days':age},signal_strength=strength,components=parts))
    signals.sort(key=lambda s:(-s['signal_strength'],s['canonical_topic']))
    for r in rows:
        r['cross_cohort_support']=max([0]+[s['signal_strength'] for s in signals if s['canonical_topic'] in r['canonical_topics']])
        if r['current_opportunity']:
            r['normalized_radar_signal']=normalize(r['velocity_adjusted_score'])
            r['opportunity_score']=.55*r['normalized_radar_signal']+.25*r['researchability_score']+.20*r['cross_cohort_support']
        r['opportunity_components']={k:r[k] for k in ('normalized_radar_signal','researchability_score','cross_cohort_support')}
    opportunities=sorted((r for r in rows if r['opportunity_score'] is not None),key=lambda r:(-r['opportunity_score'],-r['velocity_adjusted_score'],r['video_id']))
    for i,r in enumerate(opportunities,1):r['opportunity_rank']=i
    summaries=[]
    for cohort_id,cohort in cohorts['cohorts'].items():
        members=[r for r in rows if r['market_cohort']==cohort_id];eligible=[r for r in members if r['eligibility_reason']=='eligible'];current=[r for r in eligible if r['current_opportunity']];outliers=[r for r in current if r['is_outlier']]
        subjects=defaultdict(set)
        for r in outliers:
            for t in r['canonical_topics']:subjects[t].add(r['channel_id'])
        monitored=[c for c in result['metadata']['channels'] if c['channel_id'] in configs and configs[c['channel_id']]['cohort']==cohort_id]
        summaries.append(dict(market_cohort=cohort_id,label=cohort['label'],commercial_value=cohort['commercial_value'],channels_monitored=len(monitored),
            vendor_channels_monitored=sum(configs[c['channel_id']]['source_role']=='vendor_official' for c in monitored),independent_channels_monitored=sum(configs[c['channel_id']]['source_role']!='vendor_official' for c in monitored),
            independent_outliers=sum(r['source_role']!='vendor_official' for r in outliers),vendor_outliers=sum(r['source_role']=='vendor_official' for r in outliers),
            independent_median_adjusted_score=balanced_median([r for r in current if r['source_role']!='vendor_official'],'velocity_adjusted_score',configs),vendor_median_adjusted_score=balanced_median([r for r in current if r['source_role']=='vendor_official'],'velocity_adjusted_score',configs),eligible_videos=len(eligible),current_eligible_videos=len(current),
            qualifying_outliers=len(outliers),median_adjusted_score=balanced_median(current,'velocity_adjusted_score',configs),maximum_adjusted_score=max([r['velocity_adjusted_score'] for r in current],default=None),
            median_views_per_day=balanced_median(current,'views_per_day',configs),researchable_outliers=sum(r['researchability_score']>=threshold for r in outliers),
            recurring_subjects=[{'canonical_topic':t,'distinct_channels':len(cs)} for t,cs in sorted(subjects.items()) if len(cs)>=2],
            recent_activity={'published_7_days':sum(0<=r['current_age_days']<=7 for r in members),'published_30_days':sum(0<=r['current_age_days']<=window for r in members)},
            baseline_samples=[b for b in result['baselines'] if b['channel_id'] in {r['channel_id'] for r in members}],top_opportunities=[r['video_id'] for r in balanced_top([r for r in opportunities if r['market_cohort']==cohort_id])]))
    result['metadata']['collection_samples']=[{'channel_id':c['channel_id'],'channel':c['name'],'max_uploads':c.get('max_uploads',result['metadata']['settings']['max_uploads']),'window_days':c.get('window_days',result['metadata']['settings']['lookback_days']),'collected':sum(r['channel_id']==c['channel_id'] for r in rows),'oldest_publish_date':min([r['published_at'] for r in rows if r['channel_id']==c['channel_id']],default=None),'newest_publish_date':max([r['published_at'] for r in rows if r['channel_id']==c['channel_id']],default=None)} for c in result['metadata']['channels']]
    result.update(opportunities=opportunities,cross_cohort_signals=signals,cohort_summaries=summaries,competitor_config_version=watchlist['competitor_config_version'],cohort_config_version=cohorts['cohort_config_version'],scoring_version='1.0')
    from .intelligence.models import digest
    result['metadata']['market_config']={'watchlist':watchlist,'cohorts':cohorts,'rules':rules,'configuration_hash':digest([watchlist,cohorts,rules]),'opportunity_version':'1.0','scope_cohorts':sorted({c['cohort'] for c in watchlist['channels'] if c['enabled']}),'current_window_days':window}
    result['metadata'].update({k:result[k] for k in ('competitor_config_version','cohort_config_version','scoring_version')})
    return result
