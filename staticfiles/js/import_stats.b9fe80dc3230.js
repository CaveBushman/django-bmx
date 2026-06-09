var IMPORT_STATS_SPINNER =
  '<svg class="animate-spin h-3.5 w-3.5" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">' +
  '<circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>' +
  '<path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>' +
  "</svg>";

function setFileInputState(input) {
  var hasFiles = input.files && input.files.length > 0;

  input.classList.toggle("is-selected", hasFiles);
  input.classList.toggle("bg-indigo-50", hasFiles);
  input.classList.toggle("border-indigo-300", hasFiles);
}

function initImportStatsFileInputs(documentRef) {
  documentRef.querySelectorAll('#uploadForm input[type="file"]').forEach(function (input) {
    setFileInputState(input);
    input.addEventListener("change", function () {
      setFileInputState(input);
    });
  });
}

function rememberButtonLabel(button) {
  if (!button.dataset.originalLabel) {
    button.dataset.originalLabel = button.innerHTML;
  }
}

function setSubmitButtonsDisabled(form, disabled) {
  form.querySelectorAll('button[type="submit"]').forEach(function (button) {
    button.disabled = disabled;
    if (!disabled && button.dataset.originalLabel) {
      button.innerHTML = button.dataset.originalLabel;
    }
  });
}

function setSubmittingLabel(submitter, submitButton) {
  rememberButtonLabel(submitter);

  if (submitter === submitButton) {
    submitter.innerHTML = "Nahrávám... " + IMPORT_STATS_SPINNER;
  } else {
    submitter.innerHTML = IMPORT_STATS_SPINNER;
  }
}

function initImportStatsForm(documentRef, windowRef) {
  var form = documentRef.getElementById("uploadForm");
  if (!form) {
    return;
  }

  var lastSubmitter = null;
  form.querySelectorAll('button[type="submit"]').forEach(function (button) {
    rememberButtonLabel(button);
    button.addEventListener("click", function () {
      lastSubmitter = button;
    });
  });

  form.addEventListener("submit", function (event) {
    if (form.dataset.submitting === "true") {
      event.preventDefault();
      return;
    }

    var submitter = event.submitter || lastSubmitter;
    if (!submitter) {
      return;
    }

    form.dataset.submitting = "true";
    setSubmittingLabel(submitter, documentRef.getElementById("submitBtn"));
    setSubmitButtonsDisabled(form, true);

    windowRef.setTimeout(function () {
      form.dataset.submitting = "false";
      setSubmitButtonsDisabled(form, false);
    }, 30000);
  });
}

function initImportStats(documentRef, windowRef) {
  initImportStatsFileInputs(documentRef);
  initImportStatsForm(documentRef, windowRef);
}

if (typeof document !== "undefined" && typeof window !== "undefined") {
  document.addEventListener("DOMContentLoaded", function () {
    initImportStats(document, window);
  });
}

if (typeof module !== "undefined") {
  module.exports = {
    initImportStats: initImportStats,
    initImportStatsFileInputs: initImportStatsFileInputs,
    initImportStatsForm: initImportStatsForm,
    setFileInputState: setFileInputState,
    setSubmitButtonsDisabled: setSubmitButtonsDisabled,
  };
}
