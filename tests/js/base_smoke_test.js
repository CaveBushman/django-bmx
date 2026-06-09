const assert = require("node:assert/strict");
const { initBase } = require("../../static/js/base.js");

class FakeClassList {
  constructor() {
    this.values = new Set();
  }

  add(value) {
    this.values.add(value);
  }

  contains(value) {
    return this.values.has(value);
  }
}

class FakeElement {
  constructor() {
    this.dataset = {};
    this.children = [];
    this.parentNode = null;
    this.eventListeners = {};
    this.classList = new FakeClassList();
    this.removed = false;
  }

  appendChild(child) {
    child.parentNode = this;
    this.children.push(child);
    return child;
  }

  addEventListener(type, handler) {
    if (!this.eventListeners[type]) {
      this.eventListeners[type] = [];
    }
    this.eventListeners[type].push(handler);
  }

  hasAttribute(name) {
    if (name === "data-flash-persist") {
      return Object.prototype.hasOwnProperty.call(this.dataset, "flashPersist");
    }
    return false;
  }

  dispatchEvent(type, event = {}) {
    (this.eventListeners[type] || []).forEach((handler) => handler(event));
  }

  closest(selector) {
    if (selector === "[data-confirm-message]" && Object.prototype.hasOwnProperty.call(this.dataset, "confirmMessage")) {
      return this;
    }
    return this.parentNode ? this.parentNode.closest(selector) : null;
  }

  remove() {
    this.removed = true;
  }
}

class FakeDocument extends FakeElement {
  querySelectorAll(selector) {
    if (selector === "[data-flash-message]") {
      return this.children.filter((child) => Object.prototype.hasOwnProperty.call(child.dataset, "flashMessage"));
    }
    return [];
  }
}

const documentRef = new FakeDocument();
const flashMessage = new FakeElement();
flashMessage.dataset.flashMessage = "";
documentRef.appendChild(flashMessage);

const confirmButton = new FakeElement();
confirmButton.dataset.confirmMessage = "Opravdu smazat?";
documentRef.appendChild(confirmButton);

const timeoutCalls = [];
const windowRef = {
  confirmCalls: [],
  setTimeout(handler, delay) {
    timeoutCalls.push(delay);
    handler();
  },
  confirm(message) {
    this.confirmCalls.push(message);
    return false;
  },
};

initBase(documentRef, windowRef);

assert.equal(flashMessage.classList.contains("opacity-0"), true);
assert.equal(flashMessage.removed, true);
assert.deepEqual(timeoutCalls, [5000, 500]);

let prevented = false;
let stopped = false;
documentRef.dispatchEvent("click", {
  target: confirmButton,
  preventDefault() {
    prevented = true;
  },
  stopImmediatePropagation() {
    stopped = true;
  },
});
assert.deepEqual(windowRef.confirmCalls, ["Opravdu smazat?"]);
assert.equal(prevented, true);
assert.equal(stopped, true);

console.log("base smoke test passed");
