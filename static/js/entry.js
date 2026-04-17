
function applyEntryFilters() {
  var lastNameInput = document.getElementById("inputLastName");
  var clubInput = document.getElementById("inputClub");
  var mobileCards = document.querySelectorAll(".entry-mobile-card");
  var desktopRows = document.querySelectorAll(".entry-desktop-row");
  var emptyState = document.getElementById("entry-empty-state");

  var lastNameFilter = lastNameInput ? lastNameInput.value.toUpperCase().trim() : "";
  var clubFilter = clubInput ? clubInput.value.toUpperCase().trim() : "";
  var visibleCount = 0;

  for (var i = 0; i < desktopRows.length; i++) {
    var row = desktopRows[i];
    var lastNameText = (row.getAttribute("data-last-name") || "").toUpperCase();
    var clubText = (row.getAttribute("data-club") || "").toUpperCase();

    var matchesLastName = !lastNameFilter || lastNameText.indexOf(lastNameFilter) > -1;
    var matchesClub = !clubFilter || clubText.indexOf(clubFilter) > -1;

    row.style.display = matchesLastName && matchesClub ? "" : "none";
    if (matchesLastName && matchesClub) visibleCount += 1;
  }

  for (var j = 0; j < mobileCards.length; j++) {
    var card = mobileCards[j];
    var nameNode = card.querySelector("h3");
    var clubNode = card.querySelector("p");
    var riderName = nameNode ? (nameNode.textContent || nameNode.innerText).toUpperCase() : "";
    var riderClub = clubNode ? (clubNode.textContent || clubNode.innerText).toUpperCase() : "";

    var cardMatchesLastName = !lastNameFilter || riderName.indexOf(lastNameFilter) > -1;
    var cardMatchesClub = !clubFilter || riderClub.indexOf(clubFilter) > -1;

    card.style.display = cardMatchesLastName && cardMatchesClub ? "" : "none";
  }

  if (emptyState) {
    emptyState.classList.toggle("hidden", visibleCount > 0);
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
  var submitButtons = document.querySelectorAll("[data-entry-submit]");
  var selectionLabels = document.querySelectorAll("[data-entry-selection-label]");
  var selectionBreakdowns = document.querySelectorAll("[data-entry-selection-breakdown]");

  if (!form || !submitButtons.length || !selectionLabels.length || !selectionBreakdowns.length) {
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

  for (var i = 0; i < selectionLabels.length; i++) {
    selectionLabels[i].textContent = selectedLabel + " " + counts.total + " " + registrationsLabel;
  }

  for (var j = 0; j < selectionBreakdowns.length; j++) {
    selectionBreakdowns[j].textContent = breakdown;
  }

  for (var k = 0; k < submitButtons.length; k++) {
    submitButtons[k].disabled = counts.total === 0;
    submitButtons[k].classList.toggle("opacity-60", counts.total === 0);
    submitButtons[k].classList.toggle("cursor-not-allowed", counts.total === 0);
  }
}

function initializeEntryCategoryPopover() {
  var popover = document.getElementById("entry-category-popover");
  if (!popover) return;

  var title = document.getElementById("entry-category-popover-title");
  var count = document.getElementById("entry-category-popover-count");
  var list = document.getElementById("entry-category-popover-list");
  var activeTrigger = null;
  var hideTimer = null;

  function clearHideTimer() {
    if (hideTimer) {
      window.clearTimeout(hideTimer);
      hideTimer = null;
    }
  }

  function scheduleHide() {
    clearHideTimer();
    hideTimer = window.setTimeout(hidePopover, 120);
  }

  function renderParticipants(entries) {
    list.innerHTML = "";
    for (var i = 0; i < entries.length; i++) {
      var item = document.createElement("li");
      item.className = "flex items-center justify-between gap-3 rounded-xl bg-slate-50 px-3 py-2 dark:bg-slate-900";

      var plate = document.createElement("span");
      plate.className = "shrink-0 rounded-full bg-indigo-100 px-2 py-1 text-xs font-bold uppercase tracking-[0.12em] text-indigo-700 dark:bg-indigo-500/15 dark:text-indigo-300";
      plate.textContent = entries[i].plate || "-";

      var name = document.createElement("span");
      name.className = "min-w-0 flex-1 truncate font-medium text-slate-700 dark:text-slate-200";
      if (entries[i].name) {
        name.textContent = entries[i].name;
      } else {
        name.textContent = ((entries[i].first_name || "") + " " + (entries[i].last_name || "")).trim();
      }

      item.appendChild(plate);
      item.appendChild(name);
      list.appendChild(item);
    }
  }

  function positionPopover(trigger) {
    var rect = trigger.getBoundingClientRect();
    var popoverRect = popover.getBoundingClientRect();
    var top = rect.bottom + 10;
    var left = rect.left + rect.width / 2 - popoverRect.width / 2;

    if (left < 16) left = 16;
    if (left + popoverRect.width > window.innerWidth - 16) {
      left = window.innerWidth - popoverRect.width - 16;
    }
    if (top + popoverRect.height > window.innerHeight - 16) {
      top = rect.top - popoverRect.height - 10;
    }
    if (top < 16) top = 16;

    popover.style.top = top + "px";
    popover.style.left = left + "px";
  }

  function showPopover(trigger) {
    clearHideTimer();
    activeTrigger = trigger;

    var categoryName = trigger.getAttribute("data-category-name") || "";
    var categoryCount = parseInt(trigger.getAttribute("data-category-count") || "0", 10);
    var entries = [];

    var template = trigger.nextElementSibling;
    if (template && template.classList.contains("entry-category-template")) {
      var items = template.querySelectorAll(".entry-category-template-item");
      for (var i = 0; i < items.length; i++) {
        entries.push({
          plate: items[i].getAttribute("data-plate") || "-",
          name: items[i].getAttribute("data-name") || "",
        });
      }
    }

    title.textContent = categoryName;
    count.textContent = categoryCount + " přihlášených";
    renderParticipants(entries);
    popover.hidden = false;
    positionPopover(trigger);
  }

  function hidePopover() {
    clearHideTimer();
    popover.hidden = true;
    activeTrigger = null;
  }

  var triggers = document.querySelectorAll(".entry-category-trigger");
  for (var i = 0; i < triggers.length; i++) {
    triggers[i].addEventListener("mouseenter", function () {
      showPopover(this);
    });
    triggers[i].addEventListener("focus", function () {
      showPopover(this);
    });
    triggers[i].addEventListener("mouseleave", scheduleHide);
    triggers[i].addEventListener("blur", scheduleHide);
    triggers[i].addEventListener("click", function (event) {
      event.preventDefault();
      event.stopPropagation();
      if (activeTrigger === this && !popover.hidden) {
        hidePopover();
        return;
      }
      showPopover(this);
    });
  }

  popover.addEventListener("mouseenter", clearHideTimer);
  popover.addEventListener("mouseleave", scheduleHide);

  document.addEventListener("click", function (event) {
    if (popover.hidden) return;
    if (popover.contains(event.target)) return;
    if (event.target.closest && event.target.closest(".entry-category-trigger")) return;
    hidePopover();
  });

  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape") {
      hidePopover();
    }
  });

  window.addEventListener("resize", function () {
    if (!popover.hidden && activeTrigger) {
      positionPopover(activeTrigger);
    }
  });
}

document.addEventListener("DOMContentLoaded", function () {
  applyEntryFilters();
  syncEntryChoiceState();
  updateEntrySelectionSummary();
  initializeEntryCategoryPopover();

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
