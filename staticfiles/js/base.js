document.addEventListener("DOMContentLoaded", function () {
  var flashMessages = document.querySelectorAll("[data-flash-message]");
  if (!flashMessages.length) {
  } else {
    window.setTimeout(function () {
      flashMessages.forEach(function (message) {
        message.classList.add("opacity-0");
        window.setTimeout(function () {
          message.remove();
        }, 500);
      });
    }, 5000);
  }

  document.addEventListener("click", function (event) {
    var confirmButton = event.target.closest("[data-confirm-message]");
    if (!confirmButton) {
      return;
    }

    if (!window.confirm(confirmButton.dataset.confirmMessage || "Are you sure?")) {
      event.preventDefault();
    }
  });
});
