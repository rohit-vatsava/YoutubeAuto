# Requirement-driven full research

The planner deduplicates generic cluster questions while retaining every original
claim ID. Research questions are not factual assertions. Comparison research adds
primary-documentation, alternative and common-criterion requirements; no named
alternative is invented. The canonical subject comes from StoryResolutionGate.

Full research searches before its first evidence synthesis. Each search has a
requirement ID, query, category, timestamp, returned/selected/rejected results and
measured estimated model+search cost delta. All search records are persisted inside
the existing SQLite research outcome and exported as research_searches.json.
No schema migration is necessary.

Each requirement gets at most two semantically distinct queries. A normalized
keyword/alias signature deduplicates equivalent queries; this is deterministic,
not a general semantic model. Unattempted material requirements take precedence
over second attempts. Fetch allocation reserves room for remaining requirements.
Failed preflight URLs are excluded from repeated fetches; the first-party domain
anchors alternate document discovery. Fetched resolution documents can be reused.
Discovery snippets and competitor YouTube metadata never support factual claims.

Interim synthesis after discovery extracts exact passages and resolves requirements
through the existing claim-relative validator. It may suggest ANGLE_UNSUPPORTED,
but the executor continues discovery. Comparison support additionally requires a
passage-grounded alternative/criterion, claims supporting both sides under declared
comparable conditions, and a decision/rationale. Only grounded comparison leads
can refine the next query. The independent fact checker still evaluates entailment.

An unsupported angle is terminal only after unresolved angle research was attempted
and the search ceiling was reached or searches repeatedly added no relevant evidence.
Direct contradictions stop through the existing CORE_CONTRADICTION gate. Time,
cost, source and requirement limits remain separate failure reasons, never fabricated
proof that an angle is invalid. Budget exhaustion cannot force script generation.

Limits remain four full-research logical searches, six source attempts, $1 and
300 seconds, plus the existing separately bounded preflight. The adapter now counts
full-research searches separately from preflight (previously preflight accidentally
consumed one of the four full-research slots). Both stages share the same cost/time
ledger. These are ceilings, not promises: actual affordability and retrieval results
may stop research sooner. A complete packet stops discovery early.

Offline planning replay only lists conditional queries; it does not invent new
results or claim that live research will succeed. Original run artifacts are immutable.
