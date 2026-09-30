"""M4.1: bounded visual direction; never authors narration or evidence.

Model text is data only. No paths, credentials, shell commands or arbitrary URLs
are accepted by the plan schema. Generated prompts use reviewed templates; open
ended model proposals require a future review step, not implicit execution.
"""
from dataclasses import dataclass, field, asdict
from typing import Protocol
import copy
import json
import math
from .models import ARCHETYPES
from .planning import digest

KINDS = ('FACTUAL_EVIDENCE','FACTUAL_EXPLANATION','CREATIVE_METAPHOR','DECORATIVE_BROLL','AVATAR_HOST','TRANSITION')
PROVIDERS = ('LOCAL_MOTION_GRAPHIC','OFFICIAL_SOURCE','AVATAR','HF_LTX','AGNES')
HEADINGS = ('DOCUMENTED ≠ DEPLOYED','DOCUMENTATION CONTEXT','DOCUMENTED TOOLS',
            'REASONING SETTINGS','TASK → TEST → MEASURE','CONFIGURATION CHECKLIST',
            'FEATURE LIST ≠ REAL ENVIRONMENT','DOCUMENTATION BOUNDARY','FEATURE LIST ≠ DEPLOYMENT DECISION')
NEGATIVE = 'Readable text, logos, watermarks, product UI, product demonstrations, benchmarks, performance numbers, visual clutter, cyberpunk cityscapes.'

@dataclass(frozen=True)
class TechUncoveredBrandProfile:
    name: str = 'Tech Uncovered'
    style: str = 'premium technical, dark cinematic, clean modern UI, high contrast, restrained cyan/white, minimal clutter'
    audience: str = 'developer/tech-literate audience'
    first_change_max: float = 1.2
    hook_max: float = 3.0
    cadence_seconds: float = 3.5
    max_static_hold: float = 5.0
    avatar_min: float = 6.0
    avatar_max: float = 12.0
    caption_words: tuple = (2,6)
    prohibitions: tuple = ('generic cyberpunk overload','fake UI as evidence','hype-first visuals')

@dataclass
class CreativeDirectorInput:
    script_id: str
    revision: int
    title: str
    final_narration: str
    sentences: list[dict]
    source_surfaces: list[dict]
    provenance: dict
    topic: str | None
    cohort: str | None
    audience: str
    target_platform: str
    target_duration: float
    available_archetypes: list[str]
    available_providers: list[str]
    avatar_availability: str
    voice_availability: str
    brand: TechUncoveredBrandProfile
    production_constraints: dict
    analytics_priors: dict | None = None

@dataclass
class HeroShot:
    purpose: str
    duration: float
    scene_type: str
    avatar_usage: bool
    visual_description: str
    headline: str
    motion_direction: str
    asset_source_preference: str
    generation_prompt: str | None = None
    negative_prompt: str | None = None

@dataclass
class CreativeAssetRequest:
    asset_id: str
    scene_id: str
    preferred_provider: str
    acceptable_fallback: list[str]
    must_be_factual: bool
    generation_allowed: bool
    expected_duration: float
    resolution: list[int]
    orientation: str
    prompt: str | None
    negative_prompt: str | None

@dataclass
class CreativeScene:
    scene_id: str
    narration_sentence_ids: list[str]
    start: float
    end: float
    purpose: str
    visual_message: str
    scene_archetype: str
    visual_type: str
    avatar_usage: bool
    on_screen_text: list[dict]
    editorial_heading: str
    choreography: list[dict]
    transition: str
    asset_requirements: list[str]
    provider_preference: str
    generation_prompt: str | None
    negative_prompt: str | None
    factuality_class: str
    claim_provenance: list[dict]
    retention_role: str

@dataclass
class CreativePlan:
    script_id: str
    revision: int
    input_sha256: str
    creative_concept: str
    visual_thesis: str
    hook_strategy: str
    hero_shot: HeroShot
    scenes: list[CreativeScene]
    retention_plan: dict
    avatar_plan: list[dict]
    asset_generation_requests: list[CreativeAssetRequest]
    factual_visual_constraints: list[str]
    production_notes: list[str]
    def to_dict(self):return asdict(self)

