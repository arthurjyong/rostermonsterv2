// Config.gs
// Library-level configuration accessors per `docs/decision_log.md`
// D-0049 / D-0051 / D-0052. Centralizing config in the library means:
//
// 1. ONE source of truth — set the value once on this Apps Script
//    project's Script Properties, all downstream consumers (the
//    launcher's writeback Web App route + every operator-bound shim
//    spawned by `makeCopy(template)`) read the same value via
//    `RMLib.getCloudRunUrl()`.
// 2. No `makeCopy()` propagation issue — Script Properties on bound
//    spreadsheets are NOT copied by `DriveApp.makeCopy()`. Putting the
//    URL on the library project (which is one project, never copied)
//    sidesteps that entirely.
// 3. Updates to the URL (region change, new deployment) propagate to
//    every consumer without re-pushing any code, because the library
//    is loaded at HEAD per D-0041 sub-decision 3.
//
// **Operator-side setup** (one-time per environment):
//   1. Open this Apps Script project in the Apps Script editor.
//   2. Project Settings → Script Properties → Add script property.
//   3. Property name: `CLOUD_RUN_URL`
//      Value: the Cloud Run service URL (e.g.,
//             `https://roster-monster-compute-693837275969.asia-southeast1.run.app`)
//   4. Save.
//
// The bound shim's "Solve Roster" handler will throw a clear
// CONFIG_ERROR pointing here if the property is unset.

function getCloudRunUrl() {
  return PropertiesService.getScriptProperties().getProperty('CLOUD_RUN_URL');
}
