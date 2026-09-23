"""Bounded editorial, caution-polarity and structured category-list rules.

Negation never grants a sentence-wide exemption: every clause must independently
match a caution construction; positive clauses retain their forbidden matches.
"""
import re


def normalize(text):return re.sub(r'\s+',' ',text.casefold().replace('’',"'")).strip().rstrip('.?!:')

# These are inference targets, not product facts. Restrict the entire target to
# prevent 'no evidence of X, but it is Y' from laundering the positive assertion.
TARGET=r'(?:broad |universal |general |independent |real-world |comparative )?(?:reliability|superiority|availability|safety|performance|benchmark(?: evidence| results)?|agi|launch timing|a launch date)'
TARGETS=TARGET+r'(?:(?:,? (?:and|or) |, )'+TARGET+r')*'
OBSERVATION=r'(?:(?:the |this |listed |documented )*(?:support|prices|pricing|capabilities|specifications|documentation|evidence|constraints|scope|limits))'
OBSERVATIONS=OBSERVATION+r'(?: (?:and|or) '+OBSERVATION+r')*'
CAUTIONS=[
    r'(?:this )?does not prove better performance',
    r'listed support is not a guarantee of reliability',
    r'not reliable', r'not necessarily available',r'does not prove',r'cannot conclude',r'no evidence shows',
    r'listed tool support does not show that a tool is enabled, appropriate, or reliable in every deployment',
    r'(?:the supplied documentation )?does not prove a specific workflow payoff',
    r'listed support ≠ guaranteed availability, appropriateness, reliability, or workflow payoff',
    r'documentation ≠ workflow guarantee',
    r'(?:that is |this is |it is )?not (?:the same as )?(?:a )?(?:proven workflow result|workflow guarantee|guarantee)',
    r'(?:the documentation |the supplied evidence |this |it )?does not prove (?:reliability|a workflow result|a specific workflow payoff)',
    r'listed tool support does not establish that a tool is available, appropriate, or reliable in every deployment(?:, and the supplied evidence proves no specific workflow payoff)?',
    r'(?:the tool |this |it )?cannot be treated as reliable',
    r'tool support alone does not establish that a tool is appropriate, reliable, or enabled in every deployment(?:, and the supplied evidence provides no specific workflow payoff)?',
    r'(?:(?:the )?(?:supplied )?(?:documentation|docs|sources|evidence|model page) )?(?:does not|do not|cannot|can not|doesn\'t|don\'t) (?:establish|prove|demonstrate|confirm|justify|support) '+TARGETS,
    r'(?:do not|don\'t|should not) treat '+OBSERVATIONS+r' as (?:proof|evidence)(?: of| for) '+TARGETS,
    r'without treating '+OBSERVATIONS+r' as (?:proof|evidence)(?: of| for) '+TARGETS,
    r'(?:this is |that is |it is )?not (?:proof|evidence)(?: of| for) '+TARGETS,
    r'no (?:benchmark )?evidence (?:establishes|proves|demonstrates|confirms|supports) '+TARGETS,
    r'(?:there is )?no evidence of '+TARGETS,
    r'(?:we |you |readers )?(?:should not infer|cannot conclude|cannot establish) '+TARGETS,
    TARGETS+r' (?:is|are|remain|remains) (?:unknown|unverified)',
]


def clauses(text):
    # Retain comma-separated noun lists, split coordinated finite assertions and
    # contrastive clauses. Decimal points and model names are not sentence ends.
    return [m for m in re.finditer(r'.+?(?=(?:[.!?;](?:\s|$)|\s+(?:but|however|yet|although)\s+|,?\s+and\s+(?:it|this|the model|[A-Z][\w-]*)\s+(?:is|can|does|has)\b)|$)',text) if m.group().strip(' ,.;!?')]


def caution_clause(text):
    t=normalize(text).strip(' ,;')
    t=re.sub(r'^(?:but|however|yet|although|and)\s+','',t)
    return any(re.fullmatch(pattern,t) for pattern in CAUTIONS)


def polarity(text, forbidden):
    spans=clauses(text);result=[]
    for category,pattern in forbidden.items():
        for match in re.finditer(pattern,text,re.I):
            clause=next((c for c in spans if c.start()<=match.start()<c.end()),None)
            cautious=bool(clause and caution_clause(clause.group()))
            # Negation scopes only the guarantee occurrence, not preceding facts.
            negated=re.search(r'not a (?:workflow )?guarantee\b',text,re.I)
            if negated and negated.start()<=match.start()<negated.end():cautious=True
            result.append(dict(category=category,text=match.group(),start_offset=match.start(),end_offset=match.end(),
                polarity='CAUTIONARY_NEGATION' if cautious else 'ASSERTION',
                scope=clause.group().strip() if clause else text,
                reason='Concept is inside a bounded no-inference caution.' if cautious else 'No applicable caution/negation scopes this occurrence.'))
    return sorted(result,key=lambda r:(r['start_offset'],r['category']))


