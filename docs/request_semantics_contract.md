# Request Semantics Contract (ICU/HD First Release)

## 1. Purpose and scope
This document is the normative contract for ICU/HD first-release **request semantics**.

It defines, for request text only:
- accepted raw request grammar,
- accepted raw token vocabulary,
- deterministic raw-to-canonical mapping,
- deterministic canonical-to-machine-effect mapping,
- combination handling,
- duplicate handling,
- and request-level consumability outcomes.

This contract is implementation-facing and intentionally narrow.

## 2. Boundary position relative to template / snapshot / parser / domain model
This contract sits between:
- raw request text as present in snapshot rows, and
- normalized Request semantics used downstream.

Boundary alignment:
- Template-level shape/columns remain defined in `docs/template_contract.md`.
- Snapshot capture/extraction concerns remain defined in `docs/snapshot_contract.md`.
- Generic parser result envelope and parser/normalizer boundary remain defined in `docs/parser_normalizer_contract.md`.
- Broader domain entities/relationships remain defined in `docs/domain_model.md`.

This file defines only the request-semantics sub-contract within that boundary.

## 3. What this contract governs and what it does not govern
This contract governs:
- how raw ICU/HD request text is lexed and parsed,
- which raw request tokens are accepted,
- how accepted tokens map to canonical normalized request classes,
- how canonical classes map to first-release machine effects,
- deterministic handling of combinations and duplicates,
- and consumable vs non-consumable outcomes at request level.

This contract does **not** govern:
- solver behavior,
- search strategy,
- scoring weights or formulas,
- writeback/UI policy,
- cloud execution behavior,
- spreadsheet extraction mechanics,
- or generic parser result structure already owned elsewhere.

## 4. ICU/HD first-release raw request input model
Input for this contract is the raw request text for a single doctor on a single date (possibly blank).

The parser must re-validate this raw text directly and must not rely on spreadsheet-side validation.

## 5. Lexical and grammar rules
Normative rules:
1. Delimiter grammar is **comma-separated only**.
2. Parsing is trim-tolerant around tokens and commas.
3. Token matching is case-insensitive.
4. A blank string after trim is valid and means no request codes.
5. Slash (`/`), semicolon (`;`), period (`.`), and arbitrary punctuation as delimiters are not accepted.

Operational consequence:
- If text cannot be deterministically parsed under comma-only grammar, parser must not guess.

## 6. Accepted raw token vocabulary
Accepted raw ICU/HD tokens are exactly:
- `CR`
- `NC`
- `AL`
- `TL`
- `SL`
- `MC`
- `HL`
- `NSL`
- `OPL`
- `EXAM`
- `EMCC`
- `PM_OFF`

No additional raw tokens are recognized by this first-release contract.

## 7. Canonical normalized request classes
Canonical normalized request classes are exactly:
- `CR`
- `NC`
- `FULL_DAY_OFF`
- `PM_OFF`

## 8. Raw-to-canonical mapping
Raw-to-canonical mapping is exact and closed:
- `CR` -> `CR`
- `NC` -> `NC`
- `AL` -> `FULL_DAY_OFF`
- `TL` -> `FULL_DAY_OFF`
- `SL` -> `FULL_DAY_OFF`
- `MC` -> `FULL_DAY_OFF`
- `HL` -> `FULL_DAY_OFF`
- `NSL` -> `FULL_DAY_OFF`
- `OPL` -> `FULL_DAY_OFF`
- `EXAM` -> `FULL_DAY_OFF`
- `EMCC` -> `PM_OFF`
- `PM_OFF` -> `PM_OFF`

## 9. Canonical-to-machine-effect mapping
Machine-effect vocabulary for ICU/HD first release is exactly:
- `sameDayHardBlock`
- `prevDayCallSoftPenaltyTrigger`
- `callPreferencePositive`

`sameDayHardBlock` is defined as:
- excludes the doctor from all slot assignment on that date in ICU/HD first release.

Canonical-to-machine-effect mapping is exact:
- `CR` -> `callPreferencePositive`
- `NC` -> `sameDayHardBlock`
- `FULL_DAY_OFF` -> `sameDayHardBlock` + `prevDayCallSoftPenaltyTrigger`
- `PM_OFF` -> `sameDayHardBlock` + `prevDayCallSoftPenaltyTrigger`

No additional machine effects are introduced by this contract.

## 10. Combination handling rules
Combined recognized codes are allowed.

For deterministic combinations of recognized tokens, parser behavior is:
1. Preserve recognized raw token set (with provenance retained at request level).
2. Preserve canonical class set.
3. Resolve machine effects as full union of effects from canonical classes.
4. Keep outcome `CONSUMABLE` when meaning remains deterministic.
5. Emit non-blocking parser issues for awkward but deterministic combinations where appropriate.

Normative special case:
- `CR` + blocking-class combinations (for example `CR, NC`, `CR, EXAM`, `CR, PM_OFF`) remain `CONSUMABLE`, preserve provenance, preserve full union of effects, and emit a non-blocking parser issue rather than structural rejection.

## 11. Duplicate handling rules
Duplicates of recognized codes are allowed but must be normalized without changing meaning.

Required behavior:
1. Canonicalize duplicates to stable sets at raw/canonical/effect layers.
2. Keep outcome `CONSUMABLE`.
3. Emit a non-blocking parser issue.
4. Apply this rule both to direct duplicates and alias duplicates that collapse after raw-to-canonical mapping.

