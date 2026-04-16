document.addEventListener("DOMContentLoaded", function () {
  var form = document.getElementById("rider-request-form");
  if (!form) {
    return;
  }

  var lookupInput = document.getElementById("uci_id_lookup");
  var lookupButton = document.getElementById("lookup_button");
  var lookupConfirmed = document.getElementById("lookup_confirmed");
  var requestDetails = document.getElementById("request_details");
  var licenceDetails = document.getElementById("licence_details");

  function showError(message) {
    var container = document.getElementById("js-error-container");
    var text = document.getElementById("js-error-text");
    if (container && text) {
      text.textContent = message;
      container.classList.remove("hidden");
      container.scrollIntoView({ behavior: "smooth", block: "center" });
      return;
    }
    window.alert(message);
  }

  function hideError() {
    var container = document.getElementById("js-error-container");
    if (container) {
      container.classList.add("hidden");
    }
  }

  function setLookupStatus(message, state) {
    var status = document.getElementById("lookup_status");
    if (!status) {
      return;
    }

    status.classList.remove("hidden", "is-success", "is-error");
    var icon = "";

    if (state === "success") {
      status.classList.add("is-success");
      icon = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" class="w-5 h-5 shrink-0"><path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.857-9.809a.75.75 0 00-1.214-.882l-3.483 4.79-1.88-1.88a.75.75 0 10-1.06 1.061l2.5 2.5a.75.75 0 001.137-.089l4-5.5z" clip-rule="evenodd" /></svg>';
    } else if (state === "error") {
      status.classList.add("is-error");
      icon = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" class="w-5 h-5 shrink-0"><path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.28 7.22a.75.75 0 00-1.06 1.06L8.94 10l-1.72 1.72a.75.75 0 101.06 1.06L10 11.06l1.72 1.72a.75.75 0 101.06-1.06L11.06 10l1.72-1.72a.75.75 0 00-1.06-1.06L10 8.94 8.28 7.22z" clip-rule="evenodd" /></svg>';
    }

    status.innerHTML = icon + "<span>" + message + "</span>";
  }

  function setDetailsLocked(locked) {
    [requestDetails, licenceDetails].forEach(function (element) {
      if (!element) {
        return;
      }

      if (locked) {
        element.classList.add(
          "rider-request-hidden",
          "rider-request-step-locked",
          "opacity-0",
          "translate-y-4"
        );
      } else {
        element.classList.remove("rider-request-hidden");
        window.setTimeout(function () {
          element.classList.remove(
            "rider-request-step-locked",
            "opacity-0",
            "translate-y-4"
          );
        }, 50);
      }
    });

    if (requestDetails) {
      requestDetails
        .querySelectorAll('input, select, button[type="submit"]')
        .forEach(function (element) {
          element.disabled = locked;
        });
    }
  }

  function fillRiderData(rider) {
    document.getElementById("uci_id").value = rider.uci_id || "";
    document.getElementById("first_name").value = rider.first_name || "";
    document.getElementById("last_name").value = rider.last_name || "";
    document.getElementById("date_of_birth").value = rider.date_of_birth || "";
    document.getElementById("gender").value = rider.gender || "";

    document.getElementById("first_name_preview").value = rider.first_name || "";
    document.getElementById("last_name_preview").value = rider.last_name || "";
    document.getElementById("date_of_birth_preview").value = rider.date_of_birth || "";
    document.getElementById("gender_preview").value = rider.gender || "";
    lookupInput.value = rider.uci_id || "";
  }

  async function lookupLicence() {
    var uciId = lookupInput.value.trim();
    if (!/^\d{11}$/.test(uciId)) {
      showError(form.dataset.msgUciInvalid);
      lookupConfirmed.value = "";
      setDetailsLocked(true);
      lookupInput.focus();
      return;
    }

    hideError();
    lookupButton.disabled = true;
    lookupButton.innerHTML =
      '<svg class="animate-spin -ml-1 mr-2 h-4 w-4 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg>' +
      form.dataset.msgLoading;

    try {
      var response = await fetch(
        form.dataset.lookupUrl + "?uci_id=" + encodeURIComponent(uciId),
        { headers: { "X-Requested-With": "XMLHttpRequest" } }
      );

      var data = null;
      try {
        data = await response.json();
      } catch (_error) {
        data = null;
      }

      if (!response.ok || !data || !data.ok) {
        throw new Error((data && data.message) || form.dataset.msgLookupNotFound);
      }

      fillRiderData(data.rider);
      lookupConfirmed.value = "1";
      setDetailsLocked(false);
      setLookupStatus(form.dataset.msgLookupSuccess, "success");
    } catch (error) {
      lookupConfirmed.value = "";
      setDetailsLocked(true);
      showError(error.message || form.dataset.msgLookupNotFound);
      var status = document.getElementById("lookup_status");
      if (status) {
        status.classList.add("hidden");
      }
    } finally {
      lookupButton.disabled = false;
      lookupButton.textContent = lookupButton.dataset.defaultLabel || "Načíst licenci";
    }
  }

  function validateForm() {
    hideError();
    if (lookupConfirmed.value !== "1") {
      showError(form.dataset.msgLookupRequired);
      lookupInput.focus();
      return false;
    }

    var phone = document.getElementById("emergency-phone");
    if (!/^[\d\+\-\s]{6,20}$/.test(phone.value)) {
      showError(form.dataset.msgPhoneInvalid);
      phone.focus();
      return false;
    }
    return true;
  }

  lookupButton.dataset.defaultLabel = lookupButton.textContent;
  lookupButton.addEventListener("click", lookupLicence);
  lookupInput.addEventListener("input", function (event) {
    event.target.value = event.target.value.replace(/\D/g, "").slice(0, 11);
    lookupConfirmed.value = "";
    if (requestDetails && !requestDetails.classList.contains("rider-request-hidden")) {
      setDetailsLocked(true);
      var status = document.getElementById("lookup_status");
      if (status) {
        status.classList.add("hidden");
      }
    }
  });
  lookupInput.addEventListener("keypress", function (event) {
    if (event.key === "Enter") {
      event.preventDefault();
      lookupLicence();
    }
  });

  form.addEventListener("submit", function (event) {
    if (!validateForm()) {
      event.preventDefault();
    }
  });

  setDetailsLocked(lookupConfirmed.value !== "1");
  if (lookupConfirmed.value === "1") {
    setLookupStatus(form.dataset.msgLookupConfirmed, "success");
  }
});
