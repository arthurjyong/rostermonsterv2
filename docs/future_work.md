# Future Work

## Purpose
Parking lot for hypothetical future directions and open ideas that are not yet committed work.

This document is intentionally **non-normative**:
- It is not a roadmap. Committed milestone-level delivery order lives in `docs/roadmap.md`.
- It is not a decision. Accepted directional decisions live in `docs/decision_log.md`.
- It is not an active execution tracker. Active milestone/checkpoint/task truth lives in `docs/delivery_plan.md`.
- It is not a contract. Normative technical boundaries live in the contract docs under `docs/`.

Entries here are ideas we want to remember, not commitments to build. If an entry is promoted to committed work, migrate it into the appropriate authoritative doc (roadmap / delivery plan / decision log / contract) and delete the entry from here. If an entry is deliberately rejected, record a short rationale in `docs/decision_log.md` and delete the entry from here.

## Entry format
Each entry should be short and concrete:
- **Title**
- **Date noted**
- **Context** — what we noticed, on which surface
- **Idea / direction** — what we might do later
- **Why deferred now** — usually: out of active checkpoint scope or not yet justified
- **Trigger to revisit** (optional) — what would make this worth picking up
- **Related surfaces** — files / docs the idea would touch

Keep entries implementation-facing. Do not restate contract meaning here. Do not turn this into a vague-ideas dumping ground.

## Maintenance
- Add entries as ideas surface during planning or implementation.
- Keep entries terse; detail belongs in the authoritative doc once the idea is committed.
- When an idea is promoted, move it and delete the parking-lot entry.
- When an idea is rejected, record a short rationale in `docs/decision_log.md` and delete the parking-lot entry.
- This doc must not grow into a parallel roadmap. If it starts dictating sequencing, promote the relevant entries and trim.

## Current entries

### FW-0001 — Launcher title should be department-driven, not hardcoded to ICU/HD
- **Date noted:** 2026-04-21
- **Context:** `apps_script/m1_sheet_generator/src/LauncherForm.html` renders a static `<h1>` reading "CGH ICU/HD Roster Launcher". This is harmless today because the Department dropdown has a single ICU/HD option and ICU/HD is the only supported template (blueprint §16, D-0005, D-0011). The title is effectively baked into the page rather than derived from the selected department.
- **Idea / direction:** When the launcher gains more than one department template, derive the title from the currently selected department / template rather than hardcoding it. Possible shapes: a generic "Roster Launcher" heading plus a department-driven subtitle, or a fully template-driven title string sourced from the template artifact. The title should follow the dropdown selection rather than lag behind it.
- **Why deferred now:** M1.1 scope is ICU/HD-only pilot; there is no second department template yet, so the single-value dropdown and fixed title are consistent with actual supported behavior.
- **Trigger to revisit:** First additional department template lands, or the Department dropdown gains a second option.
- **Related surfaces:** `apps_script/m1_sheet_generator/src/LauncherForm.html` (title literal and dropdown), `apps_script/m1_sheet_generator/src/Launcher.gs` (any server-side template listing surfaced to the form), `docs/sheet_generation_contract.md` §12 (launcher surface).

### FW-0002 — Launcher doctor-count groups should be template-driven, not hardcoded ICU/HD groups
- **Date noted:** 2026-04-21
- **Context:** `apps_script/m1_sheet_generator/src/LauncherForm.html` hardcodes three doctor-count inputs — `ICU only`, `ICU + HD`, `HD only` — mirroring the ICU/HD template's declared doctor groups (`ICU_ONLY`, `ICU_HD`, `HD_ONLY`). The number of inputs, their labels, and their identifiers are all ICU/HD-specific. The submission payload shape (`icuOnly`, `icuHd`, `hdOnly`) is equally ICU/HD-specific. Other departments will declare different doctor-group structures (for example, an Emergency Department template would not have ICU/HD groupings at all).
- **Idea / direction:** Drive the doctor-count fieldset from the selected department template's declared doctor groups rather than from hardcoded form fields. Render one numeric input per declared group, with labels sourced from the template. Corresponding consequence: the launcher payload and `normalizeAndValidateConfig_` consumption shape become template-driven rather than fixed on ICU/HD keys. The blueprint already treats slot/group structure and group-based eligibility as template-declared (blueprint §6, §16), so the direction is consistent with the architecture; only the launcher UI and payload have not yet been generalized.
- **Why deferred now:** ICU/HD is the sole first-release template. A template-driven form surface is not needed until a second department with a different group structure exists, and generalizing prematurely would add surface without operator benefit during the pilot.
- **Trigger to revisit:** First additional department template lands, or ICU/HD's group declarations change, or the launcher payload contract is revisited in `docs/sheet_generation_contract.md` §12.
- **Related surfaces:** `apps_script/m1_sheet_generator/src/LauncherForm.html` (doctor-count fieldset and payload shape), `apps_script/m1_sheet_generator/src/Launcher.gs` (`submitLauncherForm` payload mapping), `apps_script/m1_sheet_generator/src/GenerateSheet.gs` (`normalizeAndValidateConfig_` group handling), `docs/template_contract.md` (doctor-group declaration), `docs/sheet_generation_contract.md` §3A and §12.4.
