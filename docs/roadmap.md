# Roadmap (Phased Skeleton)

## Phase 0: docs / architecture
- Close architecture-level boundary wording across template artifact, snapshot, parser boundary, and domain model contracts.
- Record only remaining narrow open items after contract-surface alignment.

## Phase 1: contracts
- Stabilize contract surfaces and ownership boundaries for template artifact, snapshot, and parser/normalizer handoff.
- Lock validation expectations needed for deterministic downstream-governing interpretation.

## Phase 2: parser + normalization
- Implement parser/normalizer against closed contract surfaces (not before boundary closure).
- Parse sheet-oriented inputs into normalized model.
- Produce deterministic input bundles for downstream stages.

## Phase 3: rule engine
- Implement hard-constraint evaluation framework.
- Support department template rule interpretation.

## Phase 4: scorer
- Implement soft-constraint scoring framework.
- Expose score components for diagnostics.

## Phase 5: solver
- Build allocation solver using rules + scoring.
- Support repeatable run behavior and result selection.

## Phase 6: local execution
- Provide local run workflow for development/validation.
- Emit artifacts useful for debugging and review.

## Phase 7: artifacts / writeback
- Formalize output artifacts and sheet writeback mapping.
- Ensure output structure aligns with operations needs.

## Phase 8: external worker / cloud hardening
- Add external execution path for reliability/scale.
- Harden run lifecycle, retries, and failure handling.

## Phase 9: sheet integration
- Integrate operational sheet flow with v2 pipeline.
- Validate end-to-end behavior for first department rollout.
- Include template-driven generation support for structured operator-facing request-form input sheets declared by template layout contracts.

## Phase 10: observability / benchmarking hardening
- Strengthen diagnostics, explainability, and performance benchmarks.
- Set baseline operational SLO-oriented checks.
