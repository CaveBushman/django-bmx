function initEventAdmin(documentRef) {
  var form = documentRef.querySelector("[data-event-admin-form]");
  if (!form) {
    return;
  }

  function updateFileSelection(input) {
    var field = input.closest("[data-file-field]");
    if (!field) {
      return;
    }

    var status = field.querySelector("[data-file-selection]");
    if (!status) {
      return;
    }

    var files = input.files || [];
    if (!files.length) {
      status.textContent = "Zadny soubor nevybran";
      status.dataset.hasFile = "false";
      return;
    }

    if (files.length === 1) {
      status.textContent = "Vybrano: " + files[0].name;
      status.dataset.hasFile = "true";
      return;
    }

    status.textContent = "Vybrano souboru: " + files.length;
    status.dataset.hasFile = "true";
  }

  form.querySelectorAll("[data-file-input]").forEach(function (input) {
    updateFileSelection(input);
    input.addEventListener("change", function () {
      updateFileSelection(input);
    });
  });

  form.addEventListener("submit", function (event) {
    var submitter = event.submitter;
    if (!submitter || !submitter.dataset.loadingLabel) {
      return;
    }

    submitter.disabled = true;
    submitter.dataset.defaultLabel = submitter.innerHTML;
    submitter.innerHTML =
      submitter.dataset.loadingLabel +
      ' <svg class="ml-1 inline h-4 w-4 animate-spin text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 0 1 8-8V0C5.373 0 0 5.373 0 12h4Zm2 5.291A7.962 7.962 0 0 1 4 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647Z"></path></svg>';
  });
}

if (typeof document !== "undefined") {
  document.addEventListener("DOMContentLoaded", function () {
    initEventAdmin(document);
  });
}

if (typeof module !== "undefined") {
  module.exports = { initEventAdmin: initEventAdmin };
}
