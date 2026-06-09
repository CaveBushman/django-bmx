const assert = require("node:assert/strict");
const { initImportStats } = require("../../static/js/import_stats.js");

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
    if (force) {
      this.add(value);
    } else {
      this.remove(value);
    }
  }
}

class FakeElement {
  constructor(tagName) {
    this.tagName = tagName.toUpperCase();
    this.children = [];
    this.parentNode = null;
    this.dataset = {};
    this.eventListeners = {};
    this.classList = new FakeClassList();
    this.disabled = false;
    this.files = [];
    this.id = "";
    this.innerHTML = "";
    this.name = "";
    this.type = "";
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

  querySelectorAll(selector) {
    return queryAll(this, selector);
  }
}

class FakeDocument extends FakeElement {
  constructor() {
    super("document");
    this.nodesById = {};
  }

  register(id, element) {
    this.nodesById[id] = element;
    element.id = id;
    return element;
  }

  getElementById(id) {
    return this.nodesById[id] || null;
  }

  querySelectorAll(selector) {
    if (selector === '#uploadForm input[type="file"]') {
      const form = this.getElementById("uploadForm");
      return form ? queryAll(form, 'input[type="file"]') : [];
    }
    return queryAll(this, selector);
  }
}

function queryAll(root, selector) {
  const matches = [];
  const walk = (node) => {
    node.children.forEach((child) => {
      if (matchesSelector(child, selector)) {
        matches.push(child);
      }
      walk(child);
    });
  };
  walk(root);
  return matches;
}

function matchesSelector(element, selector) {
  if (selector === 'input[type="file"]') {
    return element.tagName === "INPUT" && element.type === "file";
  }
  if (selector === 'button[type="submit"]') {
    return element.tagName === "BUTTON" && element.type === "submit";
  }
  return false;
}

const documentRef = new FakeDocument();
const form = documentRef.register("uploadForm", new FakeElement("form"));
const input = new FakeElement("input");
input.type = "file";
const submitButton = documentRef.register("submitBtn", new FakeElement("button"));
submitButton.type = "submit";
submitButton.innerHTML = "Nahrát vybrané soubory";
const deleteButton = new FakeElement("button");
deleteButton.type = "submit";
deleteButton.innerHTML = "Smazat";

form.appendChild(input);
form.appendChild(submitButton);
form.appendChild(deleteButton);
documentRef.appendChild(form);

const timeoutCalls = [];
const windowRef = {
  setTimeout(handler, delay) {
    timeoutCalls.push({ handler, delay });
  },
};

initImportStats(documentRef, windowRef);

assert.equal(input.classList.contains("is-selected"), false);
input.files = [{ name: "motos.html" }];
input.dispatchEvent("change");
assert.equal(input.classList.contains("is-selected"), true);
assert.equal(input.classList.contains("bg-indigo-50"), true);

submitButton.dispatchEvent("click");
form.dispatchEvent("submit", { submitter: submitButton });
assert.equal(form.dataset.submitting, "true");
assert.equal(submitButton.disabled, true);
assert.equal(deleteButton.disabled, true);
assert.match(submitButton.innerHTML, /Nahrávám/);
assert.deepEqual(timeoutCalls.map((call) => call.delay), [30000]);

let prevented = false;
form.dispatchEvent("submit", {
  submitter: submitButton,
  preventDefault() {
    prevented = true;
  },
});
assert.equal(prevented, true);

timeoutCalls[0].handler();
assert.equal(form.dataset.submitting, "false");
assert.equal(submitButton.disabled, false);
assert.equal(deleteButton.disabled, false);
assert.equal(submitButton.innerHTML, "Nahrát vybrané soubory");

console.log("import stats smoke test passed");
