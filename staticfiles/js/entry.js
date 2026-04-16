
function applyEntryFilters() {
  var lastNameInput = document.getElementById("inputLastName");
  var clubInput = document.getElementById("inputClub");
  var table = document.getElementById("myTable");

  if (!table) return;

  var lastNameFilter = lastNameInput ? lastNameInput.value.toUpperCase().trim() : "";
  var clubFilter = clubInput ? clubInput.value.toUpperCase().trim() : "";
  var rows = table.getElementsByTagName("tr");

  for (var i = 0; i < rows.length; i++) {
    var cells = rows[i].getElementsByTagName("td");

    if (!cells.length) continue;

    var lastNameText = cells[1] ? (cells[1].textContent || cells[1].innerText).toUpperCase() : "";
    var clubText = cells[3] ? (cells[3].textContent || cells[3].innerText).toUpperCase() : "";

    var matchesLastName = !lastNameFilter || lastNameText.indexOf(lastNameFilter) > -1;
    var matchesClub = !clubFilter || clubText.indexOf(clubFilter) > -1;

    rows[i].style.display = matchesLastName && matchesClub ? "" : "none";
  }
}

function searchByLastName() {
  applyEntryFilters();
}

function searchByClub() {
  applyEntryFilters();
}

function syncEntryChoiceState() {
  var labels = document.querySelectorAll(".entry-choice");
  for (var i = 0; i < labels.length; i++) {
    var label = labels[i];
    var input = label.querySelector('input[type="checkbox"]');
    if (!input) continue;

    label.classList.toggle("selected", input.checked);
  }
}

function getSelectedLabelCount(name, form) {
  var labels = (form || document).querySelectorAll(".entry-choice.selected");
  var count = 0;

  for (var i = 0; i < labels.length; i++) {
    var input = labels[i].querySelector('input[name="' + name + '"]');
    if (input) count += 1;
  }

  return count;
}

function getEntrySelectionCounts(form) {
  var root = form || document;
  var count20 = root.querySelectorAll('input[name="checkbox_20"]:checked').length;
  var count24 = root.querySelectorAll('input[name="checkbox_24"]:checked').length;
  var countBeginner = root.querySelectorAll('input[name="checkbox_beginner"]:checked').length;

  if (count20 === 0) count20 = getSelectedLabelCount("checkbox_20", root);
  if (count24 === 0) count24 = getSelectedLabelCount("checkbox_24", root);
  if (countBeginner === 0) countBeginner = getSelectedLabelCount("checkbox_beginner", root);

  return {
    count20: count20,
    count24: count24,
    countBeginner: countBeginner,
    total: count20 + count24 + countBeginner,
  };
}

function updateEntrySelectionSummary() {
  var form = document.getElementById("entry-form");
  var submitButton = document.getElementById("entry-submit-btn");
  var selectionLabel = document.getElementById("entry-selection-label");
  var selectionBreakdown = document.getElementById("entry-selection-breakdown");

  if (!form || !submitButton || !selectionLabel || !selectionBreakdown) {
    return;
  }

  var counts = getEntrySelectionCounts(form);
  var selectedLabel = form.dataset.selectedLabel || "Vybráno";
  var registrationsLabel = form.dataset.registrationsLabel || "registrací";
  var beginnerLabel = form.dataset.beginnerLabel || "Příchozí";
  var beginnerInputs = form.querySelectorAll('input[name="checkbox_beginner"]').length > 0;
  var breakdown =
    '20" ' + counts.count20 + ' | 24" ' + counts.count24 +
    (beginnerInputs ? " | " + beginnerLabel + " " + counts.countBeginner : "");

  selectionLabel.textContent = selectedLabel + " " + counts.total + " " + registrationsLabel;
  selectionBreakdown.textContent = breakdown;

  submitButton.disabled = counts.total === 0;
  submitButton.classList.toggle("opacity-60", counts.total === 0);
  submitButton.classList.toggle("cursor-not-allowed", counts.total === 0);
}

document.addEventListener("DOMContentLoaded", function () {
  applyEntryFilters();
  syncEntryChoiceState();
  updateEntrySelectionSummary();

  var form = document.getElementById("entry-form");
  if (form) {
    var refreshSelectionSummary = function () {
      syncEntryChoiceState();
      updateEntrySelectionSummary();
    };

    form.addEventListener("change", function (event) {
      var target = event.target;
      if (!target || target.type !== "checkbox") return;
      refreshSelectionSummary();
    });

    form.addEventListener("click", function (event) {
      var target = event.target;
      if (!target) return;

      var clickedLabel = target.closest ? target.closest(".entry-choice") : null;
      if (!clickedLabel) return;

      window.setTimeout(refreshSelectionSummary, 0);
    });
  }
});

window.syncEntryChoiceState = syncEntryChoiceState;
window.updateEntrySelectionSummary = updateEntrySelectionSummary;
