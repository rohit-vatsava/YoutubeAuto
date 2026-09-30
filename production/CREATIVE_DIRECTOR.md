# M4.1 Creative Director

The optional `produce --creative-director` stage sits after narration alignment and before final ProductionSpec/render export. Existing planning builds the timing and source-surface scaffold; CreativeDirector consumes it, validates a CreativePlan, and applies visual treatment without changing narration, timestamps, captions, claims, research or M3 readiness.

## Interfaces

`CreativeDirectorInput` carries script/revision/title, narration sentence IDs and times, source surfaces and evidence mappings, topic/cohort, audience/platform/duration, available archetypes/providers, avatar/voice availability, brand, constraints and optional analytics priors. `TechUncoveredBrandProfile` contains configurable retention priors. No M6 dependency; analytics are carried as context, not automatically trusted settings.

`CreativePlan` contains concept, thesis, hook strategy, typed HeroShot, CreativeScene[], CreativeAssetRequest[], retention plan, avatar windows, factual constraints and production notes. All input provenance is hashed. Creative scenes preserve exact upstream display surfaces as well as separate, reviewed editorial headings.

`DeterministicCreativeDirector` uses a bounded documentation/evaluation treatment family. It is intentionally conservative, not a universal creative strategist. `LLMCreativeDirector` accepts an injected structured-output adapter only; no model client, credentials or live calls are included. Unknown fields, unsafe routes, invented display wording and unreviewed generation prompts fail closed. The current controlled prompt template limits LLM freedom deliberately.

## Routing

- FACTUAL_EVIDENCE: official/source-backed assets or deterministic sourced cards; never fabricated evidence.
- FACTUAL_EXPLANATION: local diagrams/cards, authorized text and provenance.
- CREATIVE_METAPHOR / DECORATIVE_BROLL: HF_LTX proposals; AGNES then local acceptable fallback metadata. No automatic switching or dispatch.
- AVATAR_HOST: existing avatar asset/placeholder plus local composition.
- TRANSITION: local motion graphics.

Generated-media requests remain proposals. ProductionSpec uses existing local assets for this preview; actual generated-media screen time is zero. Official screenshots cannot be fabricated or inferred from the model. Future fulfillment must pass existing AssetRouter/provider gates.

## Validation

Checks exact input identity, sentence coverage/order, unchanged scene timing, display/evidence mappings, known archetypes and provider enums, factual routing, controlled prompts, valid asset IDs, avatar bounds/windows, hook pivot, first change, maximum static hold, source-backed list grouping and final payoff. Retention metrics are independently recomputed. Model output never supplies filesystem paths, URLs, shell commands or credentials. Descriptive model prose is not executed.

## Astra revision 7

The real saved M3 narration is unchanged. Timing comes from the existing **synthetic** revision-7 narration fixture: 57.2 seconds, 9 scenes. It is not aligned to a recorded voice. Host windows are0–3s and54.2–57.2s. Editorial headings distinguish documentation from deployment; they add no product capability assertions. First contrast reveal0.8s; documentation pivot3s. Existing lists remain source-authored and grouped to three emphasized items.

The optional LTX sample was not used: its soft abstract background adds less clarity than the local cards/diagrams for these evidence-heavy scenes. No external assets were generated.

## Run offline

Use a new output directory for each build:

```sh
.venv/bin/python main.py produce \
  --fixture fixtures/production/astra-revision-7/fixture.json \
  --preview --avatar fixtures/production/astra-revision-7/avatar.json \
  --creative-director --output reports/production/astra-revision-7
node tools/render_production.mjs \
  --spec reports/production/astra-revision-7/production-spec.json --render
```

The output includes creative-input.json, creative-plan.json, creative-plan.md, existing M4 production files and optional silent preview.mp4. Existing non-director CLI behavior remains unchanged. No publishing or provider calls occur.
