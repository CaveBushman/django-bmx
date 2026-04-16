function initFlashMessages(documentRef, windowRef) {
  var flashMessages = documentRef.querySelectorAll("[data-flash-message]");
  if (!flashMessages.length) {
    return;
  }

  windowRef.setTimeout(function () {
    flashMessages.forEach(function (message) {
      message.classList.add("opacity-0");
      windowRef.setTimeout(function () {
        if (typeof message.remove === "function") {
          message.remove();
        }
      }, 500);
    });
  }, 5000);
}

function initConfirmButtons(documentRef, windowRef) {
  documentRef.addEventListener("click", function (event) {
    var confirmButton = event.target.closest("[data-confirm-message]");
    if (!confirmButton) {
      return;
    }

    if (!windowRef.confirm(confirmButton.dataset.confirmMessage || "Are you sure?")) {
      event.preventDefault();
    }
  });
}

function initBase(documentRef, windowRef) {
  initFlashMessages(documentRef, windowRef);
  initConfirmButtons(documentRef, windowRef);
}

if (typeof document !== "undefined" && typeof window !== "undefined") {
  document.addEventListener("DOMContentLoaded", function () {
    initBase(document, window);
  });
}

if (typeof module !== "undefined") {
  module.exports = {
    initBase: initBase,
    initConfirmButtons: initConfirmButtons,
    initFlashMessages: initFlashMessages,
  };
}
