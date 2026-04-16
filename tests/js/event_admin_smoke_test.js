const assert = require("node:assert/strict");
const { initEventAdmin } = require("../../static/js/event_admin.js");

class FakeElement {
  constructor(tagName) {
    this.tagName = tagName.toUpperCase();
    this.children = [];
    this.parentNode = null;
    this.dataset = {};
    this.eventListeners = {};
    this.innerHTML = "";
    this.textContent = "";
    this.disabled = false;
    this.files = [];
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

  dispatchEvent(type, event = {}) {
    (this.eventListeners[type] || []).forEach((handler) => handler(event));
  }

  closest(selector) {
    let current = this;
    while (current) {
      if (matchesSelector(current, selector)) {
        return current;
      }
      current = current.parentNode;
    }
    return null;
  }

  querySelector(selector) {
    return this.querySelectorAll(selector)[0] || null;
  }

  querySelectorAll(selector) {
    const matches = [];
    const walk = (node) => {
      node.children.forEach((child) => {
        if (matchesSelector(child, selector)) {
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
  }
}

function matchesSelector(element, selector) {
  if (selector.startsWith("[") && selector.endsWith("]")) {
    const attr = selector.slice(1, -1);
    const dataAttr = attr.startsWith("data-") ? attr.slice(5).replace(/-([a-z])/g, (_, ch) => ch.toUpperCase()) : null;
    return dataAttr ? Object.prototype.hasOwnProperty.call(element.dataset, dataAttr) : false;
  }
  return false;
}

function buildFileField() {
  const field = new FakeElement("div");
  field.dataset.fileField = "";

  const input = new FakeElement("input");
  input.dataset.fileInput = "";

  const status = new FakeElement("p");
  status.dataset.fileSelection = "";

  field.appendChild(input);
  field.appendChild(status);
  return { field, input, status };
}

const documentRef = new FakeDocument();
const form = new FakeElement("form");
form.dataset.eventAdminForm = "";
documentRef.appendChild(form);

const firstField = buildFileField();
const secondField = buildFileField();
form.appendChild(firstField.field);
form.appendChild(secondField.field);

const submitButton = new FakeElement("button");
submitButton.dataset.loadingLabel = "Nahravam XLS vysledky...";
submitButton.innerHTML = "Nahrat";
form.appendChild(submitButton);

initEventAdmin(documentRef);

assert.equal(firstField.status.textContent, "Zadny soubor nevybran");

firstField.input.files = [{ name: "results.xlsx" }];
firstField.input.dispatchEvent("change");
assert.equal(firstField.status.textContent, "Vybrano: results.xlsx");
assert.equal(firstField.status.dataset.hasFile, "true");

secondField.input.files = [{ name: "moto1.txt" }, { name: "moto2.txt" }];
secondField.input.dispatchEvent("change");
assert.equal(secondField.status.textContent, "Vybrano souboru: 2");

form.dispatchEvent("submit", { submitter: submitButton });
assert.equal(submitButton.disabled, true);
assert.match(submitButton.innerHTML, /Nahravam XLS vysledky/);

console.log("event_admin smoke test passed");
