from dataclasses import dataclass,field,asdict
from typing import Protocol

@dataclass
class VideoPerformance:
    video_id:str
    platform:str
    published_at:str|None
    measurement_window:str
    measured_at:str
    views:int|None=None
    watch_time:float|None=None  # seconds, total
    average_view_duration:float|None=None  # seconds
    average_percentage_viewed:float|None=None  # percent, may exceed 100 on loops
    likes:int|None=None
    comments:int|None=None
    shares:int|None=None
    saves:int|None=None
    followers_or_subscribers_gained:int|None=None
    impressions:int|None=None
    viewed_vs_swiped:dict|None=None
    retention_first_3_seconds:float|None=None  # percentage if provider explicitly exposes it
    source_metric_payload:dict=field(default_factory=dict)
    metric_provenance:dict=field(default_factory=dict)
    schema_version:str='1.0'
    def to_dict(self):return asdict(self)

class DistributionAdapter(Protocol):
    platform:str
    def prepare(self,spec:dict,artifact_path:str)->dict:...
    def publish(self,package:dict)->str:...

class AnalyticsAdapter(Protocol):
    platform:str
    def normalize(self,video_id:str,payload:dict,measurement_window:str,measured_at:str)->VideoPerformance:...
