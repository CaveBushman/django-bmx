function initEventAdmin(documentRef) {
  var form = documentRef.querySelector("[data-event-admin-form]");
  if (!form) {
    return;
  }

  var timingConfig = {
    rem: {
      heading: "Soubory pro REM",
      note: "Výchozí režim pro běžné závody. Přepni na BEM jen při práci s XLS exporty a importem výsledků z BEM.",
      resultsHelp: "Nahrání TXT souboru s výsledky z REM.",
      fileTypeHelp: "Pouze txt soubory"
    },
    bem: {
      heading: "Soubory pro BEM",
      note: "BEM režim použij pro XLS startovky, seznam jezdců a import výsledků z BEM.",
      resultsHelp: "Nahrání XLS nebo XLSX souboru s výsledky z BEM.",
      fileTypeHelp: "Pouze xls a xlsx soubory"
    }
  };

  function updateFileSelection(input) {
    var field = input.closest("[data-file-field]");
    if (!field) {
      return;
    }

    var status = field.querySelector("[data-file-selection]");
    if (!status) {
      return;
    }
    var uploadTitle = field.querySelector("[data-upload-title]");
    var uploadSubtitle = field.querySelector("[data-upload-subtitle]");

    var files = input.files || [];
    if (!files.length) {
      status.textContent = "Zadny soubor nevybran";
      status.dataset.hasFile = "false";
      if (uploadTitle) {
        uploadTitle.textContent = "Vybrat nebo přetáhnout soubor";
      }
      if (uploadSubtitle) {
        uploadSubtitle.textContent = "Soubor se nahraje až po potvrzení tlačítkem Nahrát.";
      }
      return;
    }

    if (files.length === 1) {
      status.textContent = "Vybrano: " + files[0].name;
      status.dataset.hasFile = "true";
      if (uploadTitle) {
        uploadTitle.textContent = files[0].name;
      }
      if (uploadSubtitle) {
        uploadSubtitle.textContent = "Připraveno k nahrání.";
      }
      return;
    }

    status.textContent = "Vybrano souboru: " + files.length;
    status.dataset.hasFile = "true";
    if (uploadTitle) {
      uploadTitle.textContent = "Vybrano souboru: " + files.length;
    }
    if (uploadSubtitle) {
      uploadSubtitle.textContent = "Připraveno k nahrání.";
    }
  }

  form.querySelectorAll("[data-file-input]").forEach(function (input) {
    updateFileSelection(input);
    input.addEventListener("change", function () {
      updateFileSelection(input);
    });
  });

  form.querySelectorAll("[data-file-dropzone]").forEach(function (dropzone) {
    var field = dropzone.closest("[data-file-field]");
    var input = field ? field.querySelector("[data-file-input]") : null;
    if (!input) {
      return;
    }

    ["dragenter", "dragover"].forEach(function (eventName) {
      dropzone.addEventListener(eventName, function (event) {
        event.preventDefault();
        dropzone.dataset.dragActive = "true";
      });
    });

    ["dragleave", "drop"].forEach(function (eventName) {
      dropzone.addEventListener(eventName, function (event) {
        event.preventDefault();
        dropzone.dataset.dragActive = "false";
      });
    });

    dropzone.addEventListener("drop", function (event) {
      var files = event.dataTransfer ? event.dataTransfer.files : null;
      if (!files || !files.length) {
        return;
      }
      input.files = files;
      updateFileSelection(input);
    });
  });

  function setDatasetValue(element, attribute, mode) {
    var key = mode + attribute.charAt(0).toUpperCase() + attribute.slice(1);
    if (element.dataset[key] !== undefined) {
      element[attribute] = element.dataset[key];
    }
  }

  function applyTimingMode(mode) {
    var config = timingConfig[mode] || timingConfig.rem;
    var section = form.querySelector("[data-timing-section]");
    if (!section) {
      return;
    }

    var heading = section.querySelector("[data-timing-heading]");
    var note = section.querySelector("[data-timing-note]");
    var resultsHelp = section.querySelector("[data-results-help]");
    var fileTypeHelp = section.querySelector("[data-file-type-help]");

    if (heading) {
      heading.textContent = config.heading;
    }
    if (note) {
      note.textContent = config.note;
    }
    if (resultsHelp) {
      resultsHelp.textContent = config.resultsHelp;
    }
    if (fileTypeHelp) {
      fileTypeHelp.textContent = config.fileTypeHelp;
    }

    section.querySelectorAll("[data-timing-mode]").forEach(function (button) {
      button.setAttribute("aria-pressed", button.dataset.timingMode === mode ? "true" : "false");
    });

    section.querySelectorAll("[data-timing-action]").forEach(function (element) {
      setDatasetValue(element, "name", mode);
      setDatasetValue(element, "value", mode);
      if (element.dataset[mode + "LoadingLabel"] !== undefined) {
        element.dataset.loadingLabel = element.dataset[mode + "LoadingLabel"];
      }
      if (element.dataset[mode + "ConfirmMessage"] !== undefined) {
        element.dataset.confirmMessage = element.dataset[mode + "ConfirmMessage"];
      }
      if (element.dataset[mode + "HasResults"] !== undefined) {
        var hasResults = element.dataset[mode + "HasResults"] === "true";
        element.disabled = element.dataset.timingAction === "upload" ? hasResults : !hasResults;
      }
    });

    section.querySelectorAll("[data-file-input]").forEach(function (input) {
      setDatasetValue(input, "name", mode);
      setDatasetValue(input, "accept", mode);
      input.value = "";
      updateFileSelection(input);
    });
  }

  form.querySelectorAll("[data-timing-section]").forEach(function (section) {
    var defaultMode = section.dataset.defaultMode || "rem";
    section.querySelectorAll("[data-timing-mode]").forEach(function (button) {
      button.addEventListener("click", function () {
        applyTimingMode(button.dataset.timingMode || defaultMode);
      });
    });
    applyTimingMode(defaultMode);
  });

  form.addEventListener("submit", function (event) {
    var submitter = event.submitter;
    if (!submitter || !submitter.dataset.loadingLabel) {
      return;
    }

    if (submitter.dataset.confirmMessage && !window.confirm(submitter.dataset.confirmMessage)) {
      event.preventDefault();
      return;
    }

    form.querySelectorAll("input[data-event-admin-action]").forEach(function (input) {
      input.remove();
    });

    if (submitter.name) {
      var actionInput = documentRef.createElement("input");
      actionInput.type = "hidden";
      actionInput.name = submitter.name;
      actionInput.value = submitter.value || "1";
      actionInput.dataset.eventAdminAction = "true";
      form.appendChild(actionInput);
    }

    submitter.disabled = true;
    submitter.dataset.defaultLabel = submitter.innerHTML;
    submitter.innerHTML =
      submitter.dataset.loadingLabel +
      ' <svg class="ml-1 inline h-4 w-4 animate-spin text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 0 1 8-8V0C5.373 0 0 5.373 0 12h4Zm2 5.291A7.962 7.962 0 0 1 4 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647Z"></path></svg>';

    if (submitter.dataset.resetAfterDownload === "true") {
      window.setTimeout(function () {
        submitter.disabled = false;
        submitter.innerHTML = submitter.dataset.defaultLabel;
      }, 2500);
    }
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
