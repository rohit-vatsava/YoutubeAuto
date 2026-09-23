from . import GENERATION_VERSION
from dataclasses import asdict, dataclass, field
from ..intelligence.models import digest, stable_id


class Record:
    def to_dict(self):
        return asdict(self)


@dataclass
class SourceRecord(Record):
    source_id: str
    url: str
    title: str
    publisher: str
    publication_date: str | None
    retrieved_at: str
    source_type: str = 'OTHER'
    primary_or_secondary: str = 'UNKNOWN'
    authority_score: float = 20
    freshness_score: float = 0
    relevance_score: float = 0
    source_priority: float = 0
    notes: list = field(default_factory=list)
    text: str = ''
    content_hash: str = ''
    syndication_group: str = ''
    metadata_basis: str = 'retrieved_document'
    canonical_url: str = ''
    retrieved_url: str = ''
    headings: list = field(default_factory=list)
    source_owner: str = ''
    authority_type: str = 'UNKNOWN'
    selection_warnings: list = field(default_factory=list)
    source_topic_relevance: float = 0


@dataclass
class ResearchClaim(Record):
    claim_id: str
    text: str
    materiality: str = 'IMPORTANT'
    claim_type: str = 'FACT'
    evidence_ids: list = field(default_factory=list)
    contradicting_evidence_ids: list = field(default_factory=list)
    status: str = 'UNVERIFIED'
    confidence: float = 0
    rationale: str = ''
    passages: list = field(default_factory=list)
    supported_wording: str = ''
    limitations: list = field(default_factory=list)
    requires_attribution: bool = False


@dataclass
class CostRecord(Record):
    search_calls: int = 0
    fetched_pages: int = 0
    fetch_attempts: int = 0
    model_calls: int = 0
    model_input_tokens: int = 0
    model_output_tokens: int = 0
    estimated_model_cost_usd: float | None = 0.0
    estimated_search_cost_usd: float | None = 0.0
    known_cost_usd: float = 0.0
    actual_cost_usd: float = 0.0
    reserved_cost_usd: float = 0.0
    released_reserve_usd: float = 0.0
    active_reservation_usd: float = 0.0
    conservative_unknown_cost_usd: float = 0.0
    estimated_cost_upper_bound_usd: float = 0.0
    total_research_seconds: float = 0.0
    total_generation_seconds: float = 0.0
    usage_complete: bool = True
    attempts: list = field(default_factory=list)
    pricing: dict = field(default_factory=dict)
    story_resolution_cost: dict = field(default_factory=lambda: {'estimated_cost_usd':0.0,'model_calls':0,'search_calls':0,'elapsed_seconds':0.0})
    full_research_cost: dict = field(default_factory=lambda: {'estimated_cost_usd':0.0,'model_calls':0,'search_calls':0,'elapsed_seconds':0.0})
    script_generation_cost: dict = field(default_factory=lambda: {'estimated_cost_usd':0.0,'model_calls':0,'search_calls':0,'elapsed_seconds':0.0})
    fact_check_cost: dict = field(default_factory=lambda: {'estimated_cost_usd':0.0,'model_calls':0,'search_calls':0,'elapsed_seconds':0.0})
    quality_review_cost: dict = field(default_factory=lambda: {'estimated_cost_usd':0.0,'model_calls':0,'search_calls':0,'elapsed_seconds':0.0})



# Small explicit wire examples also define strict structured-output shapes for the live adapter.
CLAIM_EXAMPLE = dict(claim_id='c1', text='A precise claim', materiality='CRITICAL', claim_type='FACT',
    evidence_ids=['source-id'], contradicting_evidence_ids=[], status='UNVERIFIED', confidence=0.0,
    rationale='Explain support and scope', passages=[{'source_id':'source-id','quote':'Exact passage','relation':'SUPPORTS'}],
    supported_wording='The safely supported proposition', limitations=[], requires_attribution=False)
PACKET_EXAMPLE = dict(topic='Specific topic', final_research_question='Question', confirmed_story='Supported event',
    what_changed='Change', why_now='Timeliness', why_it_matters='Audience relevance',
    claims=[CLAIM_EXAMPLE], useful_numbers=[], timeline=[], entities=[],
    unsupported_competitor_claims=[], safe_angle='Supported original angle', angles_to_avoid=[],
    research_gaps=[], confidence=0.0, freshness={'established':False,'event_date':'','evidence_ids':[]},
    canonical_story_resolved=False, core_claim_ids=[], resolved_requirement_ids=[],
    remaining_questions_material=True, research_status='INSUFFICIENT')
