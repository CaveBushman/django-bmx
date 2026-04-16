document.addEventListener("DOMContentLoaded", function () {
  var riderFiltersForm = document.getElementById("riderFiltersForm");
  if (riderFiltersForm) {
    riderFiltersForm.addEventListener("submit", function () {
      var pageInput = riderFiltersForm.querySelector('input[name="page"]');
      if (pageInput) {
        pageInput.remove();
      }
    });
  }

  document.querySelectorAll("[data-rider-detail-url]").forEach(function (row) {
    row.addEventListener("click", function (event) {
      if (event.target.closest("a, button, input, select, textarea, label")) {
        return;
      }
      window.location = row.dataset.riderDetailUrl;
    });

    row.addEventListener("keydown", function (event) {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        window.location = row.dataset.riderDetailUrl;
      }
    });

    row.setAttribute("tabindex", "0");
  });

  document.querySelectorAll("[data-rider-photo]").forEach(function (image) {
    image.addEventListener("error", function () {
      image.classList.add("hidden");
      var fallback = image.nextElementSibling;
      if (fallback) {
        fallback.classList.remove("hidden");
        fallback.classList.add("flex");
      }
    });
  });
});
