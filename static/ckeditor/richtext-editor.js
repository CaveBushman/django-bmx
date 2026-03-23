(function () {
  function decodeHtml(value) {
    var textarea = document.createElement("textarea");
    textarea.innerHTML = value || "";
    return textarea.value;
  }

  function sanitizeHtml(html) {
    var template = document.createElement("template");
    template.innerHTML = html || "";

    var allowedTags = {
      A: ["href", "target", "rel"],
      B: [],
      BR: [],
      EM: [],
      H2: [],
      H3: [],
      H4: [],
      I: [],
      LI: [],
      OL: [],
      P: [],
      STRONG: [],
      U: [],
      UL: [],
    };

    var blockedTags = ["SCRIPT", "STYLE", "IFRAME", "OBJECT", "EMBED"];

    function walk(node) {
      var children = Array.prototype.slice.call(node.childNodes);
      children.forEach(function (child) {
        if (child.nodeType === Node.ELEMENT_NODE) {
          var tagName = child.tagName.toUpperCase();

          if (blockedTags.indexOf(tagName) !== -1) {
            child.remove();
            return;
          }

          if (!allowedTags[tagName]) {
            var fragment = document.createDocumentFragment();
            while (child.firstChild) {
              fragment.appendChild(child.firstChild);
            }
            child.replaceWith(fragment);
            return;
          }

          Array.prototype.slice.call(child.attributes).forEach(function (attribute) {
            if (allowedTags[tagName].indexOf(attribute.name) === -1) {
              child.removeAttribute(attribute.name);
            }
          });

          if (tagName === "A") {
            var href = child.getAttribute("href") || "";
            if (
              href &&
              href.charAt(0) !== "/" &&
              href.charAt(0) !== "#" &&
              !/^https?:\/\//i.test(href) &&
              !/^mailto:/i.test(href) &&
              !/^tel:/i.test(href)
            ) {
              child.removeAttribute("href");
            }
            if (child.getAttribute("target") === "_blank") {
              child.setAttribute("rel", "noopener noreferrer");
            }
          }

          walk(child);
          return;
        }

        if (child.nodeType === Node.COMMENT_NODE) {
          child.remove();
        }
      });
    }

    walk(template.content);
    return template.innerHTML;
  }

  function createButton(label, command, value) {
    var button = document.createElement("button");
    button.type = "button";
    button.className = "rt-toolbar__button";
    button.textContent = label;
    button.dataset.command = command;
    if (value) {
      button.dataset.value = value;
    }
    return button;
  }

  function createToolbar() {
    var toolbar = document.createElement("div");
    toolbar.className = "rt-toolbar";
    [
      createButton("B", "bold"),
      createButton("I", "italic"),
      createButton("U", "underline"),
      createButton("H2", "formatBlock", "h2"),
      createButton("H3", "formatBlock", "h3"),
      createButton("Odrážky", "insertUnorderedList"),
      createButton("Číslování", "insertOrderedList"),
      createButton("Odkaz", "createLink"),
      createButton("Zrušit odkaz", "unlink"),
      createButton("Vyčistit", "removeFormat"),
    ].forEach(function (button) {
      toolbar.appendChild(button);
    });
    return toolbar;
  }

  function syncEditor(editable, textarea) {
    textarea.value = sanitizeHtml(editable.innerHTML);
  }

  function initializeRichText(textarea) {
    if (!textarea || textarea.dataset.richtextInitialized === "1") {
      return;
    }

    textarea.dataset.richtextInitialized = "1";
    textarea.classList.add("rt-source");

    var wrapper = document.createElement("div");
    wrapper.className = "rt-editor";

    var toolbar = createToolbar();
    var editable = document.createElement("div");
    editable.className = "rt-editor__surface";
    editable.contentEditable = "true";
    editable.dataset.placeholder = "Pište obsah propozic nebo článku...";
    editable.innerHTML = sanitizeHtml(decodeHtml(textarea.value));

    textarea.parentNode.insertBefore(wrapper, textarea);
    wrapper.appendChild(toolbar);
    wrapper.appendChild(editable);
    wrapper.appendChild(textarea);

    toolbar.addEventListener("click", function (event) {
      var button = event.target.closest("button[data-command]");
      if (!button) {
        return;
      }

      var command = button.dataset.command;
      var value = button.dataset.value || null;

      if (command === "createLink") {
        var selected = window.getSelection().toString().trim();
        var url = window.prompt("Zadejte URL odkazu", "https://");
        if (!url) {
          return;
        }
        document.execCommand("createLink", false, url);
        if (!selected) {
          syncEditor(editable, textarea);
        }
      } else if (command === "formatBlock") {
        document.execCommand(command, false, value.toUpperCase());
      } else {
        document.execCommand(command, false, value);
      }

      editable.focus();
      syncEditor(editable, textarea);
    });

    editable.addEventListener("input", function () {
      syncEditor(editable, textarea);
    });

    editable.addEventListener("blur", function () {
      editable.innerHTML = sanitizeHtml(editable.innerHTML);
      syncEditor(editable, textarea);
    });

    if (textarea.form) {
      textarea.form.addEventListener("submit", function () {
        editable.innerHTML = sanitizeHtml(editable.innerHTML);
        syncEditor(editable, textarea);
      });
    }

    syncEditor(editable, textarea);
  }

  function boot() {
    document.querySelectorAll("textarea[data-richtext-editor='1']").forEach(initializeRichText);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }

  document.addEventListener("formset:added", function () {
    boot();
  });
})();
