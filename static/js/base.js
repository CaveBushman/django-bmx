function initFlashMessages(documentRef, windowRef) {
  var flashMessages = documentRef.querySelectorAll("[data-flash-message]");
  if (!flashMessages.length) {
    return;
  }

  flashMessages.forEach(function (message) {
    if (message.hasAttribute("data-flash-persist")) {
      return;
    }
    var timeout = parseInt(message.dataset.flashTimeout, 10) || 5000;
    windowRef.setTimeout(function () {
      message.classList.add("opacity-0");
      windowRef.setTimeout(function () {
        if (typeof message.remove === "function") {
          message.remove();
        }
      }, 500);
    }, timeout);
  });
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