class CreativeDirectorProvider(Protocol):
    def direct(self, context: CreativeDirectorInput) -> CreativePlan: ...


def input_from_spec(spec, draft, *, brand=None, analytics_priors=None):
    brand=brand or TechUncoveredBrandProfile()
    if spec['provenance']['m3_readiness']!='READY_FOR_PRODUCTION':
        raise ValueError('Creative Director requires READY_FOR_PRODUCTION M3')
    return CreativeDirectorInput(spec['script_id'],spec['revision'],spec['title'],draft['full_script'],
        copy.deepcopy(spec['narration_beats']),[copy.deepcopy(t) for s in spec['scenes'] for t in s['on_screen_text']],
        copy.deepcopy(spec['provenance']),spec['creative_dna'].get('topic'),spec['creative_dna'].get('cohort'),
        brand.audience,'YouTube Shorts',spec['duration_target'],list(ARCHETYPES),list(PROVIDERS),
        'AVAILABLE' if any(a.get('source_path') for a in spec['avatar_assets']) else 'PLACEHOLDER' if spec['avatar_assets'] else 'UNAVAILABLE',
        spec['voice_timing']['status'],brand,dict(fps=spec['fps'],width=1080,height=1920,
        upstream_scenes=copy.deepcopy(spec['scenes']),avatar_assets=copy.deepcopy(spec['avatar_assets'])),analytics_priors)


def metaphor_prompt(context, scene):
    # Intentionally abstract, never a recognizable product interface or claimed behavior.
    return (f'9:16 vertical, {min(4, scene.end-scene.start):.1f}-second shot. Abstract evaluation metaphor: '
        'three unbranded translucent tiles approach a separate empty test frame one at a time; '
        'the frame makes no success judgment. One dominant subject on a dark background. '
        f'{context.brand.style}. Slow controlled camera push-in, sequential cyan edge illumination. '
        'Illustration only, not a real software interface or evidence of product behavior. '
        'No readable text, no logos, no watermarks, no people.')


def role_for(text, index, last):
    lower=text.lower()
    if index==0:return 0,'AvatarHost','AVATAR_HOST','hook'
    if last:return 8,'FinalPayoff','AVATAR_HOST','payoff'
    if 'reasoning.effort' in lower:return 3,'FeatureList','FACTUAL_EXPLANATION','explanation'
    if 'responses api' in lower:return 2,'ArchitectureDiagram','FACTUAL_EXPLANATION','explanation'
    if 'measure' in lower or 'test them' in lower:return 4,'ThreeStepProcess','CREATIVE_METAPHOR','application'
    if 'checklist' in lower:return 5,'ThreeStepProcess','TRANSITION','application'
    if 'reliable' in lower:return 6,'ComparisonCards','FACTUAL_EXPLANATION','boundary'
    if 'does not prove' in lower:return 7,'ComparisonCards','FACTUAL_EXPLANATION','boundary'
    return 1,'DocumentationCard','FACTUAL_EXPLANATION','context'


def retention(context, scenes, avatars):
    changes=sorted({e['time'] for s in scenes for e in s.choreography})
    holds=[b-a for a,b in zip(changes,changes[1:]+[context.target_duration])]
    return dict(first_visual_change_time=next(t for t in changes if t>0),
        hook_end_time=min(context.brand.hook_max,scenes[0].end),
        scene_change_times=[s.start for s in scenes[1:]],payoff_start_time=scenes[-1].start,
        avatar_screen_time=sum(a['end']-a['start'] for a in avatars),
        generated_media_screen_time=0.0,generated_media_proposed_time=sum(min(4,s.end-s.start) for s in scenes if s.generation_prompt),
        factual_visual_screen_time=sum(s.end-s.start for s in scenes if any(t['factual'] for t in s.on_screen_text)),
        visual_density='one dominant idea; at most three emphasized list items',max_static_hold=max(holds),
        caption_density=sum(len(s['caption_segments']) for s in context.production_constraints['upstream_scenes'])/context.target_duration,
        visual_novelty_events=[dict(scene_id=s.scene_id,**e) for s in scenes for e in s.choreography],
        timing_basis=context.voice_availability,prior_source='brand defaults; analytics optional and not auto-applied')


