import re
from .generation import sentences
from .hooks import mapping_errors


def validate_check(raw,draft,packet,now):
    """Independent semantic verdict AND deterministic traceability must both pass."""
    from .pivot_acceptance import scope_issues
    from copy import deepcopy
    checked_draft=deepcopy(draft)
    # Rejected alternatives are retained for audit, never publishable claims.
    checked_draft['hook_candidates']=[h for h in draft['hook_candidates'] if h.get('eligible')]
    issues=scope_issues(checked_draft,packet,draft=True);checks={r['sentence_id']:r for r in raw.get('sentence_checks',[])}
    claims={c['claim_id']:c for c in packet['claims']}
    for s in sentences(draft):
        check=checks.get(s['sentence_id'])
        if not check or not check.get('supported') or check.get('issues'):issues.append(s['sentence_id']+':SEMANTIC_SUPPORT_MISSING')
        # Every sentence is checked, even one the generator labels opinion/nonmaterial.
        if s.get('statement_type') not in ('OPINION','PREDICTION') or (check and check.get('material',True)):
            issues.extend(s['sentence_id']+':'+e for e in mapping_errors(s,packet))
        if check and (set(check.get('claim_ids',[]))!=set(s.get('claim_ids',[])) or set(check.get('source_ids',[]))!=set(s.get('source_ids',[]))):issues.append(s['sentence_id']+':CHECK_MAPPING_MISMATCH')
        supporting=' '.join(claims[c]['supported_wording']+' '+' '.join(p['quote'] for p in claims[c]['passages']) for c in s.get('claim_ids',[]) if c in claims)
        semantic_numeric=False
        if draft.get('scope_contract_version')==2 and packet.get('pivot_acceptance'):
            from .pivot_scope import classify
            decision=classify(dict(text=s['text'],factual=s.get('factual',True),claim_ids=s.get('claim_ids',[]),evidence_ids=s.get('source_ids',[]),passage_ids=s.get('evidence_passage_ids',[])),packet)
            semantic_numeric=decision['classification'] in ('SUPPORTED_EXACT','SUPPORTED_PARAPHRASE','SUPPORTED_COMPOSITE_PARAPHRASE','NONFACTUAL_EDITORIAL')
            if decision['classification'] in ('NEW_UNSUPPORTED_CLAIM','BROADER_THAN_EVIDENCE','FORBIDDEN_CATEGORY'):issues.append(s['sentence_id']+':'+decision['classification']+':'+s['text'])
        for num in re.findall(r'\b\d+(?:\.\d+)?%?',s['text']):
            if not semantic_numeric and num not in supporting:issues.append(s['sentence_id']+':UNSUPPORTED_NUMBER:'+num)
        attribution_pattern=r'\b(says|said|reports|reported|according|claims|announced)\b'
        if draft.get('scope_contract_version')==2:attribution_pattern=r'\b(says|said|reports|reported|according|claims|documents|documentation|documented|lists|listed|model page)\b'
        attributed_elsewhere=any(
            set(s.get('claim_ids',[]))<=set(other.get('claim_ids',[])) and
            re.search(attribution_pattern,other['text'],re.I)
            for other in sentences(draft) if other is not s)
        if any(claims.get(c,{}).get('requires_attribution') for c in s.get('claim_ids',[])) and not re.search(attribution_pattern,s['text'],re.I) and not (semantic_numeric and attributed_elsewhere):issues.append(s['sentence_id']+':ATTRIBUTION_REQUIRED')
    hooks={h['hook_id']:h for h in raw.get('hook_checks',[])}
    for h in draft['hook_candidates']:
        if not h.get('eligible'):continue
        c=hooks.get(h['hook_id'])
        if not c or not c.get('supported') or c.get('issues') or not h['eligible']:issues.append(h['hook_id']+':UNSAFE_HOOK')
    if not raw.get('title_supported') or not draft.get('title_claim_ids') or any(cid not in claims or claims[cid]['status'] not in ('VERIFIED','PARTIALLY_VERIFIED') for cid in draft.get('title_claim_ids',[])):issues.append('UNSUPPORTED_TITLE')
    for key in ('unsupported_sentences','overstated_sentences','attribution_issues','timeline_issues','numerical_issues','ambiguity_issues','new_material_claims'):
        issues.extend(str(x) for x in raw.get(key,[]))
    if not raw.get('visual_notes_supported'):issues.append('UNSUPPORTED_VISUAL_NOTES')
    verdict=raw.get('verdict','RESEARCH_REQUIRED')
    if issues:verdict='FAIL'
    elif verdict not in ('PASS','PASS_WITH_MINOR_EDITS','FAIL','RESEARCH_REQUIRED'):verdict='RESEARCH_REQUIRED'
    raw.update(script_id=draft['script_id'],revision=draft['revision'],checked_at=now,claims_checked=len(sentences(draft)),deterministic_issues=issues,verdict=verdict)
    return raw
