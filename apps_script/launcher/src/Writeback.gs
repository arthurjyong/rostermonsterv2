// Writeback.gs
// Thin delegate shim per `docs/decision_log.md` D-0052: the writeback
// library implementation moved to the central library
// (`apps_script/central_library/src/Writeback.gs`) so the bound
// shim's "Solve Roster" menu can invoke it inline without a launcher
// Web App round-trip. The launcher's existing writeback Web App route
// (per D-0046, file-upload-via-launcher-form path) keeps its
// `google.script.run.applyWriteback(jsonString)` surface — `google.script.run`
// can only reach functions in the calling Apps Script project, NOT
// library functions, so this thin wrapper exists in the launcher
// project to delegate to `RMLib.applyWriteback(...)`.
//
// One library implementation, two consumers (launcher Web App form +
// bound shim "Solve Roster" menu) — same writeback contract §17
// 3-state diagnostic surface in both paths.

// Public function reachable from `WritebackForm.html` via
// `google.script.run.applyWriteback(envelopeJsonString)`.
//
// `RMLib` is the central library declared in `appsscript.json` under
// `dependencies.libraries[].userSymbol = "RMLib"` — the same symbol
// the bound shim uses, with the launcher's library import added in
// M4 C1 Phase 2 per D-0052 sub-decision 2.
function applyWriteback(envelopeJsonString) {
  return RMLib.applyWriteback(envelopeJsonString);
}
