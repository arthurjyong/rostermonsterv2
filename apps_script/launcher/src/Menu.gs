// Menu.gs
// Launcher UX (spreadsheet menu, sidebar, add-on flow, Google Form entrypoint) is
// intentionally deferred. This PR implements the generator core only. Public
// entrypoints live in GenerateSheet.gs and are invoked directly — via the Apps
// Script editor "Run" dropdown, `clasp run`, or a later launcher surface.

function onOpen() {
  // Intentionally empty: no menu is installed until launcher UX is in scope.
}
