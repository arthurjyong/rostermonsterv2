// CompletenessValidator.gs
// Per-anchor cardinality / uniqueness / value-coverage validation per
// `docs/snapshot_adapter_contract.md` §6 step 5 + `docs/decision_log.md`
// D-0043 sub-decision 3. Protects against the partial-loss case where the
// operator deletes a single anchored row while siblings remain — without
// these checks the extractor would silently emit an incomplete snapshot
// that downstream parser/solver stages would treat as valid input.
//
// Each validator throws Error with a per-anchor message naming the
// specific deviation; the public entrypoint catches and renders.

// Validate doctor-row anchors per section against expectedDoctorCount.<X>.
// Per `docs/snapshot_adapter_contract.md` §6 step 5: each declared section
// MUST have exactly N anchors with values `<sectionKey>:0`..`<sectionKey>:N-1`,
// no missing index, no duplicates, no unexpected values.
function _validateDoctorRowCoverage_(anchors, expectedDoctorCounts, tabName) {
  // Group actual anchor values by section.
  var actualBySection = {};
  for (var i = 0; i < anchors.length; i++) {
    var v = anchors[i].value;
    var colonIdx = v.indexOf(':');
    if (colonIdx <= 0) {
      throw new Error(
        'EXTRACTION_ERROR: malformed doctorRow anchor value "' + v +
        '" on tab "' + tabName + '" (expected `<sectionKey>:<index>`).'
      );
    }
    var sectionKey = v.substring(0, colonIdx);
    var idxStr = v.substring(colonIdx + 1);
    var idx = parseInt(idxStr, 10);
    if (!isFinite(idx) || idx < 0 || String(idx) !== idxStr) {
      throw new Error(
        'EXTRACTION_ERROR: malformed doctorRow index "' + idxStr +
        '" on tab "' + tabName + '" (expected non-negative integer).'
      );
    }
    if (!actualBySection[sectionKey]) actualBySection[sectionKey] = [];
    actualBySection[sectionKey].push(idx);
  }

  // For each declared section, validate cardinality + coverage + uniqueness.
  var declaredSections = Object.keys(expectedDoctorCounts);
  for (var s = 0; s < declaredSections.length; s++) {
    var key = declaredSections[s];
    var expectedN = parseInt(String(expectedDoctorCounts[key]), 10);
    if (!isFinite(expectedN) || expectedN < 0) {
      throw new Error(
        'EXTRACTION_ERROR: malformed expectedDoctorCount.' + key +
        ' value "' + expectedDoctorCounts[key] + '" on tab "' + tabName +
        '" (expected non-negative integer).'
      );
    }
    var actualIndexes = actualBySection[key] || [];
    if (actualIndexes.length !== expectedN) {
      throw new Error(
        'EXTRACTION_ERROR: doctor row coverage mismatch on section ' + key +
        ' (tab "' + tabName + '") — expected ' + expectedN + ', got ' +
        actualIndexes.length + '.'
      );
    }
    // Check coverage = exact set {0..expectedN-1}.
    var seen = {};
    for (var j = 0; j < actualIndexes.length; j++) {
      var idxJ = actualIndexes[j];
      if (idxJ < 0 || idxJ >= expectedN) {
        throw new Error(
          'EXTRACTION_ERROR: doctor row index ' + idxJ + ' on section ' +
          key + ' is outside expected range [0, ' + (expectedN - 1) +
          '] (tab "' + tabName + '").'
        );
      }
      if (seen[idxJ]) {
        throw new Error(
          'EXTRACTION_ERROR: duplicate doctor row index ' + idxJ +
          ' on section ' + key + ' (tab "' + tabName + '").'
        );
      }
      seen[idxJ] = true;
    }
  }

  // Reverse check: every section that produced anchors is one we declared.
  var actualSections = Object.keys(actualBySection);
  for (var t = 0; t < actualSections.length; t++) {
    if (!Object.prototype.hasOwnProperty.call(
        expectedDoctorCounts, actualSections[t])) {
      throw new Error(
        'EXTRACTION_ERROR: unexpected doctorRow section "' +
        actualSections[t] + '" on tab "' + tabName +
        '" — no matching expectedDoctorCount sheet-level anchor.'
      );
    }
  }
}

