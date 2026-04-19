// TemplateData.gs
// Loader that returns the first-release ICU/HD template artifact. This PR supports
// exactly one department ("CGH ICU/HD Call"); additional departments are out of scope.

var ICU_HD_DEPARTMENT_LABEL_ = 'CGH ICU/HD Call';

function loadIcuHdTemplate_() {
  return ICU_HD_TEMPLATE_ARTIFACT;
}

function loadTemplateArtifactByDepartment_(department) {
  var label = (department == null ? '' : String(department)).trim();
  if (label === '' || label === ICU_HD_DEPARTMENT_LABEL_) {
    return ICU_HD_TEMPLATE_ARTIFACT;
  }
  throw new Error(
    'Unsupported department "' + label + '". First-release generator only supports "' +
    ICU_HD_DEPARTMENT_LABEL_ + '".');
}
