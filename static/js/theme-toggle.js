/**
 * BMX Racing Theme Toggle Logic
 * Manages light/dark mode using localStorage and system preferences.
 */
const storageKey = "bmx-theme-preference";

const getThemePreference = () => {
  if (localStorage.getItem(storageKey)) return localStorage.getItem(storageKey);
  return window.matchMedia("(prefers-color-scheme: dark)").matches
    ? "dark"
    : "light";
};

const applyTheme = (theme) => {
  document.documentElement.setAttribute("data-theme", theme);
  localStorage.setItem(storageKey, theme);
};

// Inicializace při načtení
applyTheme(getThemePreference());

// Funkce volaná tlačítkem v navbaru
window.toggleTheme = () => {
  const current = document.documentElement.getAttribute("data-theme");
  const next = current === "dark" ? "light" : "dark";
  applyTheme(next);

  // Dispatch event pro ostatní komponenty (pokud je potřeba překreslit grafy apod.)
  window.dispatchEvent(
    new CustomEvent("themeChanged", { detail: { theme: next } }),
  );
};
