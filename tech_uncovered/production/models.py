from dataclasses import dataclass,field,asdict
from typing import Protocol,Literal

ARCHETYPES=('HeroReveal','AvatarHost','ProductCard','DocumentationCard','ScreenshotFocus','FeatureList','ComparisonCards','ArchitectureDiagram','Timeline','MetricCounter','QuoteCard','ThreeStepProcess','FinalPayoff')

@dataclass
class VisualText:
    text: str
    factual: bool
    source_sentence_id: str
    claim_ids: list[str]=field(default_factory=list)
    source_ids: list[str]=field(default_factory=list)
    evidence_passage_ids: list[str]=field(default_factory=list)

@dataclass
class CaptionSegment:
    text: str
    start_frame: int
    end_frame: int
    beat_id: str
    emphasis_words: list[int]=field(default_factory=list)

@dataclass
class NarrationBeat:
    beat_id: str
    sentence_id: str
    narration: str
    start_frame: int
    end_frame: int
    claim_ids: list[str]
    source_ids: list[str]
    evidence_passage_ids: list[str]
    factual: bool

@dataclass
class AssetRequirement:
    asset_id: str
    path: str
    kind: str
    placeholder: bool
    license: str
    sha256: str

@dataclass
class ScenePlan:
    scene_id: str
    scene_type: str
    beat_ids: list[str]
    narration: str
    on_screen_text: list[VisualText]
    visual_intent: str
    asset_requirements: list[str]
    start_frame: int
    end_frame: int
    transition: str
    caption_segments: list[CaptionSegment]
    claim_ids: list[str]
    music_slots: list[dict]=field(default_factory=list)
    sfx_slots: list[dict]=field(default_factory=list)
    visual_events: list[dict]=field(default_factory=list)
    creative_treatment: dict=field(default_factory=dict)
    avatar: dict|None=None
    caption_bounds: dict=field(default_factory=lambda:dict(x=104,y=1310,width=872,height=202))

@dataclass
class ProductionSpec:
    video_id: str
    script_id: str
    revision: int
    title: str
    duration_target: float
    narration_beats: list[NarrationBeat]
    claim_ids: list[str]
    scenes: list[ScenePlan]
    assets: list[AssetRequirement]
    provenance: dict
    creative_dna: dict
    avatar_assets: list[dict]=field(default_factory=list)
    routed_assets: list[dict]=field(default_factory=list)
    audio_mix: dict=field(default_factory=dict)
    retention_metadata: dict=field(default_factory=dict)
    creative_asset_requests: list[dict]=field(default_factory=list)
    schema_version: str='1.1'
    width: int=1080
    height: int=1920
    fps: int=30
    safe_bounds: dict=field(default_factory=lambda:dict(left=96,right=984,top=160,bottom=1580))
    voice_timing: dict=field(default_factory=lambda:dict(status='ESTIMATED',audio_path=None,provider='word-proportional',notes='Silent preview; recorded narration and alignment required for final delivery'))
    production_status: str='PREVIEW_ONLY'
    def to_dict(self):return asdict(self)

class VoiceTimingProvider(Protocol):
    def align(self,beats:list[NarrationBeat],audio_path:str,fps:int)->list[NarrationBeat]:...