// Section-header anchors (`rosterMonster:section`) MUST cover exactly the
// set of declared sections (one anchor per declared section, no duplicates,
// no extras).
function _validateSectionCoverage_(anchors, expectedDoctorCounts, tabName) {
  var declared = Object.keys(expectedDoctorCounts);
  declared.sort();

  var actual = anchors.map(function (a) { return a.value; });
  actual.sort();

  if (actual.length !== declared.length) {
    throw new Error(
      'EXTRACTION_ERROR: section coverage mismatch on tab "' + tabName +
      '" — expected ' + declared.length + ' sections, got ' + actual.length +
      '.'
    );
  }
  for (var i = 0; i < declared.length; i++) {
    if (declared[i] !== actual[i]) {
      throw new Error(
        'EXTRACTION_ERROR: section coverage mismatch on tab "' + tabName +
        '" — expected {' + declared.join(', ') + '}, got {' +
        actual.join(', ') + '}.'
      );
    }
  }
}

// Call-point row anchors have a template-fixed expected set per
// `docs/template_artifact_contract.md` §9 `pointRows` — for ICU/HD first
// release this is `{MICU_CALL_POINT, MHD_CALL_POINT}`.
function _validateCallPointRowCoverage_(anchors, tabName) {
  var EXPECTED = ['MICU_CALL_POINT', 'MHD_CALL_POINT'];
  _validateFixedSetCoverage_(anchors, EXPECTED, 'callPointRow', tabName);
}

// Component-ID row anchors have a template-fixed expected set per
// `docs/domain_model.md` §11.2 — the 9 first-release component identifiers.
function _validateComponentIdCoverage_(anchors, tabName) {
  var EXPECTED = [
    'unfilledPenalty',
    'pointBalanceWithinSection',
    'pointBalanceGlobal',
    'spacingPenalty',
    'preLeavePenalty',
    'crReward',
    'dualEligibleIcuBonus',
    'standbyAdjacencyPenalty',
    'standbyCountFairnessPenalty',
  ];
  _validateFixedSetCoverage_(anchors, EXPECTED, 'componentId', tabName);
}

// Assignment-row anchors: validates cardinality against the launcher-
// recorded `rosterMonster:expectedAssignmentRowCount` sheet-level anchor +
// uniqueness of the per-row `<surfaceId>:<rowOffset>` values. Catches the
// partial-loss case Codex P1 flagged on PR #96 — without the cardinality
// check, a deleted assignment row would silently omit its prefilled
// assignments from the snapshot, and the parser couldn't reconstruct the
// loss because missing rows produce no records. Exact value-coverage
// (which surfaceIds/rowOffsets are expected) is template-derived and the
// extractor doesn't have the template at runtime, so the parser admission
// stage cross-checks individual surfaceId:rowOffset values against the
// template per `docs/parser_normalizer_contract.md` §14 — that closes the
// "wrong rowOffset value but right count" residual.
function _validateAssignmentRowCoverage_(anchors, expectedCount, tabName) {
  if (anchors.length !== expectedCount) {
    throw new Error(
      'EXTRACTION_ERROR: assignmentRow coverage mismatch on tab "' + tabName +
      '" — expected ' + expectedCount + ', got ' + anchors.length +
      '. An assignment row may have been deleted or duplicated; regenerate ' +
      'via the launcher to recover the expected layout.'
    );
  }
  var seen = {};
  for (var i = 0; i < anchors.length; i++) {
    var v = anchors[i].value;
    if (seen[v]) {
      throw new Error(
        'EXTRACTION_ERROR: duplicate assignmentRow value "' + v +
        '" on tab "' + tabName + '".'
      );
    }
    seen[v] = true;
  }
}

// Generic fixed-set coverage check: actual values MUST equal EXPECTED set
// exactly (same elements, no duplicates, no extras).
function _validateFixedSetCoverage_(anchors, expectedSet, anchorName, tabName) {
  var expectedSorted = expectedSet.slice().sort();
  var actual = anchors.map(function (a) { return a.value; }).sort();

  if (actual.length !== expectedSorted.length) {
    throw new Error(
      'EXTRACTION_ERROR: ' + anchorName + ' coverage mismatch on tab "' +
      tabName + '" — expected {' + expectedSorted.join(', ') +
      '}, got {' + actual.join(', ') + '}.'
    );
  }
  for (var i = 0; i < expectedSorted.length; i++) {
    if (actual[i] !== expectedSorted[i]) {
      throw new Error(
        'EXTRACTION_ERROR: ' + anchorName + ' coverage mismatch on tab "' +
        tabName + '" — expected {' + expectedSorted.join(', ') +
        '}, got {' + actual.join(', ') + '}.'
      );
    }
  }
}