class DeterministicCreativeDirector:
    def direct(self, context):
        scenes=[];assets=[];avatars=[];fps=context.production_constraints['fps']
        available=context.avatar_availability!='UNAVAILABLE'
        for i,upstream in enumerate(context.production_constraints['upstream_scenes']):
            ids=[b['sentence_id'] for b in context.sentences if b['beat_id'] in upstream['beat_ids']]
            provenance=[{k:b[k] for k in ('sentence_id','claim_ids','source_ids','evidence_passage_ids','factual')} for b in context.sentences if b['sentence_id'] in ids]
            role,archetype,kind,retention_role=role_for(upstream['narration'],i,i==len(context.sentences)-1)
            avatar=available and retention_role in ('hook','payoff')
            if kind=='AVATAR_HOST' and not avatar:kind='FACTUAL_EXPLANATION';archetype='HeroReveal' if i==0 else 'FinalPayoff'
            start,end=upstream['start_frame']/fps,upstream['end_frame']/fps
            events=[dict(time=start,action='establish',max_emphasis_items=3)]
            if i==0:
                events.extend([dict(time=min(start+0.8,end-1/fps),action='contrast_reveal',max_emphasis_items=3),dict(time=min(context.brand.hook_max,end-1/fps),action='documentation_pivot',max_emphasis_items=3)])
            cursor=events[-1]['time']+context.brand.cadence_seconds
            while cursor<end:
                events.append(dict(time=round(cursor,4),action='progressive_reveal',max_emphasis_items=3));cursor+=context.brand.cadence_seconds
            # Lists may need faster groups to cover the unchanged source inventory.
            for old in upstream.get('visual_events',[]):
                if old.get('focus',{}).get('item_start') is not None:
                    events.append(dict(time=old['frame']/fps,action='list_group',max_emphasis_items=3,focus=old['focus']))
            events=sorted({e['time']:e for e in events}.values(),key=lambda e:e['time'])
            scene=CreativeScene(upstream['scene_id'],ids,start,end,HEADINGS[role],HEADINGS[role],archetype,kind,avatar,
                copy.deepcopy(upstream['on_screen_text']),HEADINGS[role],events,'fade-through-background',
                ['creative-'+upstream['scene_id']],'AVATAR' if avatar else 'LOCAL_MOTION_GRAPHIC',None,None,kind,provenance,retention_role)
            if kind=='CREATIVE_METAPHOR':
                scene.generation_prompt=metaphor_prompt(context,scene);scene.negative_prompt=NEGATIVE
                scene.provider_preference='HF_LTX' if 'HF_LTX' in context.available_providers else 'LOCAL_MOTION_GRAPHIC'
            factual=kind in ('FACTUAL_EVIDENCE','FACTUAL_EXPLANATION')
            fallback=[p for p in (['AGNES','LOCAL_MOTION_GRAPHIC'] if scene.generation_prompt else ['LOCAL_MOTION_GRAPHIC']) if p in context.available_providers and p!=scene.provider_preference]
            assets.append(CreativeAssetRequest(scene.asset_requirements[0],scene.scene_id,scene.provider_preference,fallback,
                factual,bool(scene.generation_prompt),min(4,end-start) if scene.generation_prompt else end-start,
                [576,1024] if scene.generation_prompt else [1080,1920],'9:16',scene.generation_prompt,scene.negative_prompt))
            if avatar:
                astart=start if i==0 else end-3
                avatars.append(dict(scene_id=scene.scene_id,start=astart,end=astart+3,position='right',screen_width=.30,
                    background='transparent-or-masked',adjacent_text=HEADINGS[role],entrance='fade-slide',exit='fade-slide'))
            scenes.append(scene)
        plan=CreativePlan(context.script_id,context.revision,digest(asdict(context)),
            'DOCUMENTATION VS DEPLOYMENT','Separate documented options from a deployment decision.',
            'Host identity plus an immediate contrast; pivot to source-backed documentation within three seconds.',
            HeroShot('Introduce the documentation/deployment distinction',min(3,scenes[0].end),scenes[0].scene_archetype,available,
                     'Host beside a split documentation/evaluation card; the comparison is editorial framing, not evidence.',
                     HEADINGS[0],'Reveal the contrast at 0.8s; pivot at 3s.','AVATAR' if available else 'LOCAL_MOTION_GRAPHIC'),
            scenes,retention(context,scenes,avatars),avatars,assets,
            ['Only upstream factual text and mappings may appear as evidence.','Never render generated UI as documentation or product behavior.',
             'Generated metaphors are illustrative only; official assets require source provenance.'],
            ['No external calls. All generation requests are proposals; local rendering is the default.',
             'Avatar availability may be a placeholder. Voice timing availability is recorded explicitly.',
             'No analytics priors required. Any future changed priors must be validated.'])
        validate(plan,context);return plan


