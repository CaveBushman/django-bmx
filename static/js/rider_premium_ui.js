document.addEventListener("DOMContentLoaded", function () {
  var statsPage = document.querySelector(".premium-stats-page");

  document.querySelectorAll("[data-auto-submit]").forEach(function (field) {
    field.addEventListener("change", function () {
      if (field.form) {
        if (statsPage) {
          statsPage.style.transition = "opacity 0.15s";
          statsPage.style.opacity = "0.45";
          statsPage.style.pointerEvents = "none";
          statsPage.style.cursor = "wait";
        }
        field.form.submit();
      }
    });
  });

  var metricToggles = document.querySelectorAll(".metric-view-toggle");
  var metricPanels = document.querySelectorAll(".metric-panel");
  if (metricToggles.length && metricPanels.length) {
    var syncMetricPanels = function (selectedValue) {
      metricPanels.forEach(function (panel) {
        panel.classList.toggle("hidden", panel.dataset.metricPanel !== selectedValue);
      });
    };

    metricToggles.forEach(function (toggle) {
      toggle.addEventListener("change", function () {
        if (toggle.checked) {
          syncMetricPanels(toggle.value);
        }
      });
    });

    var activeMetric = Array.from(metricToggles).find(function (toggle) {
      return toggle.checked;
    });
    if (activeMetric) {
      syncMetricPanels(activeMetric.value);
    }
  }

  var modal = document.getElementById("help-modal");
  var title = document.getElementById("help-modal-title");
  var body = document.getElementById("help-modal-body");
  var closeButton = document.getElementById("help-modal-close");
  var actionButton = document.getElementById("help-modal-action");

  if (!modal || !title || !body || !closeButton || !actionButton) {
    return;
  }

  var closeModal = function () {
    modal.classList.add("hidden");
    document.body.classList.remove("overflow-hidden");
  };

  document.querySelectorAll(".help-trigger").forEach(function (button) {
    button.addEventListener("click", function () {
      title.textContent = button.dataset.helpTitle || "Nápověda";
      body.textContent = button.dataset.helpBody || "";
      modal.classList.remove("hidden");
      document.body.classList.add("overflow-hidden");
    });
  });

  closeButton.addEventListener("click", closeModal);
  actionButton.addEventListener("click", closeModal);
  modal.addEventListener("click", function (event) {
    if (event.target === modal || event.target === modal.firstElementChild) {
      closeModal();
    }
  });
  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape" && !modal.classList.contains("hidden")) {
      closeModal();
    }
  });
});
