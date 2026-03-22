function searchByName() {
    // Declare variables
    var input, filter, table, tr, td, i, txtValue;
    input = document.getElementById("inputName");
    filter = input.value.toUpperCase();
    table = document.getElementById("myTable");
    tr = table.getElementsByTagName("tr");
  
    // Loop through all table rows, and hide those who don't match the search query
    for (i = 0; i < tr.length; i++) {
      td = tr[i].getElementsByTagName("td")[0];
      if (td) {
        txtValue = td.textContent || td.innerText;
        if (txtValue.toUpperCase().indexOf(filter) > -1) {
          tr[i].style.display = "";
        } else {
          tr[i].style.display = "none";
        }
      }
    }
  }

  function searchByClub() {
    // Declare variables
    var input, filter, table, tr, td, i, txtValue;
    input = document.getElementById("inputClub");
    filter = input.value.toUpperCase();
    table = document.getElementById("myTable");
    tr = table.getElementsByTagName("tr");
  
    // Loop through all table rows, and hide those who don't match the search query
    for (i = 0; i < tr.length; i++) {
      td = tr[i].getElementsByTagName("td")[1];
      if (td) {
        txtValue = td.textContent || td.innerText;
        if (txtValue.toUpperCase().indexOf(filter) > -1) {
          tr[i].style.display = "";
        } else {
          tr[i].style.display = "none";
        }
      }
    }
  }
  
  function searchByClass() {
    // Declare variables
    var input, filter, table, tr, td, i, txtValue;
    input = document.getElementById("inputClass");
    filter = input.value.toUpperCase();
    table = document.getElementById("myTable");
    tr = table.getElementsByTagName("tr");
  
    // Loop through all table rows, and hide those who don't match the search query
    for (i = 0; i < tr.length; i++) {
      td = tr[i].getElementsByTagName("td")[2];
      if (td) {
        txtValue = td.textContent || td.innerText;
        if (txtValue.toUpperCase().indexOf(filter) > -1) {
          tr[i].style.display = "";
        } else {
          tr[i].style.display = "none";
        }
      }
    }
  }

  function updateEntrySelectionSummary() {
    var submitButton = document.getElementById("entry-submit-btn");
    var selectionLabel = document.getElementById("entry-selection-label");
    var selectionBreakdown = document.getElementById("entry-selection-breakdown");

    if (!submitButton || !selectionLabel || !selectionBreakdown) {
      return;
    }

    var count20 = document.querySelectorAll('input[name="checkbox_20"]:checked').length;
    var count24 = document.querySelectorAll('input[name="checkbox_24"]:checked').length;
    var beginnerInputs = document.querySelectorAll('input[name="checkbox_beginner"]');
    var countBeginner = document.querySelectorAll('input[name="checkbox_beginner"]:checked').length;
    var totalCount = count20 + count24 + countBeginner;

    selectionLabel.textContent = "Vybráno " + totalCount + " registrací";
    selectionBreakdown.textContent =
      '20" ' + count20 + ' | 24" ' + count24 + (beginnerInputs.length ? " | Příchozí " + countBeginner : "");

    submitButton.disabled = totalCount === 0;
    submitButton.classList.toggle("opacity-60", totalCount === 0);
    submitButton.classList.toggle("cursor-not-allowed", totalCount === 0);
  }

  document.addEventListener("change", function (event) {
    if (event.target && event.target.matches('input[name="checkbox_20"], input[name="checkbox_24"], input[name="checkbox_beginner"]')) {
      updateEntrySelectionSummary();
    }
  });

  document.addEventListener("DOMContentLoaded", updateEntrySelectionSummary);
  
