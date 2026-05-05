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
//
// Per `docs/analysis_renderer_contract.md` §11.3, the launcher's route
// is the layer that deserializes the operator-uploaded JSON string
// before calling `RMLib.renderAnalysis(output)`. The library's
// boundary is the in-memory `AnalyzerOutput` object per §6 + §9.
// On parse failure we surface the structured `AnalysisRendererResult`
// shape per §16 directly so the form's response handler renders the
// failure card consistently with library-side admission failures.
function renderAnalysis(outputJsonString) {
  var output;
  try {
    output = JSON.parse(outputJsonString);
  } catch (e) {
    return {
      state: 'FAILED',
      newTabIds: [],
      newTabNames: [],
      error: {
        code: 'INVALID_INPUT_VERSION',
        message: 'Could not parse uploaded JSON as AnalyzerOutput: ' +
          (e && e.message ? e.message : String(e)),
      },
    };
  }
  return RMLib.renderAnalysis(output);
}