## 12. Unknown / malformed / mixed-known-unknown handling
Parser must not guess.

Rules:
1. Unknown token(s) are not silently ignored.
2. Malformed delimiter patterns (for example slash-separated forms) are not auto-corrected.
3. Mixed known + unknown content is only `CONSUMABLE` if downstream-governing request facts can still be derived deterministically under parser/normalizer rules; otherwise it is `NON_CONSUMABLE`.
4. If deterministic downstream-governing request facts cannot be derived, result must be `NON_CONSUMABLE`.
5. Issue semantics must be explicit, but exact issue-code string standardization is deferred unless required elsewhere.

First-release default intent for unknown or malformed content is conservative: non-guessing, explicit issues, and non-consumable whenever determinism is broken.

## 13. Consumable vs non-consumable rules
A parsed request is `CONSUMABLE` when all downstream-governing request facts are deterministically derivable under this contract.

A parsed request is `NON_CONSUMABLE` when determinism is not possible from the provided raw text (including unknown/malformed content that blocks deterministic derivation).

Recognized-only awkward combinations and duplicates are not, by themselves, grounds for `NON_CONSUMABLE`; they stay `CONSUMABLE` with non-blocking issues.

## 14. Required normalized Request-level outputs for consumable parses
For a `CONSUMABLE` parsed request, normalized request semantics must include:
1. recognized raw tokens,
2. canonical class set,
3. resolved machine-effect set,
4. canonical deterministic ordering for emitted sets (not unstable encounter-order output).

These outputs are request-semantic payload requirements only and do not redefine the generic parser result envelope.

## 15. Explicit deferrals
This contract explicitly defers:
- solver interpretation and conflict resolution behavior,
- objective/scoring impact magnitude,
- UI/writeback presentation policy,
- runtime/deployment/cloud behaviors,
- spreadsheet ingestion mechanics,
- and any expansion beyond ICU/HD first-release request vocabulary and mappings.

This contract also does not reopen settled boundaries already defined in blueprint/template/snapshot/parser/domain docs.

## 16. Worked examples (ICU/HD first release)
Legend:
- Raw tokens/classes/effects are shown as deterministic sets in canonical order.
- "Issue semantics" uses descriptive labels (non-normative strings) to keep meaning explicit without over-standardizing issue codes.

| Raw input | Recognized raw tokens | Canonical classes | Machine effects | Issue semantics | Outcome |
|---|---|---|---|---|---|
| `""` (blank) | `{}` | `{}` | `{}` | none | `CONSUMABLE` |
| `"   "` (whitespace only) | `{}` | `{}` | `{}` | none | `CONSUMABLE` |
| `CR` | `{CR}` | `{CR}` | `{callPreferencePositive}` | none | `CONSUMABLE` |
| `NC` | `{NC}` | `{NC}` | `{sameDayHardBlock}` | none | `CONSUMABLE` |
| `AL` | `{AL}` | `{FULL_DAY_OFF}` | `{sameDayHardBlock, prevDayCallSoftPenaltyTrigger}` | none | `CONSUMABLE` |
| `EMCC` | `{EMCC}` | `{PM_OFF}` | `{sameDayHardBlock, prevDayCallSoftPenaltyTrigger}` | none | `CONSUMABLE` |
| `PM_OFF` | `{PM_OFF}` | `{PM_OFF}` | `{sameDayHardBlock, prevDayCallSoftPenaltyTrigger}` | none | `CONSUMABLE` |
| `EXAM, NC` | `{EXAM, NC}` | `{FULL_DAY_OFF, NC}` | `{sameDayHardBlock, prevDayCallSoftPenaltyTrigger}` | optional non-blocking awkward-combination issue | `CONSUMABLE` |
| `CR, NC` | `{CR, NC}` | `{CR, NC}` | `{callPreferencePositive, sameDayHardBlock}` | non-blocking CR-plus-blocking combination issue | `CONSUMABLE` |
| `CR, EXAM` | `{CR, EXAM}` | `{CR, FULL_DAY_OFF}` | `{callPreferencePositive, sameDayHardBlock, prevDayCallSoftPenaltyTrigger}` | non-blocking CR-plus-blocking combination issue | `CONSUMABLE` |
| `EXAM, PM_OFF` | `{EXAM, PM_OFF}` | `{FULL_DAY_OFF, PM_OFF}` | `{sameDayHardBlock, prevDayCallSoftPenaltyTrigger}` | optional non-blocking overlapping-blocking-classes issue | `CONSUMABLE` |
| `NC, NC` | `{NC}` | `{NC}` | `{sameDayHardBlock}` | non-blocking duplicate-recognized-token issue | `CONSUMABLE` |
| `EMCC, PM_OFF` | `{EMCC, PM_OFF}` | `{PM_OFF}` | `{sameDayHardBlock, prevDayCallSoftPenaltyTrigger}` | non-blocking duplicate-after-alias-normalization issue | `CONSUMABLE` |
| `CR/NC` | n/a (malformed delimiter) | n/a | n/a | blocking malformed-grammar issue (non-comma delimiter) | `NON_CONSUMABLE` |
| `CR, XYZ` | `{CR}` (with unknown remainder present) | indeterminate under unknown-token presence | indeterminate | blocking unknown-token issue; parser must not guess | `NON_CONSUMABLE` |