def validate(plan, context):
    def require(ok,message):
        if not ok:raise ValueError('CreativePlan: '+message)
    require(type(plan) is CreativePlan,'schema')
    require((plan.script_id,plan.revision,plan.input_sha256)==(context.script_id,context.revision,digest(asdict(context))),'input provenance')
    upstream=context.production_constraints['upstream_scenes'];fps=context.production_constraints['fps']
    require(len(plan.scenes)==len(upstream),'scene coverage')
    assets={a.asset_id:a for a in plan.asset_generation_requests}
    require(len(assets)==len(plan.asset_generation_requests)==len(plan.scenes),'unique assets')
    seen=[]
    for scene,original in zip(plan.scenes,upstream):
        require(scene.scene_id==original['scene_id'],'scene identity/order')
        require((scene.start,scene.end)==(original['start_frame']/fps,original['end_frame']/fps),'scene timing')
        ids=[b['sentence_id'] for b in context.sentences if b['beat_id'] in original['beat_ids']]
        require(scene.narration_sentence_ids==ids,'narration coverage');seen+=ids
        expected=[{k:b[k] for k in ('sentence_id','claim_ids','source_ids','evidence_passage_ids','factual')} for b in context.sentences if b['sentence_id'] in ids]
        require(scene.claim_provenance==expected,'claim provenance')
        require(scene.on_screen_text==original['on_screen_text'],'upstream text/provenance')
        require(scene.scene_archetype in context.available_archetypes,'archetype')
        require(scene.factuality_class==scene.visual_type and scene.visual_type in KINDS,'factuality class')
        require(scene.editorial_heading in HEADINGS,'unreviewed display wording')
        require(scene.transition=='fade-through-background','transition')
        require(scene.provider_preference in context.available_providers,'provider')
        require(len(scene.asset_requirements)==1 and scene.asset_requirements[0] in assets,'asset resolution')
        asset=assets[scene.asset_requirements[0]]
        require(asset.scene_id==scene.scene_id and asset.preferred_provider==scene.provider_preference,'asset ownership')
        require(all(p in context.available_providers for p in asset.acceptable_fallback),'fallback provider')
        permitted={
            'FACTUAL_EVIDENCE':('LOCAL_MOTION_GRAPHIC','OFFICIAL_SOURCE'),
            'FACTUAL_EXPLANATION':('LOCAL_MOTION_GRAPHIC','OFFICIAL_SOURCE'),
            'CREATIVE_METAPHOR':('HF_LTX','AGNES','LOCAL_MOTION_GRAPHIC'),
            'DECORATIVE_BROLL':('HF_LTX','AGNES','LOCAL_MOTION_GRAPHIC'),
            'AVATAR_HOST':('AVATAR','LOCAL_MOTION_GRAPHIC'),
            'TRANSITION':('LOCAL_MOTION_GRAPHIC',)}
        require(all(p in permitted[scene.visual_type] for p in [asset.preferred_provider]+asset.acceptable_fallback),'visual routing policy')
        require(asset.generation_allowed==bool(scene.generation_prompt),'generation permission')
        if asset.generation_allowed:require('LOCAL_MOTION_GRAPHIC' in asset.acceptable_fallback or asset.preferred_provider=='LOCAL_MOTION_GRAPHIC','local fallback missing')
        # Every factual display surface is authorized, including host/transition scenes.
        for t in scene.on_screen_text:
            if t['factual']:require(bool(t['claim_ids'] and t['source_ids'] and t['evidence_passage_ids']),'factual display authorization')
        factual=scene.visual_type in ('FACTUAL_EVIDENCE','FACTUAL_EXPLANATION')
        require(asset.must_be_factual==factual,'factual routing flag')
        if factual:
            require(all(p in ('LOCAL_MOTION_GRAPHIC','OFFICIAL_SOURCE') for p in [asset.preferred_provider]+asset.acceptable_fallback),'generated factual evidence')
            require(not asset.generation_allowed and scene.generation_prompt is None,'generated factual prompt')
            for t in scene.on_screen_text:
                if t['factual']:require(bool(t['claim_ids'] and t['source_ids'] and t['evidence_passage_ids']),'missing factual authorization')
        # Factual payload cannot hide under a creative label to enable generation.
        if asset.generation_allowed:
            require(scene.visual_type in ('CREATIVE_METAPHOR','DECORATIVE_BROLL'),'generation class')
            require(not any(p['factual'] for p in expected),'factual narration routed to generated media')
            require(scene.generation_prompt==asset.prompt==metaphor_prompt(context,scene),'unreviewed generated prompt')
            require(scene.negative_prompt==asset.negative_prompt==NEGATIVE,'negative prompt')
            require(asset.resolution==[576,1024],'provider resolution')
        else:require(scene.generation_prompt is None and asset.prompt is None and asset.negative_prompt is None,'unexpected prompt')
        require(asset.orientation=='9:16' and math.isfinite(asset.expected_duration) and 0<asset.expected_duration<=scene.end-scene.start+.00001,'asset duration/orientation')
        events=scene.choreography
        require(bool(events) and events[0]['time']==scene.start,'initial visual')
        times=[e['time'] for e in events]
        require(all(isinstance(t,(float,int)) and math.isfinite(t) and scene.start<=t<scene.end for t in times) and times==sorted(set(times)),'event times')
        require(max(b-a for a,b in zip(times,times[1:]+[scene.end]))<=context.brand.max_static_hold,'static hold')
        for e in events:
            require(set(e)<= {'time','action','max_emphasis_items','focus'} and e['action'] in ('establish','contrast_reveal','documentation_pivot','progressive_reveal','list_group') and e['max_emphasis_items']==3,'event schema')
            if 'focus' in e:require(any(e['focus']==old.get('focus') for old in original.get('visual_events',[])),'list provenance')
    require(seen==[b['sentence_id'] for b in context.sentences],'all narration')
    require(any(e['action']=='documentation_pivot' and e['time']<=context.brand.hook_max for e in plan.scenes[0].choreography),'hook pivot')
    require(plan.scenes[-1].editorial_heading==HEADINGS[-1],'payoff visual')
    require(plan.hero_shot.avatar_usage==plan.scenes[0].avatar_usage and plan.hero_shot.scene_type==plan.scenes[0].scene_archetype,'hero treatment')
    require(plan.scenes[-1].retention_role=='payoff' and plan.scenes[-1].scene_archetype=='FinalPayoff','payoff')
    require(plan.hero_shot.headline==plan.scenes[0].editorial_heading and plan.hero_shot.generation_prompt is None and 0<plan.hero_shot.duration<=context.brand.hook_max,'hero')
    avatar_scenes=[]
    for a in plan.avatar_plan:
        require(set(a)=={'scene_id','start','end','position','screen_width','background','adjacent_text','entrance','exit'},'avatar schema')
        s=next((s for s in plan.scenes if s.scene_id==a['scene_id']),None)
        require(s is not None and s.avatar_usage and s.start<=a['start']<a['end']<=s.end,'avatar timing')
        require(a['position'] in ('left','right','center') and .2<=a['screen_width']<=.4 and a['adjacent_text']==s.editorial_heading,'avatar placement')
        require(a['entrance']==a['exit']=='fade-slide' and a['background']=='transparent-or-masked','avatar treatment')
        avatar_scenes.append(a['scene_id'])
    require(len(avatar_scenes)==len(set(avatar_scenes)) and set(avatar_scenes)=={s.scene_id for s in plan.scenes if s.avatar_usage},'avatar coverage')
    computed=retention(context,plan.scenes,plan.avatar_plan)
    require(plan.retention_plan==computed,'retention metrics')
    require(computed['first_visual_change_time']<=context.brand.first_change_max,'first visual change')
    if context.avatar_availability!='UNAVAILABLE':require(context.brand.avatar_min<=computed['avatar_screen_time']<=context.brand.avatar_max,'avatar duration')
    else:require(not plan.avatar_plan,'avatar unavailable')
    return True


