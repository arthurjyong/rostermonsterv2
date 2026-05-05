// AnalysisRenderer.gs (launcher delegate shim)
// Same delegate-shim pattern as `Writeback.gs` per
// `docs/decision_log.md` D-0052: the renderer implementation lives in
// the central library (`apps_script/central_library/src/AnalysisRenderer.gs`)
// per D-0060. The launcher's analysis-render Web App route per D-0063
// can only invoke functions in the calling Apps Script project via
// `google.script.run`, NOT library functions, so this thin wrapper
// exists in the launcher project to delegate to `RMLib.renderAnalysis(...)`.
//
// One library implementation, single consumer (launcher Web App form) —
// same `docs/analysis_renderer_contract.md` §10 + §16 result shape both
// in the library and on the wire to the operator.

// Public function reachable from `AnalysisRendererForm.html` via
// `google.script.run.renderAnalysis(outputJsonString)`.
//
// `RMLib` is the central library declared in `appsscript.json` under
// `dependencies.libraries[].userSymbol = "RMLib"` — the same symbol
// the bound shim uses.
function renderAnalysis(outputJsonString) {
  return RMLib.renderAnalysis(outputJsonString);
}
