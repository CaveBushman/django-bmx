const assert = require("node:assert/strict");
const { initTheme } = require("../../static/js/theme.js");

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

  toggle(value, force) {
    if (typeof force === "boolean") {
      if (force) {
        this.values.add(value);
      } else {
        this.values.delete(value);
      }
      return force;
    }

    if (this.values.has(value)) {
      this.values.delete(value);
      return false;
    }

    this.values.add(value);
    return true;
  }
}

class FakeElement {
  constructor() {
    this.classList = new FakeClassList();
  }
}

const sunIcon = new FakeElement();
sunIcon.classList.add("hidden");
const moonIcon = new FakeElement();

const documentRef = {
  documentElement: new FakeElement(),
  getElementById(id) {
    if (id === "icon-sun") {
      return sunIcon;
    }
    if (id === "icon-moon") {
      return moonIcon;
    }
    return null;
  },
};

let storedTheme = "dark";
let themeListener = null;
const windowRef = {
  localStorage: {
    getItem(key) {
      return key === "theme" ? storedTheme : null;
    },
    setItem(key, value) {
      if (key === "theme") {
        storedTheme = value;
      }
    },
  },
  matchMedia() {
    return {
      matches: false,
      addEventListener(type, handler) {
        if (type === "change") {
          themeListener = handler;
        }
      },
    };
  },
};

const controller = initTheme(documentRef, windowRef);

assert.equal(documentRef.documentElement.classList.contains("dark"), true);
assert.equal(sunIcon.classList.contains("hidden"), false);
assert.equal(moonIcon.classList.contains("hidden"), true);

controller.toggleTheme();
assert.equal(documentRef.documentElement.classList.contains("dark"), false);
assert.equal(storedTheme, "light");
assert.equal(sunIcon.classList.contains("hidden"), true);
assert.equal(moonIcon.classList.contains("hidden"), false);

storedTheme = null;
themeListener();
assert.equal(documentRef.documentElement.classList.contains("dark"), false);

console.log("theme smoke test passed");
