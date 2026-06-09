function readThemePreference(windowRef) {
  try {
    return windowRef.localStorage.getItem("theme");
  } catch (error) {
    return null;
  }
}

function writeThemePreference(windowRef, value) {
  try {
    windowRef.localStorage.setItem("theme", value);
  } catch (error) {
    console.warn("Theme preference could not be saved.", error);
  }
}

function prefersDarkTheme(windowRef) {
  try {
    return (
      windowRef.matchMedia &&
      windowRef.matchMedia("(prefers-color-scheme: dark)").matches
    );
  } catch (error) {
    return false;
  }
}

function updateThemeIcons(documentRef) {
  var isDark = documentRef.documentElement.classList.contains("dark");
  var sunIcon = documentRef.getElementById("icon-sun");
  var moonIcon = documentRef.getElementById("icon-moon");

  if (sunIcon) {
    sunIcon.classList.toggle("hidden", !isDark);
  }

  if (moonIcon) {
    moonIcon.classList.toggle("hidden", isDark);
  }
}

function applyTheme(documentRef, windowRef, theme) {
  var useDark = theme === "dark" || (theme !== "light" && prefersDarkTheme(windowRef));
  documentRef.documentElement.classList.toggle("dark", useDark);
  updateThemeIcons(documentRef);
  return useDark;
}

function createThemeController(documentRef, windowRef) {
  return {
    applyTheme: function (theme) {
      return applyTheme(documentRef, windowRef, theme);
    },
    toggleTheme: function () {
      var nextTheme = documentRef.documentElement.classList.contains("dark") ? "light" : "dark";
      applyTheme(documentRef, windowRef, nextTheme);
      writeThemePreference(windowRef, nextTheme);
    },
    getStoredTheme: function () {
      return readThemePreference(windowRef);
    },
  };
}

function bindSystemThemeListener(windowRef, onChange) {
  try {
    var mediaQuery = windowRef.matchMedia("(prefers-color-scheme: dark)");
    if (mediaQuery && typeof mediaQuery.addEventListener === "function") {
      mediaQuery.addEventListener("change", onChange);
    } else if (mediaQuery && typeof mediaQuery.addListener === "function") {
      mediaQuery.addListener(onChange);
    }
  } catch (error) {
    // Safari fallback: ignore listener setup when matchMedia is limited.
  }
}

function initTheme(documentRef, windowRef) {
  var controller = createThemeController(documentRef, windowRef);
  controller.applyTheme(controller.getStoredTheme());

  bindSystemThemeListener(windowRef, function () {
    if (!controller.getStoredTheme()) {
      controller.applyTheme(null);
    }
  });

  return controller;
}

if (typeof document !== "undefined" && typeof window !== "undefined") {
  document.addEventListener("DOMContentLoaded", function () {
    var controller = initTheme(document, window);
    window.toggleTheme = controller.toggleTheme;
  });
}

if (typeof module !== "undefined") {
  module.exports = {
    applyTheme: applyTheme,
    bindSystemThemeListener: bindSystemThemeListener,
    createThemeController: createThemeController,
    initTheme: initTheme,
    prefersDarkTheme: prefersDarkTheme,
    readThemePreference: readThemePreference,
    updateThemeIcons: updateThemeIcons,
    writeThemePreference: writeThemePreference,
  };
}
