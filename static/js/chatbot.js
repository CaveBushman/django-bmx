function scrollToBottom() {
  const chatMessages = document.getElementById("chat-messages");
  if (!chatMessages) {
    return;
  }

  const observer = new ResizeObserver(() => {
    chatMessages.scrollTop = chatMessages.scrollHeight;
  });
  observer.observe(chatMessages);

  requestAnimationFrame(() => {
    chatMessages.scrollTop = chatMessages.scrollHeight;
  });

  [50, 150, 300].forEach((delay) => {
    setTimeout(() => {
      chatMessages.scrollTop = chatMessages.scrollHeight;
    }, delay);
  });
}

function getChatStorage(key, fallback) {
  return JSON.parse(localStorage.getItem(key) || JSON.stringify(fallback));
}

function saveMessageToLocal(role, content, time) {
  const messages = getChatStorage("chatMessages", []);
  messages.push({ role, content, time });
  localStorage.setItem("chatMessages", JSON.stringify(messages));
}

function closeChat() {
  const chatbox = document.getElementById("chatbot-box");
  if (chatbox) {
    chatbox.style.display = "none";
  }
  localStorage.setItem("chipkaVisible", "false");
}

function toggleChat() {
  const chatbox = document.getElementById("chatbot-box");
  if (!chatbox) {
    return;
  }

  const isHidden = window.getComputedStyle(chatbox).display === "none";
  chatbox.style.display = isHidden ? "flex" : "none";
  localStorage.setItem("chipkaVisible", isHidden ? "true" : "false");
}

function clearAllMessages() {
  if (!window.confirm("Opravdu chceš smazat všechny zprávy?")) {
    return;
  }

  const chatList = document.getElementById("chat-messages-list");
  const chatbotControls = document.getElementById("chatbot-controls");
  const toggleBtn = document.getElementById("important-filter-toggle");

  if (chatList) {
    chatList.innerHTML = "";
  }

  localStorage.removeItem("chatMessages");
  localStorage.removeItem("importantReplies");
  localStorage.setItem("showOnlyImportant", "false");

  if (toggleBtn) {
    toggleBtn.textContent = "🔎 Zobrazit jen důležité";
  }
  if (chatbotControls) {
    chatbotControls.classList.add("hidden");
  }

  closeChat();
}

function toggleImportant(button) {
  const replyBubble = button.closest("div.relative");
  const wrapper = button.closest(".reply-message");
  if (!replyBubble || !wrapper) {
    return;
  }

  const contentText = replyBubble.childNodes[2]?.textContent?.trim() || "";
  let stored = getChatStorage("importantReplies", []);

  if (wrapper.classList.contains("important")) {
    wrapper.classList.remove("important");
    stored = stored.filter((text) => text !== contentText);
    button.textContent = "☆";
  } else {
    wrapper.classList.add("important");
    stored.push(contentText);
    button.textContent = "★";
  }

  localStorage.setItem("importantReplies", JSON.stringify(stored));
  toggleImportantFilter();
}

let showOnlyImportant = false;

function toggleImportantFilter() {
  const allReplies = document.querySelectorAll("#chat-messages-list .reply-message");
  const allUserMessages = document.querySelectorAll("#chat-messages-list .user-message");
  const toggleBtn = document.getElementById("important-filter-toggle");

  if (!toggleBtn || allReplies.length === 0) {
    return;
  }

  showOnlyImportant = !showOnlyImportant;

  allReplies.forEach((message) => {
    if (showOnlyImportant && !message.classList.contains("important")) {
      message.style.display = "none";
    } else {
      message.style.display = "";
    }
  });

  allUserMessages.forEach((message) => {
    message.style.display = showOnlyImportant ? "none" : "";
  });

  toggleBtn.textContent = showOnlyImportant
    ? "👁️ Zobrazit všechny zprávy"
    : "🔎 Zobrazit jen důležité";
  localStorage.setItem("showOnlyImportant", String(showOnlyImportant));
  scrollToBottom();
}

function buildUserMessage(content, formattedTime) {
  const wrapper = document.createElement("div");
  wrapper.className = "user-message mb-4 flex justify-end items-end gap-2";

  const avatar = document.createElement("div");
  avatar.innerHTML =
    '<div class="w-8 h-8 rounded-full bg-indigo-600 text-white flex items-center justify-center text-xs font-bold">TY</div>';

  const bubble = document.createElement("div");
  bubble.className =
    "relative bg-indigo-100 text-sm text-gray-800 p-3 rounded-lg max-w-xs shadow";
  bubble.innerHTML = `
    <div class="absolute right-[-8px] top-3 w-0 h-0 border-t-8 border-t-transparent border-l-8 border-l-indigo-100 border-b-8 border-b-transparent"></div>
    ${content}
    <div class="text-xs text-gray-500 mt-2 text-right">${formattedTime}</div>
  `;

  wrapper.appendChild(bubble);
  wrapper.appendChild(avatar);
  return wrapper;
}

