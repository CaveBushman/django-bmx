const assert = require("node:assert/strict");
const { initNavbar } = require("../../static/js/navbar.js");

class FakeClassList {
  constructor(initial = []) {
    this.values = new Set(initial);
  }

  add(value) {
    this.values.add(value);
  }

  remove(value) {
    this.values.delete(value);
  }

  contains(value) {
    return this.values.has(value);
  }
}

class FakeElement {
  constructor(tagName) {
    this.tagName = tagName.toUpperCase();
    this.children = [];
    this.parentNode = null;
    this.dataset = {};
    this.attributes = {};
    this.eventListeners = {};
    this.classList = new FakeClassList();
    this.style = {};
  }

  appendChild(child) {
    child.parentNode = this;
    this.children.push(child);
    return child;
  }

  setAttribute(name, value) {
    this.attributes[name] = value;
  }

  getAttribute(name) {
    return this.attributes[name];
  }

  addEventListener(type, handler) {
    if (!this.eventListeners[type]) {
      this.eventListeners[type] = [];
    }
    this.eventListeners[type].push(handler);
  }

  dispatchEvent(type, event = {}) {
    (this.eventListeners[type] || []).forEach((handler) => handler(event));
  }

  contains(target) {
    if (this === target) {
      return true;
    }
    return this.children.some((child) => child.contains(target));
  }

  querySelectorAll(selector) {
    const matches = [];
    const walk = (node) => {
      node.children.forEach((child) => {
        if (selector === "a" && child.tagName === "A") {
          matches.push(child);
        }
        if (selector === "[data-theme-toggle]" && Object.prototype.hasOwnProperty.call(child.dataset, "themeToggle")) {
          matches.push(child);
        }
        walk(child);
      });
    };
    walk(this);
    return matches;
  }
}

class FakeDocument extends FakeElement {
  constructor() {
    super("document");
    this.nodesById = {};
    this.body = new FakeElement("body");
  }

  getElementById(id) {
    return this.nodesById[id] || null;
  }

  register(id, element) {
    this.nodesById[id] = element;
    element.id = id;
    return element;
  }
}

const documentRef = new FakeDocument();
const navbar = documentRef.register("navbar", new FakeElement("nav"));
documentRef.appendChild(navbar);

const languageButton = documentRef.register("language-menu-button", new FakeElement("button"));
const languageMenu = documentRef.register("language-menu", new FakeElement("div"));
languageMenu.classList.add("hidden");
navbar.appendChild(languageButton);
navbar.appendChild(languageMenu);

const profileButton = documentRef.register("user-menu-button", new FakeElement("button"));
const profileDropdown = documentRef.register("profile-dropdown", new FakeElement("div"));
profileDropdown.classList.add("hidden");
navbar.appendChild(profileButton);
navbar.appendChild(profileDropdown);

const mobileButton = documentRef.register("show-mobile-nav-btn", new FakeElement("button"));
const mobileMenu = documentRef.register("mobile-menu", new FakeElement("div"));
mobileMenu.classList.add("hidden");
navbar.appendChild(mobileButton);
navbar.appendChild(mobileMenu);

const homeLink = new FakeElement("a");
navbar.appendChild(homeLink);

initNavbar(documentRef, { toggleTheme() {} });

languageButton.dispatchEvent("click", {
  preventDefault() {},
  stopPropagation() {},
});
assert.equal(languageMenu.classList.contains("hidden"), false);
assert.equal(languageButton.getAttribute("aria-expanded"), "true");

documentRef.dispatchEvent("click", { target: navbar });
assert.equal(languageMenu.classList.contains("hidden"), true);
assert.equal(languageButton.getAttribute("aria-expanded"), "false");

languageButton.dispatchEvent("click", {
  preventDefault() {},
  stopPropagation() {},
});
assert.equal(languageMenu.classList.contains("hidden"), false);
documentRef.dispatchEvent("keydown", { key: "Escape" });
assert.equal(languageMenu.classList.contains("hidden"), true);

console.log("navbar smoke test passed");
