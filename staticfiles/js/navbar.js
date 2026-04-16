document.addEventListener("DOMContentLoaded", function () {
  // This file initializes navbar interactivity after the page has loaded.
  console.debug("navbar.js loaded");

  // --- INITIALIZATION ---
  var navbar = document.getElementById("navbar");
  if (!navbar) {
    console.debug("navbar.js: No navbar element found");
    return; // Nothing to do on pages without the navbar.
  }

  // Main navbar elements used by JavaScript.
  var profileButton = document.getElementById("user-menu-button");
  var profileDropdown = document.getElementById("profile-dropdown");
  var mobileMenuButton = document.getElementById("show-mobile-nav-btn");
  var mobileMenu = document.getElementById("mobile-menu");
  var languageButton = document.getElementById("language-menu-button");
  var languageMenu = document.getElementById("language-menu");
  var themeButtons = document.querySelectorAll("[data-theme-toggle]");

  // --- HELPER FUNCTIONS ---
  
  // Helper to keep ARIA state in sync for toggle buttons.
  function setExpanded(button, expanded) {
    try {
      if (button) {
        button.setAttribute("aria-expanded", expanded ? "true" : "false");
      }
    } catch (error) {
      console.warn("Error setting aria-expanded:", error);
    }
  }

  // Hide the profile dropdown and update the associated button state.
  function hideProfileDropdown() {
    try {
      if (profileDropdown) {
        profileDropdown.classList.add("hidden");
        setExpanded(profileButton, false);
      }
    } catch (error) {
      console.warn("Error hiding profile dropdown:", error);
    }
  }

  // Hide the language selection menu and update the associated button state.
  function hideLanguageMenu() {
    try {
      if (languageMenu) {
        languageMenu.classList.add("hidden");
        setExpanded(languageButton, false);
      }
    } catch (error) {
      console.warn("Error hiding language menu:", error);
    }
  }

  // Hide the mobile navigation menu and restore page scrolling.
  function hideMobileMenu() {
    try {
      if (mobileMenu) {
        mobileMenu.classList.add("hidden");
        setExpanded(mobileMenuButton, false);
        document.body.style.overflow = "";
      }
    } catch (error) {
      console.warn("Error hiding mobile menu:", error);
    }
  }

  // Show the mobile navigation menu and prevent page scroll behind it.
  function showMobileMenu() {
    try {
      if (mobileMenu) {
        mobileMenu.classList.remove("hidden");
        setExpanded(mobileMenuButton, true);
        document.body.style.overflow = "hidden";
      }
    } catch (error) {
      console.warn("Error showing mobile menu:", error);
    }
  }

  // Close all open dropdowns and the mobile menu.
  function closeAllMenus() {
    hideProfileDropdown();
    hideLanguageMenu();
    hideMobileMenu();
  }

  // --- EVENT HANDLERS ---
  
  // Attach theme toggle behavior to all theme toggle buttons.
  try {
    themeButtons.forEach(function (button) {
      button.addEventListener("click", function () {
        try {
          if (typeof window.toggleTheme === "function") {
            window.toggleTheme();
          }
        } catch (error) {
          console.warn("Error toggling theme:", error);
        }
      });
    });
  } catch (error) {
    console.warn("Error attaching theme toggle handlers:", error);
  }

  // Profile menu button toggle.
  if (profileButton && profileDropdown) {
    try {
      profileButton.addEventListener("click", function (event) {
        try {
          event.preventDefault();
          event.stopPropagation();
          hideLanguageMenu();
          var shouldOpen = profileDropdown.classList.contains("hidden");
          hideProfileDropdown();
          if (shouldOpen) {
            profileDropdown.classList.remove("hidden");
            setExpanded(profileButton, true);
          }
        } catch (error) {
          console.warn("Error in profile button click handler:", error);
        }
      });
    } catch (error) {
      console.warn("Error attaching profile button handler:", error);
    }
  }

  // Language menu button toggle.
  if (languageButton && languageMenu) {
    try {
      console.debug("navbar.js: attaching language button handler", languageButton, languageMenu);
      languageButton.addEventListener("click", function (event) {
        try {
          event.preventDefault();
          event.stopPropagation();
          hideProfileDropdown();
          var shouldOpen = languageMenu.classList.contains("hidden");
          hideLanguageMenu();
          if (shouldOpen) {
            languageMenu.classList.remove("hidden");
            setExpanded(languageButton, true);
          }
        } catch (error) {
          console.warn("Error in language button click handler:", error);
        }
      });
    } catch (error) {
      console.warn("Error attaching language button handler:", error);
    }
  }

  // Mobile menu button toggle.
  if (mobileMenuButton && mobileMenu) {
    try {
      mobileMenuButton.addEventListener("click", function () {
        try {
          if (mobileMenu.classList.contains("hidden")) {
            showMobileMenu();
          } else {
            hideMobileMenu();
          }
        } catch (error) {
          console.warn("Error in mobile menu button click handler:", error);
        }
      });
    } catch (error) {
      console.warn("Error attaching mobile menu button handler:", error);
    }
  }

  // Close the mobile menu when any navbar link is clicked.
  try {
    navbar.querySelectorAll("a").forEach(function (link) {
      link.addEventListener("click", function () {
        try {
          hideMobileMenu();
        } catch (error) {
          console.warn("Error hiding mobile menu on link click:", error);
        }
      });
    });
  } catch (error) {
    console.warn("Error attaching link handlers:", error);
  }

  // Close opened dropdowns when clicking outside of them.
  try {
    document.addEventListener("click", function (event) {
      try {
        if (profileButton && profileDropdown && !profileDropdown.classList.contains("hidden")) {
          if (!profileDropdown.contains(event.target) && !profileButton.contains(event.target)) {
            hideProfileDropdown();
          }
    }

    if (languageButton && languageMenu && !languageMenu.classList.contains("hidden")) {
      if (!languageMenu.contains(event.target) && !languageButton.contains(event.target)) {
        hideLanguageMenu();
      }
        }
      });
    } catch (error) {
      console.warn("Error in document click handler:", error);
    }
  }

  // Close menus on Escape key.
  try {
    document.addEventListener("keydown", function (event) {
      try {
        if (event.key === "Escape") {
          closeAllMenus();
        }
      } catch (error) {
        console.warn("Error in escape key handler:", error);
      }
    });
  } catch (error) {
    console.warn("Error attaching escape key handler:", error);
  }
});
