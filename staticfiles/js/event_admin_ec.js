function initEventAdminEc(documentRef) {
  var paymentEl = documentRef.getElementById("payment-amount");
  if (paymentEl) {
    var value = parseInt(paymentEl.textContent.replace(/\D/g, ""), 10);
    if (!Number.isNaN(value)) {
      paymentEl.textContent = value.toLocaleString("cs-CZ") + " CZK";
    }
  }

  var addButton = documentRef.getElementById("ec-results-add-input");
  var inputsWrapper = documentRef.getElementById("ec-results-inputs");
  var submitButton = documentRef.getElementById("ec-results-submit");
  var uploadForm = addButton ? addButton.closest("form") : null;

  if (!addButton || !inputsWrapper) {
    return;
  }

  function createInputRow(index) {
    var row = documentRef.createElement("div");
    row.className = "ec-results-input-row";

    var header = documentRef.createElement("div");
    header.className = "ec-results-input-header";

    var label = documentRef.createElement("label");
    label.className = "block text-sm font-semibold text-slate-700 dark:text-slate-200";
    label.textContent = "PDF výsledků " + index;

    var removeButton = documentRef.createElement("button");
    removeButton.type = "button";
    removeButton.className = "ec-results-remove";
    removeButton.setAttribute("aria-label", "Odebrat PDF výsledků " + index);
    removeButton.setAttribute("title", "Odebrat toto pole");
    removeButton.textContent = "−";

    var input = documentRef.createElement("input");
    input.type = "file";
    input.name = "results-pdf-files";
    input.accept = ".pdf,application/pdf";
    input.className =
      "block w-full cursor-pointer rounded-md border border-gray-300 bg-white text-sm text-gray-900 focus:ring-2 focus:ring-blue-600";

    header.appendChild(label);
    header.appendChild(removeButton);
    row.appendChild(header);
    row.appendChild(input);
    return row;
  }

  function renumberInputs() {
    inputsWrapper.querySelectorAll(".ec-results-input-row").forEach(function (row, index) {
      var label = row.querySelector("label");
      if (label) {
        label.textContent = "PDF výsledků " + (index + 1);
      }

      var removeButton = row.querySelector(".ec-results-remove");
      if (removeButton) {
        removeButton.setAttribute("aria-label", "Odebrat PDF výsledků " + (index + 1));
      }
    });
  }

  addButton.addEventListener("click", function () {
    var nextIndex = inputsWrapper.querySelectorAll(".ec-results-input-row").length + 1;
    inputsWrapper.appendChild(createInputRow(nextIndex));
  });

  inputsWrapper.addEventListener("click", function (event) {
    var removeButton = event.target.closest(".ec-results-remove");
    if (!removeButton) {
      return;
    }

    var row = removeButton.closest(".ec-results-input-row");
    if (!row) {
      return;
    }

    row.remove();
    renumberInputs();
  });

  if (uploadForm && submitButton) {
    submitButton.dataset.defaultLabel = submitButton.innerHTML;
    uploadForm.addEventListener("submit", function (event) {
      if (!event.submitter || event.submitter !== submitButton) {
        return;
      }

      submitButton.disabled = true;
      submitButton.innerHTML =
        (submitButton.dataset.loadingLabel || "Nahrávám...") +
        ' <svg class="animate-spin ml-1 -mr-1 h-4 w-4 text-white inline" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg>';
    });
  }
}

if (typeof document !== "undefined") {
  document.addEventListener("DOMContentLoaded", function () {
    initEventAdminEc(document);
  });
}

if (typeof module !== "undefined") {
  module.exports = { initEventAdminEc: initEventAdminEc };
}
