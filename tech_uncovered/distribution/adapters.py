import math
from copy import deepcopy
from .models import VideoPerformance

class OfflineDistribution:
    def prepare(self,spec,artifact_path):
        return dict(video_id=spec['video_id'],platform=self.platform,artifact_path=artifact_path,title=spec['title'],status='DRAFT_OFFLINE',publish_allowed=False,source_revision=spec['revision'])
    def publish(self,package):raise NotImplementedError('Live publishing is intentionally not implemented')
class YouTubeDistributionAdapter(OfflineDistribution):platform='youtube'
class InstagramDistributionAdapter(OfflineDistribution):platform='instagram'

class OfflineAnalytics:
    def normalize(self,video_id,payload,measurement_window,measured_at):
        if not video_id or not measurement_window or not measured_at:raise ValueError('Identity/window/timestamp required')
        values={};provenance={}
        for target,(source,multiplier) in self.mapping.items():
            value=payload.get(source)
            if value is not None:
                if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or value<0:raise ValueError('Invalid metric: '+source)
                value=value*multiplier
                if target in ('views','likes','comments','shares','saves','followers_or_subscribers_gained','impressions'):
                    if int(value)!=value:raise ValueError('Count metric is fractional')
                    value=int(value)
                provenance[target]={'source_key':source,'multiplier':multiplier,'availability':'explicit_input_only'}
            values[target]=value
        # No inference from views, plays or impressions. Optional retention needs explicit provider data.
        if 'viewed_vs_swiped' in payload:
            split=payload['viewed_vs_swiped']
            if not isinstance(split,dict) or set(split)!={'viewed_percent','swiped_percent'} or any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or not 0<=v<=100 for v in split.values()) or abs(sum(split.values())-100)>0.1:raise ValueError('Invalid viewed/swiped percentages')
            values['viewed_vs_swiped']=deepcopy(split)
        return VideoPerformance(video_id,self.platform,payload.get('published_at'),measurement_window,measured_at,**values,source_metric_payload=deepcopy(payload),metric_provenance=provenance)
    def fetch(self,*args,**kwargs):raise NotImplementedError('Live analytics fetching is intentionally not implemented')

class YouTubeAnalyticsAdapter(OfflineAnalytics):
    platform='youtube'
    mapping={'views':('views',1),'watch_time':('estimatedMinutesWatched',60),'average_view_duration':('averageViewDuration',1),'average_percentage_viewed':('averageViewPercentage',1),'likes':('likes',1),'comments':('comments',1),'shares':('shares',1),'followers_or_subscribers_gained':('subscribersGained',1),'impressions':('impressions',1),'retention_first_3_seconds':('retention_first_3_seconds',1)}
class InstagramAnalyticsAdapter(OfflineAnalytics):
    platform='instagram'
    # Export adapters use explicit units. A live API/version mapper must supply these keys.
    mapping={'views':('views',1),'watch_time':('watch_time_seconds',1),'average_view_duration':('average_watch_time_seconds',1),'average_percentage_viewed':('average_percentage_viewed',1),'likes':('likes',1),'comments':('comments',1),'shares':('shares',1),'saves':('saved',1),'followers_or_subscribers_gained':('follows',1),'impressions':('impressions',1),'retention_first_3_seconds':('retention_first_3_seconds',1)}
