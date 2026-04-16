const assert = require("node:assert/strict");
const { initRiderInactiveModal } = require("../../static/js/rider_inactive.js");

class FakeClassList {
  constructor() {
    this.values = new Set();
  }
  add(...names) {
    names.forEach((name) => this.values.add(name));
  }
  remove(...names) {
    names.forEach((name) => this.values.delete(name));
  }
  contains(name) {
    return this.values.has(name);
  }
}

class FakeElement {
  constructor(tagName, ownerDocument) {
    this.tagName = tagName.toUpperCase();
    this.ownerDocument = ownerDocument;
    this.children = [];
    this.parentNode = null;
    this.dataset = {};
    this.eventListeners = {};
    this.classList = new FakeClassList();
    this.textContent = "";
    this.firstElementChild = null;
    this.submitted = false;
  }

  appendChild(child) {
    child.parentNode = this;
    this.children.push(child);
    if (!this.firstElementChild) {
      this.firstElementChild = child;
    }
    return child;
  }

  addEventListener(type, handler) {
    if (!this.eventListeners[type]) {
      this.eventListeners[type] = [];
    }
    this.eventListeners[type].push(handler);
  }

  dispatchEvent(type, event = {}) {
    if (!event.preventDefault) {
      event.preventDefault = function () {
        this.defaultPrevented = true;
      };
    }
    if (!event.target) {
      event.target = this;
    }
    (this.eventListeners[type] || []).forEach((handler) => handler(event));
  }

  querySelectorAll(selector) {
    const results = [];
    const walk = (node) => {
      node.children.forEach((child) => {
        if (selector === "[data-release-trigger]" && child.dataset.releaseTrigger !== undefined) {
          results.push(child);
        }
        walk(child);
      });
    };
    walk(this);
    return results;
  }

  closest(selector) {
    let current = this;
    while (current) {
      if (selector === "[data-release-form]" && current.dataset.releaseForm !== undefined) {
        return current;
      }
      current = current.parentNode;
    }
    return null;
  }

  submit() {
    this.submitted = true;
  }
}

class FakeDocument {
  constructor() {
    this.nodesById = {};
    this.eventListeners = {};
    this.body = new FakeElement("body", this);
  }

  createElement(tagName) {
    return new FakeElement(tagName, this);
  }

  getElementById(id) {
    return this.nodesById[id] || null;
  }

  querySelectorAll(selector) {
    return this.body.querySelectorAll(selector);
  }

  addEventListener(type, handler) {
    if (!this.eventListeners[type]) {
      this.eventListeners[type] = [];
    }
    this.eventListeners[type].push(handler);
  }

  dispatchEvent(type, event) {
    (this.eventListeners[type] || []).forEach((handler) => handler(event));
  }

  register(id, element) {
    this.nodesById[id] = element;
    return element;
  }
}

const documentRef = new FakeDocument();
const modal = documentRef.register("inactive-release-modal", documentRef.createElement("div"));
modal.classList.add("hidden");
const overlay = documentRef.createElement("div");
modal.appendChild(overlay);
documentRef.body.appendChild(modal);

const riderLabel = documentRef.register("inactive-release-modal-rider", documentRef.createElement("span"));
const closeButton = documentRef.register("inactive-release-modal-close", documentRef.createElement("button"));
const cancelButton = documentRef.register("inactive-release-modal-cancel", documentRef.createElement("button"));
const confirmButton = documentRef.register("inactive-release-modal-confirm", documentRef.createElement("button"));

documentRef.body.appendChild(riderLabel);
documentRef.body.appendChild(closeButton);
documentRef.body.appendChild(cancelButton);
documentRef.body.appendChild(confirmButton);

const form = documentRef.createElement("form");
form.dataset.releaseForm = "";
form.dataset.riderName = "Test Rider";
const trigger = documentRef.createElement("button");
trigger.dataset.releaseTrigger = "";
form.appendChild(trigger);
documentRef.body.appendChild(form);

initRiderInactiveModal(documentRef);

trigger.dispatchEvent("click", { target: trigger });
assert.equal(riderLabel.textContent, "Test Rider");
assert.equal(modal.classList.contains("hidden"), false);
assert.equal(documentRef.body.classList.contains("overflow-hidden"), true);

documentRef.dispatchEvent("keydown", { key: "Escape" });
assert.equal(modal.classList.contains("hidden"), true);
assert.equal(documentRef.body.classList.contains("overflow-hidden"), false);

trigger.dispatchEvent("click", { target: trigger });
confirmButton.dispatchEvent("click", { target: confirmButton });
assert.equal(form.submitted, true);

console.log("rider_inactive smoke test passed");
