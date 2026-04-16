function initNavbar(documentRef, windowRef) {
  var navbar = documentRef.getElementById("navbar");
  if (!navbar) {
    return;
  }

  var profileButton = documentRef.getElementById("user-menu-button");
  var profileDropdown = documentRef.getElementById("profile-dropdown");
  var mobileMenuButton = documentRef.getElementById("show-mobile-nav-btn");
  var mobileMenu = documentRef.getElementById("mobile-menu");
  var languageButton = documentRef.getElementById("language-menu-button");
  var languageMenu = documentRef.getElementById("language-menu");
  var themeButtons = documentRef.querySelectorAll("[data-theme-toggle]");

  function setExpanded(button, expanded) {
    if (button) {
      button.setAttribute("aria-expanded", expanded ? "true" : "false");
    }
  }

  function setMenuVisibility(menu, button, isVisible) {
    if (!menu) {
      return;
    }

    if (isVisible) {
      menu.classList.remove("hidden");
    } else {
      menu.classList.add("hidden");
    }
    setExpanded(button, isVisible);
  }

  function isMenuHidden(menu) {
    return !menu || menu.classList.contains("hidden");
  }

  function hideProfileDropdown() {
    setMenuVisibility(profileDropdown, profileButton, false);
  }

  function hideLanguageMenu() {
    setMenuVisibility(languageMenu, languageButton, false);
  }

  function hideMobileMenu() {
    setMenuVisibility(mobileMenu, mobileMenuButton, false);
    if (documentRef.body && documentRef.body.style) {
      documentRef.body.style.overflow = "";
    }
  }

  function showMobileMenu() {
    setMenuVisibility(mobileMenu, mobileMenuButton, true);
    if (documentRef.body && documentRef.body.style) {
      documentRef.body.style.overflow = "hidden";
    }
  }

  function toggleDropdown(menu, button, hideSibling) {
    if (!menu || !button) {
      return;
    }

    hideSibling();
    var shouldOpen = isMenuHidden(menu);
    setMenuVisibility(menu, button, false);
    if (shouldOpen) {
      setMenuVisibility(menu, button, true);
    }
  }

  function closeAllMenus() {
    hideProfileDropdown();
    hideLanguageMenu();
    hideMobileMenu();
  }

  themeButtons.forEach(function (button) {
    button.addEventListener("click", function () {
      if (windowRef && typeof windowRef.toggleTheme === "function") {
        windowRef.toggleTheme();
      }
    });
  });

  if (profileButton && profileDropdown) {
    profileButton.addEventListener("click", function (event) {
      event.preventDefault();
      event.stopPropagation();
      toggleDropdown(profileDropdown, profileButton, hideLanguageMenu);
    });
  }

  if (languageButton && languageMenu) {
    languageButton.addEventListener("click", function (event) {
      event.preventDefault();
      event.stopPropagation();
      toggleDropdown(languageMenu, languageButton, hideProfileDropdown);
    });
  }

  if (mobileMenuButton && mobileMenu) {
    mobileMenuButton.addEventListener("click", function () {
      if (isMenuHidden(mobileMenu)) {
        showMobileMenu();
      } else {
        hideMobileMenu();
      }
    });
  }

  navbar.querySelectorAll("a").forEach(function (link) {
    link.addEventListener("click", function () {
      hideMobileMenu();
    });
  });

  documentRef.addEventListener("click", function (event) {
    if (
      profileButton &&
      profileDropdown &&
      !isMenuHidden(profileDropdown) &&
      !profileDropdown.contains(event.target) &&
      !profileButton.contains(event.target)
    ) {
      hideProfileDropdown();
    }

    if (
      languageButton &&
      languageMenu &&
      !isMenuHidden(languageMenu) &&
      !languageMenu.contains(event.target) &&
      !languageButton.contains(event.target)
    ) {
      hideLanguageMenu();
    }
  });

  documentRef.addEventListener("keydown", function (event) {
    if (event.key === "Escape") {
      closeAllMenus();
    }
  });
}

if (typeof document !== "undefined") {
  document.addEventListener("DOMContentLoaded", function () {
    initNavbar(document, typeof window !== "undefined" ? window : null);
  });
}

if (typeof module !== "undefined") {
  module.exports = { initNavbar: initNavbar };
}
