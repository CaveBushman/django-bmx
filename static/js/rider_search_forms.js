document.addEventListener("DOMContentLoaded", function () {
  var plateForm = document.querySelector("[data-plate-search-form]");
  var plateInput = document.querySelector("[data-plate-search-input]");

  if (plateInput) {
    plateInput.addEventListener("input", function () {
      plateInput.value = plateInput.value.replace(/[^0-9]/g, "");
    });
  }

  if (plateForm && plateInput) {
    plateForm.addEventListener("submit", function (event) {
      var value = plateInput.value.trim();
      if (!/^\d+$/.test(value)) {
        window.alert("Zadej startovní číslo pouze jako číslice.");
        plateInput.focus();
        event.preventDefault();
        return;
      }
      plateInput.value = value;
    });
  }

  var transponderForm = document.querySelector("[data-transponder-search-form]");
  var transponderInput = document.querySelector("[data-transponder-search-input]");
  var transponderPattern = /^[A-Z]{2}-\d{5}$/;

  if (transponderInput) {
    transponderInput.addEventListener("input", function () {
      transponderInput.value = transponderInput.value.toUpperCase();
    });
  }

  if (transponderForm && transponderInput) {
    transponderForm.addEventListener("submit", function (event) {
      var value = transponderInput.value.trim().toUpperCase();
      if (!transponderPattern.test(value)) {
        window.alert("Zadej čip v plném tvaru XX-11111.");
        transponderInput.focus();
        event.preventDefault();
        return;
      }
      transponderInput.value = value;
    });
  }
});