def entirely_cautionary(text):
    parts=clauses(text)
    return bool(parts) and all(caution_clause(c.group()) for c in parts)


def editorial(text,known):
    t=normalize(text)
    if t in known:return True
    if t in {"here's what the documentation actually says","test this before assuming it works",
             "use this as a checklist","the important part is what you still need to verify"}:return True
    if re.fullmatch(r'open on a restrained card reading “[^”]+”',t):return True
    if re.fullmatch(r'show a responses api map with two branches: “[^”]+” and “[^”]+”',t):return True
    if re.fullmatch(r'animate the full reasoning range in order: low, medium, high, xhigh, max',t):return True
    if re.fullmatch(r'display the tool list as grouped labels rather than implying every tool is enabled in every deployment',t):return True
    if re.fullmatch(r'end on a three-step frame: “[^”]+”',t):return True
    if t in {
        'think of those as a configuration checklist, not a verdict on what will work for your deployment',
        'so pick the documented settings and tools you need, test them in the actual environment, and measure the result yourself',
        'that is the gap between an api feature list and a deployment decision',
        'reasoning.effort', 'listed tools',
        'documented configuration → deployment test → measured result',
    }:return True
    if t in {"here's what the documentation actually establishes","test before you assume",
             "the important part is what you still need to test"}:return True
    if re.fullmatch(r'this is a guide to its stated api configuration surface, not a promise of workflow results',t):return True
    if re.fullmatch(r'use the documentation as a checklist',t):return True
    if re.fullmatch(r'select a documented configuration, test it in the particular deployment, and do not treat listed capabilities as proven workflow outcomes',t):return True
    if re.fullmatch(r'the useful editorial question is how to (?:translate|turn) those documented controls and integrations into an evaluation plan for a particular deployment',t):return True
    if re.fullmatch(r'a bounded, documentation-based checklist for scoping [a-z0-9 -]+ evaluation without treating listed capabilities as proven workflow outcomes',t):return True
    if re.fullmatch(r"here (?:is|’s|'s) what the (?:docs|documentation) actually says?",t):return True
    if re.search(r'\b(best|reliable|superior|excellent|cheap|safest|guaranteed|industry-leading|broadly available|universally available)\b',t):return False
    # These complete constructions describe the treatment or a reader's checklist,
    # not a product's ability. Fact-bearing relative clauses are not exempted.
    if re.search(r'\b(is|are|was|were|costs?|supports?|handles?|runs?|provides?|enables?|delivers?|achieves?|accepts?|has|have|can|will)\b|\$|\b\d+(?:\.\d+)?\s*(?:million|tokens|percent|%)\b',t):
        # 'Readers can use' is an editorial action, not the model's capability.
        return bool(re.fullmatch(
            r'(?:readers|viewers|you) can use (?:the |these |this )?(?:documented )?(?:scope and constraints|constraints|specifications|documentation|scope|limits) '
            r'(?:as (?:a |an )?(?:checklist|initial checklist|assessment checklist)|to (?:frame|inform|structure) (?:an? )?(?:initial )?(?:api-fit |api fit )?assessment)',t))
    return bool(re.fullmatch(r'(?:a|an) (?:(?:practical|concise|documentation-first|evidence-based|short) )*(?:guide|overview|checklist|look) (?:to|at|of|for) [^.!?;]+',t))


# Category labels describe documented fields; no evaluative adjectives, prices or
# new capabilities are inferred from the fact that the field is present.
CATEGORY_RULES=[
    (r'responses api computer[ -]use support',[r'Computer use Supported',r'Tools supported by this model when using the Responses API']),
    (r'(?:supported |documented )?modalities',[r'Modalities Text (?:Input and output|Input only|Output only)',r'Image (?:Input only|Input and output|Not supported)',r'Audio (?:Not supported|Input and output)',r'Video (?:Not supported|Input and output)']),
    (r'fine-tuning status',[r'Fine-tuning (?:Not supported|Supported)']),
    (r'(?:documented )?token limits',[r'[\d,]+ context window',r'[\d,]+ max output tokens']),
    (r'listed (?:text[ -]token |token )?prices',[r'Text tokens Per 1M tokens Input \$[\d.]+',r'Output \$[\d.]+']),
]


def atomic_texts(text):
    """Split enumeration boundaries, preserving exact atom text for diagnostics."""
    return [part.strip() for part in re.split(r',(?=\s|[^\d])\s*(?:and\s+)?|\s+and\s+',text.replace(' • ', ', ')) if part.strip()]


def category_support(text,passages):
    value=normalize(text);evidence=' '.join(p['quote'] for p in passages)
    for label,fields in CATEGORY_RULES:
        if re.fullmatch(label,value):
            return all(re.search(pattern,evidence,re.I) for pattern in fields)
    return False
