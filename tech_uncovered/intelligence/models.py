from dataclasses import asdict, dataclass, field
from hashlib import sha256
import json


def digest(value):
    return sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def stable_id(prefix, value):
    return prefix + '-' + digest(value)[:16]


@dataclass
class TranscriptResult:
    transcript_status: str = 'UNAVAILABLE'
    transcript_source: str | None = None
    transcript_language: str | None = None
    text: str | None = None
    segments: list[dict] = field(default_factory=list)
    structured_context: dict = field(default_factory=dict)
    retrieved_at: str = ''
    reason: str | None = 'No supplied transcript'
    provider_name: str = 'unavailable'
    provider_version: str = '1'
    content_hash: str = ''


@dataclass
class ResearchResult:
    assessments: dict = field(default_factory=dict)
    sources: list[dict] = field(default_factory=list)
    provider_name: str = 'no-op'
    provider_version: str = '1'
    retrieved_at: str = ''


@dataclass
class StoryBrief:
    video_id: str
    metadata_subject_resolution: dict = field(default_factory=dict)
    story_context_status: str | None = None
    story_type: str | None = None
    canonical_subject: str | None = None
    named_entities: list[str] = field(default_factory=list)
    alleged_event: str | None = None
    source_opportunity: dict = field(default_factory=dict)
    entities: list[str] = field(default_factory=list)
    technologies: list[str] = field(default_factory=list)
    companies: list[str] = field(default_factory=list)
    people: list[str] = field(default_factory=list)
    products_models: list[str] = field(default_factory=list)
    core_event: str | None = None
    what_changed: str | None = None
    why_now: str | None = None
    audience_relevance: str | None = None
    factual_claims: list[dict] = field(default_factory=list)
    uncertain_claims: list[dict] = field(default_factory=list)
    source_evidence: list[dict] = field(default_factory=list)
    competitor_angle: str = 'unknown'
    hook_pattern: str = 'unknown'
    emotional_frame: str = 'unknown'
    novelty_type: str = 'unknown'
    evergreen_or_news: str = 'unknown'
    time_sensitivity: str = 'unknown'
    content_depth: str = 'unknown'
    confidence: float = 0.2
    flags: list[str] = field(default_factory=list)
    context_summary: str | None = None
    event_key: str | None = None
    event_type: str | None = None
    event_date: str | None = None
    mechanism_question: str | None = None
    field_provenance: dict = field(default_factory=dict)
    unknown_reasons: dict = field(default_factory=dict)
    radar_run_id: str = ''
    intelligence_run_id: str = ''
    provider_versions: dict = field(default_factory=dict)

    def to_dict(self):
        return asdict(self)


@dataclass
class IdeaCandidate:
    idea_id: str
    source_video_ids: list[str]
    topic: str
    proposed_angle: str
    audience_question: str
    one_sentence_premise: str
    why_now: str
    originality_notes: str
    required_research: list[str]
    potential_visuals: list[str]
    canonical_subject: str | None = None
    named_entities: list[str] = field(default_factory=list)
    alleged_event: str | None = None
    source_opportunities: list[dict] = field(default_factory=list)
    source_researchability_score: float | None = None
    idea_researchability_score: float = 0.0
    story_type: str | None = None
    story_context_status: str | None = None
    subject_type: str = 'UNKNOWN'
    story_requirement: str | None = None
    story_requirement_satisfied: bool = False
    story_resolution_mode: str | None = None
    m3_entry_ready: bool = False
    m3_entry_blockers: list[str] = field(default_factory=list)
    m3_entry_contract_version: str | None = None
    comparison_context: dict = field(default_factory=dict)
    canonical_story_id: str | None = None
    canonical_story_label: str | None = None
    angle_type: str | None = None
    m2_researchability_score: float | None = None
    m2_researchability_version: str = 'radar-context-v1'
    preview_researchability_score: float | None = None
    preview_researchability_version: str = 'context-resolvability-v1'
    topic_rank: int | None = None
    angle_rank_within_topic: int | None = None
    preview_selection_phase: str | None = None
    review_status: str = 'BACKLOG'
    format_fit: str = 'Short'
    estimated_short_length: int = 45
    long_form_expandable: bool = True
    risk_flags: list[str] = field(default_factory=list)
    confidence: float = 0.2
    production_ready: bool = False
    similarity_status: str = 'REVIEW'
    similarity_details: dict = field(default_factory=dict)
    cluster_id: str = ''
    story_brief_ids: list[str] = field(default_factory=list)
    material_claim_ids: list[str] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)
    do_not_copy: list[str] = field(default_factory=list)
    story_context: list[dict] = field(default_factory=list)
    transformation: str = ''
    production_assumptions: dict = field(default_factory=dict)
    expansion_sections: list[str] = field(default_factory=list)
    duplicate_of: str | None = None
    scores: dict = field(default_factory=dict)
    score_rationale: dict = field(default_factory=dict)
    idea_score: float = 0.0
    category: str = 'BACKLOG'
    rank: int | None = None
    radar_run_id: str = ''
    intelligence_run_id: str = ''
    scoring_version: str = '1.0'
    provider_versions: dict = field(default_factory=dict)

    def to_dict(self):
        return asdict(self)
