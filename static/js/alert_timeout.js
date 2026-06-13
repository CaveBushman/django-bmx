// Po 5 s plynule skryje flash zprávu (#message) — vanilla JS, bez jQuery.
(function () {
  var FADE_MS = 600;
  document.addEventListener("DOMContentLoaded", function () {
    var el = document.getElementById("message");
    if (!el) return;
    setTimeout(function () {
      el.style.transition = "opacity " + FADE_MS + "ms ease";
      el.style.opacity = "0";
      setTimeout(function () {
        el.style.display = "none";
      }, FADE_MS);
    }, 5000);
  });
})();
