/*
 * Tlačítka "Kopírovat do schránky" v Django adminu (kód závodu, údaje pro
 * BMX Event Control). Hodnota se předává v data-copy-value, aby v šablonách
 * nebyl žádný inline JS (CSP nepovoluje unsafe-inline pro script-src).
 */
(function () {
  "use strict";

  var DONE_LABEL = "Zkopírováno ✓";
  var FAIL_LABEL = "Nepodařilo se zkopírovat";

  function flash(button, label) {
    var original = button.dataset.originalLabel || button.textContent;
    button.dataset.originalLabel = original;
    button.textContent = label;
    window.setTimeout(function () {
      button.textContent = original;
    }, 2000);
  }

  function legacyCopy(value) {
    var field = document.createElement("textarea");
    field.value = value;
    field.setAttribute("readonly", "readonly");
    field.style.position = "fixed";
    field.style.opacity = "0";
    document.body.appendChild(field);
    field.select();
    var copied = false;
    try {
      copied = document.execCommand("copy");
    } catch (error) {
      copied = false;
    }
    document.body.removeChild(field);
    return copied;
  }

  function copy(button) {
    var value = button.dataset.copyValue || "";
    if (!value) {
      return;
    }
    if (navigator.clipboard && window.isSecureContext) {
      navigator.clipboard.writeText(value).then(
        function () {
          flash(button, DONE_LABEL);
        },
        function () {
          flash(button, legacyCopy(value) ? DONE_LABEL : FAIL_LABEL);
        }
      );
      return;
    }
    flash(button, legacyCopy(value) ? DONE_LABEL : FAIL_LABEL);
  }

  document.addEventListener("click", function (event) {
    var button = event.target.closest(".bmx-copy-btn");
    if (!button) {
      return;
    }
    event.preventDefault();
    copy(button);
  });
})();
