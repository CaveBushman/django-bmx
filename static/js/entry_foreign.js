document.addEventListener("DOMContentLoaded", function () {
  var form = document.getElementById("ridersForm");
  if (!form) {
    return;
  }

  var riderTable = document.getElementById("ridersTable");
  var summaryPayload = document.getElementById("summaryPayload");
  var riderCount = document.getElementById("riderCount");
  var customerEmail = document.getElementById("customerEmail");
  var transponderPattern = /^[A-Z]{2}-\d{5}$/;

  function getCards() {
    return Array.from(document.querySelectorAll(".riderCard"));
  }

  function updateCardTitles() {
    getCards().forEach(function (card, index) {
      var title = card.querySelector(".riderCardTitle");
      if (title) {
        title.textContent = "Rider " + (index + 1);
      }
    });
  }

  function updateRiderCount() {
    if (!riderCount) {
      return;
    }

    var count = getCards().length;
    riderCount.textContent = count + " " + (count === 1 ? "rider" : "riders") + " in form";
    updateCardTitles();
  }

  function syncCategoryRules(target) {
    var card = target && target.classList && target.classList.contains("riderCard")
      ? target
      : target && target.closest(".riderCard");
    if (!card) {
      return;
    }

    var challenge = card.querySelector('[name="challenge[]"]');
    var championship = card.querySelector('[name="championship[]"]');
    var cruiser = card.querySelector('[name="cruiser[]"]');

    if (championship && championship.checked) {
      challenge.checked = false;
      cruiser.checked = false;
    }

    if ((challenge && challenge.checked) || (cruiser && cruiser.checked)) {
      championship.checked = false;
    }
  }

  function enableManualEntry(card, resetFields) {
    [
      '[name="first_name[]"]',
      '[name="last_name[]"]',
      '[name="dob[]"]',
      '[name="plate[]"]',
      '[name="nationality[]"]',
    ].forEach(function (selector) {
      var field = card.querySelector(selector);
      if (!field) {
        return;
      }
      field.readOnly = false;
      if (resetFields && selector !== '[name="nationality[]"]') {
        field.value = "";
      }
    });

    var sexField = card.querySelector('[name="sex[]"]');
    if (sexField) {
      sexField.disabled = false;
      if (resetFields) {
        sexField.value = "Muž";
      }
    }

    if (resetFields) {
      var nationalityField = card.querySelector('[name="nationality[]"]');
      if (nationalityField) {
        nationalityField.value = "";
      }
    }
  }

  function addRow() {
    var cards = getCards();
    var lastCard = cards[cards.length - 1];
    if (!lastCard) {
      return;
    }

    var newCard = lastCard.cloneNode(true);
    newCard.querySelectorAll("input").forEach(function (input) {
      if (input.type === "checkbox") {
        input.checked = false;
      } else {
        input.value = "";
      }
      input.readOnly = false;
    });

    newCard.querySelectorAll("select").forEach(function (select) {
      select.value = "Muž";
      select.disabled = false;
    });

    var clonedNotice = newCard.querySelector('.czech-rider-notice');
    if (clonedNotice) {
      clonedNotice.classList.add('hidden');
    }

    riderTable.appendChild(newCard);
    syncCategoryRules(newCard);
    updateRiderCount();
  }

  function removeRow(button) {
    var cards = getCards();
    var card = button.closest(".riderCard");
    if (!card) {
      return;
    }

    if (cards.length > 1) {
      card.remove();
      updateRiderCount();
      return;
    }

    window.alert("It must remain at least one line.");
  }

  function fetchRiderData(input) {
    var uciId = input.value.trim();
    if (!uciId) {
      return;
    }

    fetch(form.dataset.checkRiderUrl + "?uci_id=" + encodeURIComponent(uciId), {
      method: "GET",
      headers: {
        "X-CSRFToken": document.body.dataset.csrfToken || "",
      },
    })
      .then(function (response) {
        if (!response.ok) {
          return Promise.reject("Server returned an error: " + response.status);
        }
        return response.json();
      })
      .then(function (data) {
        var card = input.closest(".riderCard");
        if (!card) {
          return;
        }

        var notice = card.querySelector('.czech-rider-notice');
        if (!data.error) {
          card.querySelector('[name="first_name[]"]').value = data.first_name;
          card.querySelector('[name="last_name[]"]').value = data.last_name;
          card.querySelector('[name="dob[]"]').value = data.date_of_birth;
          card.querySelector('[name="sex[]"]').value = data.sex;
          card.querySelector('[name="plate[]"]').value = data.plate;
          card.querySelector('[name="transponder_20[]"]').value = data.transponder_20;
          card.querySelector('[name="transponder_24[]"]').value = data.transponder_24;
          card.querySelector('[name="nationality[]"]').value = data.nationality;
          enableManualEntry(card, false);
          if (notice) {
            if (data.is_czech_rider) {
              notice.classList.remove('hidden');
            } else {
              notice.classList.add('hidden');
            }
          }
        } else {
          enableManualEntry(card, true);
          if (notice) {
            notice.classList.add('hidden');
          }
        }

        syncCategoryRules(card);
      })
      .catch(function (error) {
        var card = input.closest(".riderCard");
        if (card) {
          enableManualEntry(card, false);
        }
        window.alert("Error: " + error);
      });
  }

  function validateForm() {
    var errors = [];
    var rows = getCards()
      .map(function (card) {
        return {
          uci_id: card.querySelector('[name="uci_id[]"]').value,
          first_name: card.querySelector('[name="first_name[]"]').value,
          last_name: card.querySelector('[name="last_name[]"]').value,
          date_of_birth: card.querySelector('[name="dob[]"]').value,
          sex: card.querySelector('[name="sex[]"]').value,
          plate: card.querySelector('[name="plate[]"]').value,
          nationality: card.querySelector('[name="nationality[]"]').value,
          transponder_20: card.querySelector('[name="transponder_20[]"]').value,
          transponder_24: card.querySelector('[name="transponder_24[]"]').value,
          challenge: card.querySelector('[name="challenge[]"]').checked,
          championship: card.querySelector('[name="championship[]"]').checked,
          cruiser: card.querySelector('[name="cruiser[]"]').checked,
        };
      })
      .filter(function (row) {
        return (
          row.uci_id ||
          row.first_name ||
          row.last_name ||
          row.date_of_birth ||
          row.plate ||
          row.nationality ||
          row.transponder_20 ||
          row.transponder_24 ||
          row.challenge ||
          row.championship ||
          row.cruiser
        );
      });

    if (!customerEmail.value.trim()) {
      errors.push("Contact e-mail is required.");
    }

    if (!rows.length) {
      errors.push("Add at least one rider.");
    }

    rows.forEach(function (row, index) {
      var label = "Rider " + (index + 1);
      if (!row.first_name.trim()) {
        errors.push(label + ": first name is required.");
      }
      if (!row.last_name.trim()) {
        errors.push(label + ": last name is required.");
      }
      if (!row.uci_id.trim()) {
        errors.push(label + ": UCI ID is required.");
      }
      if (!row.date_of_birth.trim()) {
        errors.push(label + ": date of birth is required.");
      }
      if (!String(row.plate).trim()) {
        errors.push(label + ": plate is required.");
      }
      if (!row.challenge && !row.championship && !row.cruiser) {
        errors.push(label + ": choose Challenge, Championship or Cruiser.");
      }
      if (row.championship && (row.challenge || row.cruiser)) {
        errors.push(label + ": Championship must be selected alone.");
      }
      if (row.transponder_20 && !transponderPattern.test(row.transponder_20.trim().toUpperCase())) {
        errors.push(label + ": transponder 20 must be in format XX-11111.");
      }
      if (row.transponder_24 && !transponderPattern.test(row.transponder_24.trim().toUpperCase())) {
        errors.push(label + ": transponder 24 must be in format XX-11111.");
      }
    });

    if (errors.length) {
      window.alert(errors.join("\n"));
      return false;
    }

    summaryPayload.value = JSON.stringify({
      customer_email: customerEmail.value.trim(),
      rows: rows,
    });
    return true;
  }

  document.addEventListener("input", function (event) {
    if (event.target.matches("[data-uppercase]")) {
      event.target.value = event.target.value.toUpperCase();
    }
  });

  document.addEventListener("change", function (event) {
    if (event.target.matches("[data-category-toggle]")) {
      syncCategoryRules(event.target);
    }
  });

  document.addEventListener("blur", function (event) {
    if (event.target.matches("[data-fetch-rider]")) {
      fetchRiderData(event.target);
    }
  }, true);

  document.addEventListener("click", function (event) {
    var removeButton = event.target.closest("[data-remove-rider]");
    if (removeButton) {
      removeRow(removeButton);
      return;
    }

    if (event.target.closest("[data-add-rider]")) {
      addRow();
    }
  });

  form.addEventListener("submit", function (event) {
    if (!validateForm()) {
      event.preventDefault();
    }
  });

  getCards().forEach(syncCategoryRules);
  updateRiderCount();
});
