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
    this.name = "";
    this.value = "";
    this.accept = "";
    this.attributes = {};
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

  setAttribute(name, value) {
    this.attributes[name] = value;
  }

  getAttribute(name) {
    return this.attributes[name];
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

  createElement(tagName) {
    return new FakeElement(tagName);
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

function buildTimingSection() {
  const section = new FakeElement("section");
  section.dataset.timingSection = "";
  section.dataset.defaultMode = "rem";

  const heading = new FakeElement("h2");
  heading.dataset.timingHeading = "";
  const note = new FakeElement("p");
  note.dataset.timingNote = "";
  const resultsHelp = new FakeElement("p");
  resultsHelp.dataset.resultsHelp = "";
  const fileTypeHelp = new FakeElement("p");
  fileTypeHelp.dataset.fileTypeHelp = "";

  const remToggle = new FakeElement("button");
  remToggle.dataset.timingMode = "rem";
  const bemToggle = new FakeElement("button");
  bemToggle.dataset.timingMode = "bem";

  const entriesButton = new FakeElement("button");
  entriesButton.dataset.timingAction = "entries";
  entriesButton.dataset.remName = "btn-rem-file";
  entriesButton.dataset.bemName = "btn-bem-file";
  entriesButton.dataset.remLoadingLabel = "Generuji REM soubor...";
  entriesButton.dataset.bemLoadingLabel = "Generuji BEM soubor...";

  const ridersButton = new FakeElement("button");
  ridersButton.dataset.timingAction = "riders";
  ridersButton.dataset.remName = "btn-rem-riders-list";
  ridersButton.dataset.bemName = "btn-riders-list";
  ridersButton.dataset.remLoadingLabel = "Generuji REM seznam jezdců...";
  ridersButton.dataset.bemLoadingLabel = "Generuji BEM seznam jezdců...";

  const uploadButton = new FakeElement("button");
  uploadButton.dataset.timingAction = "upload";
  uploadButton.dataset.remName = "btn-upload-txt";
  uploadButton.dataset.bemName = "btn-upload-result";
  uploadButton.dataset.remValue = "txt";
  uploadButton.dataset.bemValue = "xls";
  uploadButton.dataset.remLoadingLabel = "Nahrávám TXT výsledky...";
  uploadButton.dataset.bemLoadingLabel = "Nahrávám XLS výsledky...";
  uploadButton.dataset.remHasResults = "false";
  uploadButton.dataset.bemHasResults = "true";

  const deleteButton = new FakeElement("button");
  deleteButton.dataset.timingAction = "delete";
  deleteButton.dataset.remName = "btn-txt-delete";
  deleteButton.dataset.bemName = "btn-delete-xls";
  deleteButton.dataset.remValue = "delete-txt";
  deleteButton.dataset.bemValue = "delete";
  deleteButton.dataset.remLoadingLabel = "Mažu TXT výsledky...";
  deleteButton.dataset.bemLoadingLabel = "Mažu XLS výsledky...";
  deleteButton.dataset.remConfirmMessage = "Opravdu smazat TXT výsledky závodu?";
  deleteButton.dataset.bemConfirmMessage = "Opravdu smazat XLS výsledky závodu?";
  deleteButton.dataset.remHasResults = "false";
  deleteButton.dataset.bemHasResults = "true";

  const fileField = buildFileField();
  fileField.input.dataset.remName = "result-file-txt";
  fileField.input.dataset.bemName = "result-file";
  fileField.input.dataset.remAccept = ".txt";
  fileField.input.dataset.bemAccept = ".xls,.xlsx";

  section.appendChild(heading);
  section.appendChild(note);
  section.appendChild(resultsHelp);
  section.appendChild(fileTypeHelp);
  section.appendChild(remToggle);
  section.appendChild(bemToggle);
  section.appendChild(entriesButton);
  section.appendChild(ridersButton);
  section.appendChild(uploadButton);
  section.appendChild(deleteButton);
  section.appendChild(fileField.field);

  return {
    section,
    heading,
    remToggle,
    bemToggle,
    entriesButton,
    ridersButton,
    uploadButton,
    deleteButton,
    fileInput: fileField.input,
  };
}

const documentRef = new FakeDocument();
const form = new FakeElement("form");
form.dataset.eventAdminForm = "";
documentRef.appendChild(form);

const firstField = buildFileField();
const secondField = buildFileField();
form.appendChild(firstField.field);
form.appendChild(secondField.field);

const timingSection = buildTimingSection();
form.appendChild(timingSection.section);

const submitButton = new FakeElement("button");
submitButton.dataset.loadingLabel = "Nahravam XLS vysledky...";
submitButton.innerHTML = "Nahrat";
form.appendChild(submitButton);

initEventAdmin(documentRef);

assert.equal(firstField.status.textContent, "Zadny soubor nevybran");
assert.equal(timingSection.heading.textContent, "Soubory pro REM");
assert.equal(timingSection.entriesButton.name, "btn-rem-file");
assert.equal(timingSection.ridersButton.name, "btn-rem-riders-list");
assert.equal(timingSection.uploadButton.name, "btn-upload-txt");
assert.equal(timingSection.uploadButton.value, "txt");
assert.equal(timingSection.uploadButton.disabled, false);
assert.equal(timingSection.deleteButton.disabled, true);
assert.equal(timingSection.fileInput.name, "result-file-txt");
assert.equal(timingSection.fileInput.accept, ".txt");

timingSection.bemToggle.dispatchEvent("click");
assert.equal(timingSection.heading.textContent, "Soubory pro BEM");
assert.equal(timingSection.entriesButton.name, "btn-bem-file");
assert.equal(timingSection.ridersButton.name, "btn-riders-list");
assert.equal(timingSection.uploadButton.name, "btn-upload-result");
assert.equal(timingSection.uploadButton.value, "xls");
assert.equal(timingSection.uploadButton.disabled, true);
assert.equal(timingSection.deleteButton.name, "btn-delete-xls");
assert.equal(timingSection.deleteButton.value, "delete");
assert.equal(timingSection.deleteButton.disabled, false);
assert.equal(timingSection.fileInput.name, "result-file");
assert.equal(timingSection.fileInput.accept, ".xls,.xlsx");
assert.equal(timingSection.bemToggle.getAttribute("aria-pressed"), "true");

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