ANGLE_EXAMPLE = dict(angle='Angle', audience_question='Question', payoff='Payoff', why_this_angle='Rationale',
    evidence_basis=['c1'], do_not_say=[], required_nuance=[], visual_opportunities=[],
    refinement_status='UNCHANGED', originality_status='REVIEW', originality_rationale='Compare competitor context')
SENTENCE_EXAMPLE = dict(sentence_id='s1',text='Spoken sentence.',statement_type='FACT',materiality='IMPORTANT',
    claim_ids=['c1'],source_ids=['source-id'],evidence_passage_ids=['passage-id'])
HOOK_EXAMPLE = dict(hook_id='h1',text='A supported hook?',claim_ids=['c1'],source_ids=['source-id'],
    evidence_passage_ids=['passage-id'],scores={'Clarity':0.0,'Specificity':0.0,'Curiosity':0.0,'Stakes':0.0,
    'Novelty':0.0,'FactualSafety':0.0,'Brevity':0.0},rationale='Explain each component; no viral prediction')
DRAFT_EXAMPLE = dict(title_working='Working title', title_claim_ids=[],
    hook_candidates=[HOOK_EXAMPLE], selected_hook_id='h1', sections=[{'name':'CONTEXT','sentences':[SENTENCE_EXAMPLE]}],
    visual_notes=[],pronunciation_notes=[],uncertainty_notes=[])
CHECK_EXAMPLE = dict(sentence_checks=[{'sentence_id':'s1','supported':False,'material':True,
    'claim_ids':['c1'],'source_ids':['source-id'],'issues':[]}], hook_checks=[{'hook_id':'h1','supported':False,'issues':[]}],
    title_supported=False, unsupported_sentences=[],overstated_sentences=[],attribution_issues=[],timeline_issues=[],
    numerical_issues=[],ambiguity_issues=[],corrections=[], verdict='RESEARCH_REQUIRED')
QUALITY_WEIGHTS = {'HookStrength':.15,'Clarity':.20,'NarrativeFlow':.15,'InformationDensity':.10,
                   'Originality':.15,'AudienceFit':.10,'PayoffStrength':.10,'ProductionFeasibility':.05}
QUALITY_EXAMPLE = dict(components={k:0.0 for k in QUALITY_WEIGHTS}, rationale={k:'Reason' for k in QUALITY_WEIGHTS},
    spoken_naturalness={'flags':[],'notes':'Spoken read-through assessment'}, originality_status='REVIEW',
    originality_rationale='Compare final wording with competitor references',warnings=[])


def json_schema(example):
    if isinstance(example,dict):
        return {'type':'object','properties':{k:json_schema(v) for k,v in example.items()},
                'required':list(example),'additionalProperties':False}
    if isinstance(example,list):
        return {'type':'array','items':json_schema(example[0]) if example else {'type':'string'}}
    if isinstance(example,bool):return {'type':'boolean'}
    if isinstance(example,(int,float)):return {'type':'number'}
    return {'type':'string'}

PACKET_EXAMPLE['source_assessments']=[dict(source_id='source-id',source_type='OTHER',primary_or_secondary='UNKNOWN',
    credible_for_claim_ids=['c1'],authority_score=0.0,relevance_score=0.0,freshness_score=0.0,rationale='Claim-relative authority and limitations')]
PACKET_EXAMPLE['requirement_resolutions']=[dict(requirement_id='requirement-id',claim_ids=['c1'],rationale='How evidence resolves requirement')]

DRAFT_EXAMPLE['on_screen_text']=[SENTENCE_EXAMPLE]
CHECK_EXAMPLE['visual_notes_supported']=False

PACKET_EXAMPLE['early_stop_reason']=''

PACKET_EXAMPLE['comparison_evidence'] = dict(
    decision='', alternative='', criterion='', conditions='', like_for_like=False,
    selection_claim_ids=[], subject_claim_ids=[], alternative_claim_ids=[], rationale='')
