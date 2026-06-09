document.addEventListener("DOMContentLoaded", function () {
  document.querySelectorAll('#uploadForm input[type="file"]').forEach(function (input) {
    input.addEventListener("change", function () {
      var hasFiles = input.files && input.files.length > 0;
      input.classList.toggle("bg-indigo-50", hasFiles);
      input.classList.toggle("dark:bg-indigo-900/20", hasFiles);
      input.classList.toggle("border-indigo-300", hasFiles);
      input.classList.toggle("dark:border-indigo-700", hasFiles);
    });
  });

  var form = document.getElementById("uploadForm");
  if (!form) return;

  var SPINNER =
    '<svg class="animate-spin h-3.5 w-3.5" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">' +
    '<circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>' +
    '<path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>' +
    "</svg>";

  function lockForm() {
    form.querySelectorAll('button[type="submit"]').forEach(function (btn) {
      btn.disabled = true;
    });
    // NOTE: file inputs must NOT be disabled — disabled inputs are excluded
    // from form submission, which would cause files to be silently dropped.
  }

  function scheduleUnlock() {
    setTimeout(function () {
      form.querySelectorAll('button[type="submit"]').forEach(function (btn) {
        btn.disabled = false;
      });
    }, 30000);
  }

  form.addEventListener("submit", function (event) {
    var submitter = event.submitter;
    if (!submitter) return;

    var submitBtn = document.getElementById("submitBtn");
    if (submitter === submitBtn) {
      submitter.innerHTML = "Nahrávám… " + SPINNER;
    } else {
      submitter.innerHTML = SPINNER;
    }

    lockForm();
    scheduleUnlock();
  });
});
