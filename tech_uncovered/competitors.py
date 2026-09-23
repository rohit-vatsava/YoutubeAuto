"""Versioned watchlist with legacy-list compatibility and exact API identity checks."""
import math
from dataclasses import replace
from datetime import timedelta
from .youtube import YouTubeError

ROLES={'independent_creator','media_explainer','vendor_official'}


def parse_config(raw,cohort_config):
    legacy=isinstance(raw,list)
    version='legacy-1.0' if legacy else raw['competitor_config_version']
    entries=raw if legacy else raw['channels'];result=[];seen=set()
    for item in entries:
        c=dict(item);c['display_name']=c.get('display_name',c.get('name'))
        if not c['display_name']:raise ValueError('Channel display_name is required')
        c['name']=c['display_name'];c.setdefault('cohort','UNASSIGNED');c.setdefault('enabled',True);c.setdefault('weight',1.0);c.setdefault('source_role','independent_creator')
        if not legacy and c['cohort'] not in cohort_config['cohorts']:raise ValueError('Unknown cohort: '+c['cohort'])
        if type(c['enabled']) is not bool or not isinstance(c['weight'],(int,float)) or not math.isfinite(c['weight']) or c['weight']<=0:raise ValueError('Invalid enabled/weight')
        if c['source_role'] not in ROLES:raise ValueError('Invalid source_role')
        for key in ('max_uploads','window_days'):
            if key in c and (type(c[key]) is not int or c[key]<=0):raise ValueError('Invalid '+key)
        identity=c.get('channel_id') or (c.get('handle') or c['display_name']).lower()
        if identity in seen:raise ValueError('Duplicate channel identity')
        seen.add(identity);result.append(c)
    return {'competitor_config_version':version,'channels':result}


def effective_settings(c,cohorts,settings,max_uploads=None,window_days=None):
    defaults=cohorts['cohorts'].get(c['cohort'],{})
    return replace(settings,max_uploads=max_uploads if max_uploads is not None else c.get('max_uploads',defaults.get('max_uploads',settings.max_uploads)),
                   lookback_days=window_days if window_days is not None else c.get('window_days',defaults.get('window_days',settings.lookback_days)))


def resolve(client,c):
    result={'display_name':c['display_name'],'requested_handle':c.get('handle'),'cohort':c['cohort'],'source_role':c['source_role'],'status':'UNRESOLVED','alternatives':[],'channel_id':None,'canonical_name':None}
    if not c['enabled']:result['status']='DISABLED';return result
    try:
        if not c.get('handle') and not c.get('channel_id'):
            payload,_=client.get('search',{'part':'snippet','type':'channel','q':c['display_name'],'maxResults':5},timedelta(days=7))
            result['alternatives']=[{'channel_id':x['id']['channelId'],'canonical_name':x['snippet']['title']} for x in payload['items']]
            result['reason']='Display-name discovery requires an explicit handle/ID choice; no automatic selection'
            return result
        # A supplied handle must resolve to the supplied ID. Never silently trust a mismatching pair.
        request=dict(c)
        if c.get('handle'):request.pop('channel_id',None)
        channel=client.resolve_channel(request)
        if c.get('channel_id') and channel['channel_id']!=c['channel_id']:
            result.update(reason='Handle/channel_id mismatch',alternatives=[channel]);return result
        result.update(status='RESOLVED',canonical_name=channel['name'],channel_id=channel['channel_id'],channel=channel)
    except YouTubeError as exc:result['reason']=str(exc);result['error_type']=type(exc).__name__
    return result
