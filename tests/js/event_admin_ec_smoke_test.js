const assert = require("node:assert/strict");
const { initEventAdminEc } = require("../../static/js/event_admin_ec.js");

class FakeElement {
  constructor(tagName, ownerDocument) {
    this.tagName = tagName.toUpperCase();
    this.ownerDocument = ownerDocument;
    this.children = [];
    this.parentNode = null;
    this.attributes = {};
    this.dataset = {};
    this.eventListeners = {};
    this.className = "";
    this.textContent = "";
    this.innerHTML = "";
    this.disabled = false;
    this.type = "";
    this.name = "";
    this.accept = "";
  }

  appendChild(child) {
    child.parentNode = this;
    this.children.push(child);
    return child;
  }

  remove() {
    if (!this.parentNode) {
      return;
    }
    const siblings = this.parentNode.children;
    const index = siblings.indexOf(this);
    if (index >= 0) {
      siblings.splice(index, 1);
    }
    this.parentNode = null;
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

class FakeDocument {
  constructor() {
    this.nodesById = {};
  }

  createElement(tagName) {
    return new FakeElement(tagName, this);
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

function matchesSelector(element, selector) {
  if (selector.startsWith(".")) {
    return element.className.split(/\s+/).includes(selector.slice(1));
  }
  return element.tagName.toLowerCase() === selector.toLowerCase();
}

function buildInputRow(documentRef, index) {
  const row = documentRef.createElement("div");
  row.className = "ec-results-input-row";

  const header = documentRef.createElement("div");
  header.className = "ec-results-input-header";

  const label = documentRef.createElement("label");
  label.textContent = `PDF výsledků ${index}`;

  const removeButton = documentRef.createElement("button");
  removeButton.className = "ec-results-remove";
  removeButton.textContent = "−";

  const input = documentRef.createElement("input");
  input.type = "file";

  header.appendChild(label);
  header.appendChild(removeButton);
  row.appendChild(header);
  row.appendChild(input);
  return row;
}

const documentRef = new FakeDocument();

const form = documentRef.createElement("form");
const payment = documentRef.register("payment-amount", documentRef.createElement("div"));
payment.textContent = "12345";

const addButton = documentRef.register("ec-results-add-input", documentRef.createElement("button"));
const inputsWrapper = documentRef.register("ec-results-inputs", documentRef.createElement("div"));
const submitButton = documentRef.register("ec-results-submit", documentRef.createElement("button"));
submitButton.dataset.loadingLabel = "Nahrávám...";
submitButton.innerHTML = "Nahrát a sloučit PDF";

form.appendChild(addButton);
form.appendChild(inputsWrapper);
form.appendChild(submitButton);
inputsWrapper.appendChild(buildInputRow(documentRef, 1));

initEventAdminEc(documentRef);

assert.equal(payment.textContent, "12\u00a0345 CZK");

addButton.dispatchEvent("click");
assert.equal(inputsWrapper.querySelectorAll(".ec-results-input-row").length, 2);
assert.equal(inputsWrapper.querySelectorAll("label")[1].textContent, "PDF výsledků 2");

const secondRemove = inputsWrapper.querySelectorAll(".ec-results-remove")[1];
inputsWrapper.dispatchEvent("click", { target: secondRemove });
assert.equal(inputsWrapper.querySelectorAll(".ec-results-input-row").length, 1);
assert.equal(inputsWrapper.querySelector("label").textContent, "PDF výsledků 1");

form.dispatchEvent("submit", { submitter: submitButton });
assert.equal(submitButton.disabled, true);
assert.match(submitButton.innerHTML, /Nahrávám/);

console.log("event_admin_ec smoke test passed");
