
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

document.addEventListener("DOMContentLoaded", function () {
  applyEntryFilters();
  syncEntryChoiceState();

  document.querySelectorAll('.entry-choice input[type="checkbox"]').forEach(function (input) {
    input.addEventListener("change", syncEntryChoiceState);
  });
});
