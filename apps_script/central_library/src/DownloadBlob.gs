// DownloadBlob.gs
// Output transport per `docs/decision_log.md` D-0040 +
// `docs/snapshot_adapter_contract.md` §7.
//
// Apps Script doesn't expose a direct "trigger browser download" API from a
// menu handler. The standard pattern is to render an HTML page that contains
// the file content as a base64 data URI and a small JavaScript snippet that
// programmatically triggers the download on page load. The bound shim's
// `showModalDialog` displays this HTML, the operator sees a brief "Snapshot
// ready" dialog, and their browser saves the file.

function _buildDownloadHtml_(jsonString, filename) {
  // Encode the JSON as a base64 data URI. UTF-8 safe via Utilities.base64Encode
  // which accepts a string of bytes (Apps Script V8 uses UTF-16 internally;
  // we explicitly convert to UTF-8 byte array first).
  var bytes = Utilities.newBlob(jsonString).setContentType('application/json')
    .getBytes();
  var base64 = Utilities.base64Encode(bytes);
  var dataUri = 'data:application/json;base64,' + base64;

  // Small HTML page with a download link that auto-clicks on load. Operator
  // sees a brief modal then their browser saves the file. The link is also
  // visible as a manual fallback if the auto-click is blocked.
  var safeFilename = _escapeHtmlAttr_(filename);
  var html =
    '<!DOCTYPE html><html><head><base target="_top">' +
    '<style>body{font-family:Arial,sans-serif;padding:20px;}</style>' +
    '</head><body>' +
    '<p><strong>Snapshot ready.</strong></p>' +
    '<p>If your browser doesn\'t download it automatically, click ' +
    '<a id="dl" href="' + dataUri + '" download="' + safeFilename + '">' +
    safeFilename + '</a>.</p>' +
    '<p>Then run on your laptop:</p>' +
    '<pre>python -m rostermonster.run --snapshot &lt;path-to-' + safeFilename + '&gt;</pre>' +
    '<script>' +
    'document.addEventListener("DOMContentLoaded",function(){' +
    'var a=document.getElementById("dl");if(a)a.click();' +
    '});' +
    '</script>' +
    '</body></html>';
  return HtmlService.createHtmlOutput(html).setWidth(540).setHeight(220);
}

// Error variant of the modal — same shape, but no download link.
function _buildErrorHtml_(message) {
  var safe = _escapeHtmlText_(message);
  var html =
    '<!DOCTYPE html><html><head><base target="_top">' +
    '<style>body{font-family:Arial,sans-serif;padding:20px;}' +
    '.err{color:#a40000;background:#fff0f0;padding:10px;border-radius:4px;}' +
    '</style></head><body>' +
    '<p><strong>Extraction failed.</strong></p>' +
    '<div class="err">' + safe + '</div>' +
    '<p>If the message says the sheet may predate the M2 C9 metadata ' +
    'extension, regenerate the period via the launcher and retry.</p>' +
    '</body></html>';
  return HtmlService.createHtmlOutput(html).setWidth(560).setHeight(240);
}

function _escapeHtmlAttr_(s) {
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

function _escapeHtmlText_(s) {
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}