function buildBotMessage(content, formattedTime) {
  const wrapper = document.createElement("div");
  wrapper.className = "reply-message mb-4 flex justify-start items-end gap-2";

  const avatar = document.createElement("div");
  avatar.innerHTML =
    '<div class="w-8 h-8 rounded-full bg-gray-400 text-white flex items-center justify-center text-xs font-bold">BMX</div>';

  const bubble = document.createElement("div");
  bubble.className =
    "relative bg-gray-100 text-sm text-gray-800 p-3 rounded-lg max-w-xs shadow";
  bubble.innerHTML = `
    <div class="absolute left-[-8px] top-3 w-0 h-0 border-t-8 border-t-transparent border-r-8 border-r-gray-100 border-b-8 border-b-transparent"></div>
    ${content}
    <div class="text-xs text-gray-500 mt-2 text-left">${formattedTime}</div>
    <button type="button" class="ml-2 text-xs text-yellow-500 chatbot-important-toggle">☆</button>
  `;

  wrapper.appendChild(avatar);
  wrapper.appendChild(bubble);
  return wrapper;
}

async function sendMessage() {
  const input = document.getElementById("chat-input");
  const chatMessages = document.getElementById("chat-messages-list");
  const controls = document.getElementById("chatbot-controls");
  const csrfToken = document.body.dataset.csrfToken;
  if (!input || !chatMessages || !csrfToken) {
    return;
  }

  const message = input.value.trim();
  if (!message) {
    return;
  }

  const now = new Date();
  const formattedTime = now.toLocaleString("cs-CZ", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });

  chatMessages.appendChild(buildUserMessage(message, formattedTime));
  if (controls) {
    controls.classList.remove("hidden");
  }
  input.value = "";
  scrollToBottom();
  saveMessageToLocal("user", message, formattedTime);

  const loading = document.createElement("div");
  loading.id = "chatbot-loading";
  loading.className = "text-sm text-gray-400 italic mb-4";
  loading.textContent = "Czech BMX chatbot přemýšlí...";
  chatMessages.appendChild(loading);

  try {
    const response = await fetch("/api/chatbot", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": csrfToken,
      },
      credentials: "include",
      body: JSON.stringify({ message }),
    });
    const data = await response.json();
    loading.remove();

    const replyContent = data.reply || data.error || "Došlo k chybě při komunikaci.";
    const reply = buildBotMessage(replyContent, formattedTime);
    chatMessages.appendChild(reply);
    scrollToBottom();
    saveMessageToLocal("bot", replyContent, formattedTime);
  } catch (error) {
    loading.remove();
    const errorMessage = buildBotMessage("Chyba při komunikaci s asistentem.", formattedTime);
    chatMessages.appendChild(errorMessage);
  }
}

function restoreChatMessages() {
  const messages = getChatStorage("chatMessages", []);
  const importantReplies = getChatStorage("importantReplies", []);
  const container = document.getElementById("chat-messages-list");
  const controls = document.getElementById("chatbot-controls");
  const toggleBtn = document.getElementById("important-filter-toggle");

  if (!container) {
    return;
  }

  messages.forEach((message) => {
    const wrapper = message.role === "user"
      ? buildUserMessage(message.content, message.time)
      : buildBotMessage(message.content, message.time);

    if (message.role === "bot" && importantReplies.includes(message.content)) {
      wrapper.classList.add("important");
      const button = wrapper.querySelector(".chatbot-important-toggle");
      if (button) {
        button.textContent = "★";
      }
    }

    container.appendChild(wrapper);
  });

  if (messages.length > 0 && controls) {
    controls.classList.remove("hidden");
  }

  if (toggleBtn) {
    toggleBtn.textContent = "🔎 Zobrazit jen důležité";
    if (localStorage.getItem("showOnlyImportant") === "true") {
      showOnlyImportant = true;
      toggleImportantFilter();
    }
  }
}

function formatCredit() {
  const creditElement = document.getElementById("credit");
  if (!creditElement) {
    return;
  }

  const creditText = creditElement.innerText;
  const credit = parseInt(creditText.replace(" CZK", "").trim(), 10);
  if (!Number.isNaN(credit)) {
    creditElement.innerText = `${credit.toLocaleString("cs-CZ")} CZK`;
  }
}

document.addEventListener("DOMContentLoaded", () => {
  formatCredit();
  restoreChatMessages();

  const sendButton = document.getElementById("sendButton");
  const chatInput = document.getElementById("chat-input");
  const toggleButtons = document.querySelectorAll("#chatbot-toggle button, #chatbot-box button[data-chat-close]");
  const importantToggle = document.getElementById("important-filter-toggle");
  const clearButton = document.getElementById("chatbot-clear");

  if (sendButton) {
    sendButton.addEventListener("click", (event) => {
      event.preventDefault();
      sendMessage();
    });
  }

  if (chatInput) {
    chatInput.addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        sendMessage();
      }
    });
  }

  toggleButtons.forEach((button) => {
    button.addEventListener("click", (event) => {
      event.preventDefault();
      toggleChat();
    });
  });

  if (importantToggle) {
    importantToggle.addEventListener("click", (event) => {
      event.preventDefault();
      toggleImportantFilter();
    });
  }

  if (clearButton) {
    clearButton.addEventListener("click", (event) => {
      event.preventDefault();
      clearAllMessages();
    });
  }

  document.addEventListener("click", (event) => {
    const button = event.target.closest(".chatbot-important-toggle");
    if (button) {
      event.preventDefault();
      toggleImportant(button);
    }
  });

  if (localStorage.getItem("chipkaVisible") === "true") {
    const chatbox = document.getElementById("chatbot-box");
    if (chatbox) {
      chatbox.style.display = "flex";
    }
  }
});
window.toggleChat = toggleChat;
window.clearAllMessages = clearAllMessages;
