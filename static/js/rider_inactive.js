function initRiderInactiveModal(documentRef) {
  var modal = documentRef.getElementById("inactive-release-modal");
  var riderLabel = documentRef.getElementById("inactive-release-modal-rider");
  var closeButton = documentRef.getElementById("inactive-release-modal-close");
  var cancelButton = documentRef.getElementById("inactive-release-modal-cancel");
  var confirmButton = documentRef.getElementById("inactive-release-modal-confirm");
  var triggers = documentRef.querySelectorAll("[data-release-trigger]");

  if (!modal || !riderLabel || !closeButton || !cancelButton || !confirmButton || !triggers.length) {
    return;
  }

  var pendingForm = null;

  function closeModal() {
    modal.classList.add("hidden");
    if (documentRef.body && documentRef.body.classList) {
      documentRef.body.classList.remove("overflow-hidden");
    }
    pendingForm = null;
  }

  triggers.forEach(function (trigger) {
    trigger.addEventListener("click", function (event) {
      event.preventDefault();
      pendingForm = trigger.closest("[data-release-form]");
      if (!pendingForm) {
        return;
      }

      riderLabel.textContent = pendingForm.dataset.riderName || "vybraný jezdec";
      modal.classList.remove("hidden");
      if (documentRef.body && documentRef.body.classList) {
        documentRef.body.classList.add("overflow-hidden");
      }
    });
  });

  confirmButton.addEventListener("click", function () {
    if (pendingForm && typeof pendingForm.submit === "function") {
      pendingForm.submit();
    }
  });

  closeButton.addEventListener("click", closeModal);
  cancelButton.addEventListener("click", closeModal);
  modal.addEventListener("click", function (event) {
    if (event.target === modal || event.target === modal.firstElementChild) {
      closeModal();
    }
  });

  documentRef.addEventListener("keydown", function (event) {
    if (event.key === "Escape" && !modal.classList.contains("hidden")) {
      closeModal();
    }
  });
}

if (typeof document !== "undefined") {
  document.addEventListener("DOMContentLoaded", function () {
    initRiderInactiveModal(document);
  });
}

if (typeof module !== "undefined") {
  module.exports = { initRiderInactiveModal: initRiderInactiveModal };
}
