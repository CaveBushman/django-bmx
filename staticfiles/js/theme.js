function readThemePreference() {
  try {
    return window.localStorage.getItem("theme");
  } catch (error) {
    return null;
  }
}

function writeThemePreference(value) {
  try {
    window.localStorage.setItem("theme", value);
  } catch (error) {
    console.warn("Theme preference could not be saved.", error);
  }
}

function prefersDarkTheme() {
  try {
    return window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
  } catch (error) {
    return false;
  }
}

function applyTheme(theme) {
  const html = document.documentElement;
  const useDark = theme === "dark" || (theme !== "light" && prefersDarkTheme());
  html.classList.toggle("dark", useDark);
  updateThemeIcons();
  return useDark;
}

function updateThemeIcons() {
  const isDark = document.documentElement.classList.contains("dark");
  const sunIcon = document.getElementById("icon-sun");
  const moonIcon = document.getElementById("icon-moon");

  if (sunIcon) {
    sunIcon.classList.toggle("hidden", !isDark);
  }

  if (moonIcon) {
    moonIcon.classList.toggle("hidden", isDark);
  }
}

function toggleTheme() {
  const nextTheme = document.documentElement.classList.contains("dark") ? "light" : "dark";
  applyTheme(nextTheme);
  writeThemePreference(nextTheme);
}

document.addEventListener("DOMContentLoaded", () => {
  applyTheme(readThemePreference());

  try {
    const mediaQuery = window.matchMedia("(prefers-color-scheme: dark)");
    if (mediaQuery && typeof mediaQuery.addEventListener === "function") {
      mediaQuery.addEventListener("change", () => {
        if (!readThemePreference()) {
          applyTheme(null);
        }
      });
    } else if (mediaQuery && typeof mediaQuery.addListener === "function") {
      mediaQuery.addListener(() => {
        if (!readThemePreference()) {
          applyTheme(null);
        }
      });
    }
  } catch (error) {
    // Safari fallback: ignore listener setup when matchMedia is limited.
  }
});

window.toggleTheme = toggleTheme;
