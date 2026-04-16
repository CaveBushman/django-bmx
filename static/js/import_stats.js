document.addEventListener("DOMContentLoaded", function () {
  var fileInputs = document.querySelectorAll('#uploadForm input[type="file"]');
  fileInputs.forEach(function (input) {
    input.addEventListener("change", function () {
      var hasFiles = input.files && input.files.length > 0;
      input.classList.toggle("bg-indigo-50", hasFiles);
      input.classList.toggle("dark:bg-indigo-900/20", hasFiles);
      input.classList.toggle("border-indigo-300", hasFiles);
      input.classList.toggle("dark:border-indigo-700", hasFiles);
    });
  });

  var form = document.getElementById("uploadForm");
  var submitButton = document.getElementById("submitBtn");
  if (!form || !submitButton) {
    return;
  }

  submitButton.dataset.defaultLabel = submitButton.innerHTML;
  form.addEventListener("submit", function (event) {
    if (!event.submitter || event.submitter.id !== "submitBtn") {
      return;
    }

    submitButton.disabled = true;
    submitButton.innerHTML =
      'Nahrávám... <svg class="animate-spin ml-1 -mr-1 h-4 w-4 text-white inline" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg>';
  });
});
