
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

  labels.forEach(function (label) {
    var input = label.querySelector('input[type="checkbox"]');
    if (!input) return;

    label.classList.toggle("selected", input.checked);
  });
}

function getEntrySelectionCounts() {
  var count20 = document.querySelectorAll('input[name="checkbox_20"]:checked').length;
  var count24 = document.querySelectorAll('input[name="checkbox_24"]:checked').length;
  var countBeginner = document.querySelectorAll('input[name="checkbox_beginner"]:checked').length;
  return {
    count20: count20,
    count24: count24,
    countBeginner: countBeginner,
    total: count20 + count24 + countBeginner,
  };
}

function updateEntrySelectionSummary() {
  var submitButton = document.getElementById("entry-submit-btn");
  var selectionLabel = document.getElementById("entry-selection-label");
  var selectionBreakdown = document.getElementById("entry-selection-breakdown");
  var stickyCart = document.getElementById("entry-sticky-cart");
  var stickyValue = document.getElementById("entry-sticky-cart-value");
  var stickySubmit = document.getElementById("entry-sticky-submit");

  if (!submitButton || !selectionLabel || !selectionBreakdown) {
    return;
  }

  var counts = getEntrySelectionCounts();
  var beginnerInputs = document.querySelectorAll('input[name="checkbox_beginner"]').length > 0;
  var breakdown =
    '20" ' + counts.count20 + ' | 24" ' + counts.count24 +
    (beginnerInputs ? " | Příchozí " + counts.countBeginner : "");

  selectionLabel.textContent = "Vybráno " + counts.total + " registrací";
  selectionBreakdown.textContent = breakdown;

  submitButton.disabled = counts.total === 0;
  submitButton.classList.toggle("opacity-60", counts.total === 0);
  submitButton.classList.toggle("cursor-not-allowed", counts.total === 0);

  if (stickyCart && stickyValue && stickySubmit) {
    stickyValue.textContent = counts.total + " položek";
    stickySubmit.disabled = counts.total === 0;
    stickySubmit.classList.toggle("opacity-60", counts.total === 0);
    stickySubmit.classList.toggle("cursor-not-allowed", counts.total === 0);
    stickyCart.classList.toggle("is-visible", counts.total > 0);
    stickyCart.setAttribute("aria-hidden", counts.total > 0 ? "false" : "true");
  }
}

function confirmEntrySubmit(event) {
  var form = event.currentTarget;
  var submitter = event.submitter;
  if (!submitter || submitter.name !== "btn_add") {
    return;
  }

  var counts = getEntrySelectionCounts();
  if (!counts.total) {
    event.preventDefault();
    return;
  }

  var beginnerInputs = document.querySelectorAll('input[name="checkbox_beginner"]').length > 0;
  var message =
    "Opravdu přidat do košíku " + counts.total + " registrací?\n\n" +
    '20": ' + counts.count20 + "\n" +
    '24": ' + counts.count24 +
    (beginnerInputs ? "\nPříchozí: " + counts.countBeginner : "");

  if (!window.confirm(message)) {
    event.preventDefault();
  }
}

document.addEventListener("DOMContentLoaded", function () {
  applyEntryFilters();
  syncEntryChoiceState();
  updateEntrySelectionSummary();

  document.querySelectorAll('.entry-choice input[type="checkbox"]').forEach(function (input) {
    input.addEventListener("change", function () {
      syncEntryChoiceState();
      updateEntrySelectionSummary();
    });
  });

  var form = document.getElementById("entry-form");
  if (form) {
    form.addEventListener("submit", confirmEntrySubmit);
  }
});
