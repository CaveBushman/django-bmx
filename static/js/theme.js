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
  const html = document.documentElement;
  const isDark = html.classList.toggle("dark");

  try {
    localStorage.setItem("theme", isDark ? "dark" : "light");
  } catch (error) {
    console.warn("Theme preference could not be saved.", error);
  }

  updateThemeIcons();
}

document.addEventListener("DOMContentLoaded", () => {
  updateThemeIcons();
});

window.toggleTheme = toggleTheme;
