(function () {
  function getStoredTheme() {
    try {
      return window.localStorage.getItem("theme");
    } catch (error) {
      return null;
    }
  }

  var storedTheme = getStoredTheme();
  var prefersDark = false;

  try {
    prefersDark = Boolean(
      window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches
    );
  } catch (error) {
    prefersDark = false;
  }

  document.documentElement.classList.toggle(
    "dark",
    storedTheme === "dark" || (!storedTheme && prefersDark)
  );
})();