class LLMCreativeDirector:
    """Injected structured-output boundary only; no live model client here."""
    def __init__(self, adapter):self.adapter=adapter
    def direct(self,context):
        raw=self.adapter(asdict(context),{'schema':'CreativePlan','example':DeterministicCreativeDirector().direct(context).to_dict()})
        try:
            data=json.loads(raw) if isinstance(raw,str) else copy.deepcopy(raw)
            data['hero_shot']=HeroShot(**data['hero_shot'])
            data['scenes']=[CreativeScene(**s) for s in data['scenes']]
            data['asset_generation_requests']=[CreativeAssetRequest(**a) for a in data['asset_generation_requests']]
            plan=CreativePlan(**data);validate(plan,context)
        except (TypeError,KeyError,ValueError,AttributeError) as exc:raise ValueError('Invalid structured CreativePlan') from exc
        return plan


def apply_plan(spec,plan,context):
    validate(plan,context)
    out=copy.deepcopy(spec)
    for scene,creative in zip(out['scenes'],plan.scenes):
        scene['scene_type']=creative.scene_archetype
        scene['visual_intent']=creative.visual_message
        scene['creative_treatment']=dict(editorial_heading=creative.editorial_heading,hook_pivot_frame=round(plan.retention_plan['hook_end_time']*out['fps']),role=creative.retention_role)
        # Existing source list events preserve exact grouping/provenance.
        scene['visual_events']=[dict(frame=round(e['time']*out['fps']),type=e['action'],max_emphasis_items=3,
            focus=e.get('focus',{'phrase_index':i})) for i,e in enumerate(creative.choreography)]
        scene['avatar']=None
        a=next((a for a in plan.avatar_plan if a['scene_id']==scene['scene_id']),None)
        if a:
            from .assets import AvatarAsset
            bounds=AvatarAsset('layout',position=a['position'],width_fraction=a['screen_width']).bounds()
            scene['avatar']=dict(asset_id=out['avatar_assets'][0]['asset_id'],position=a['position'],bounds=bounds,
                start_frame=round(a['start']*out['fps']),end_frame=round(a['end']*out['fps']),entrance=a['entrance'],exit=a['exit'],masked=True)
    out['provenance']['creative_plan_sha256']=digest(plan.to_dict())
    out['provenance']['creative_director']='deterministic-v1'
    out['retention_metadata'].update(plan.retention_plan)
    out['creative_dna'].update(plan.retention_plan,scene_archetypes=[s['scene_type'] for s in out['scenes']])
    out['video_id']='video-'+digest({'base':spec['video_id'],'creative_plan':plan.to_dict()})[:16]
    # Asset proposals are recorded, never dispatched. Existing local graphics resolve every scene.
    out['creative_asset_requests']=[asdict(a) for a in plan.asset_generation_requests]
    return out


def markdown(plan):
    lines=['# '+plan.creative_concept,plan.visual_thesis,'','## Scenes','| Time | Scene | Treatment | Route |','|---|---|---|---|']
    lines += [f'| {s.start:.2f}–{s.end:.2f}s | {s.scene_id} / {s.scene_archetype} | {s.editorial_heading} | {s.visual_type}; {s.provider_preference} |' for s in plan.scenes]
    lines += ['','## Hero',json.dumps(asdict(plan.hero_shot),indent=2),'','## Avatar',json.dumps(plan.avatar_plan,indent=2),'','## Retention',json.dumps(plan.retention_plan,indent=2)]
    for a in plan.asset_generation_requests:
        if a.prompt:lines += ['','## Proposed asset '+a.asset_id,a.prompt,'Negative: '+str(a.negative_prompt),'Fallback: '+', '.join(a.acceptable_fallback)]
    return '\n'.join(lines)+'\n'
