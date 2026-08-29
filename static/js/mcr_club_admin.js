(function () {
  "use strict";

  // <details> se zavírá jen kliknutím na vlastní summary. Rozbalená nabídka
  // tak zůstane viset přes obsah i poté, co uživatel klikne jinam nebo zmáčkne
  // Escape — a protože překrývá tlačítka pod sebou, vypadá to jako zaseknutá
  // stránka. Doplňujeme proto obojí zavření.
  var pickers = Array.prototype.slice.call(
    document.querySelectorAll("details[data-outside-close]")
  );
  if (!pickers.length) {
    return;
  }

  function closeAll(except) {
    pickers.forEach(function (picker) {
      if (picker.open && picker !== except) {
        picker.open = false;
      }
    });
  }

  document.addEventListener("click", function (event) {
    pickers.forEach(function (picker) {
      if (picker.open && !picker.contains(event.target)) {
        picker.open = false;
      }
    });
  });

  document.addEventListener("keydown", function (event) {
    if (event.key !== "Escape" && event.key !== "Esc") {
      return;
    }
    var open = pickers.filter(function (picker) {
      return picker.open;
    });
    if (!open.length) {
      return;
    }
    closeAll();
    // Fokus zpět na tlačítko, které nabídku otevřelo, ať se ovládá i klávesnicí.
    var summary = open[0].querySelector("summary");
    if (summary) {
      summary.focus();
    }
  });

  // Otevření jedné nabídky zavře ostatní — kdyby jich na stránce přibylo.
  pickers.forEach(function (picker) {
    picker.addEventListener("toggle", function () {
      if (picker.open) {
        closeAll(picker);
      }
    });
  });
})();
