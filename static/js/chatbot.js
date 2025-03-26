function toggleChat() {
  const box = document.getElementById("chatbot-box");
  box.classList.toggle("hidden");
}

document.addEventListener("DOMContentLoaded", function() {
    const form = document.getElementById("chatbot-form");
    if (form) {
        form.addEventListener("submit", function(event) {
            event.preventDefault(); // Aby formulář neodeslal stránku
            sendMessage();
        });
    }
});

async function sendMessage() {
  const input = document.getElementById("query");
  const chat = document.getElementById("chat-messages");
  const text = input.value.trim();
  if (!text) return;

  const userMsg = document.createElement("div");
  userMsg.className = "user-message mb-4";

  const userText = document.createElement("div");
  userText.className = "text-sm text-gray-800";
  userText.textContent = text;

  const userTime = document.createElement("div");
  userTime.className = "text-xs text-gray-500 mt-1 text-right";
  userTime.textContent = new Date().toLocaleString('cs-CZ', {
    day: '2-digit', month: '2-digit', year: 'numeric',
    hour: '2-digit', minute: '2-digit'
  });

  userMsg.appendChild(userText);
  userMsg.appendChild(userTime);
  chat.appendChild(userMsg);

  const loading = document.createElement("div");
  loading.id = "chatbot-loading";
  loading.className = "text-gray-400 italic text-sm";
  loading.innerHTML = `BMX bot přemýšlí...`;
  chat.appendChild(loading);
  chat.scrollTop = chat.scrollHeight;

  input.value = "";

  try {
    const res = await fetch("/api/chatbot", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": window.csrfToken
      },
      body: JSON.stringify({ message: text })
    });
    const data = await res.json();
    document.getElementById("chatbot-loading").remove();

    const reply = document.createElement("div");
    reply.className = "reply-message mb-4";

    const replyText = document.createElement("div");
    replyText.className = "text-sm text-gray-800";
    replyText.textContent = data.reply;

    const replyTime = document.createElement("div");
    replyTime.className = "text-xs text-gray-500 mt-1 text-left";
    replyTime.textContent = new Date().toLocaleString('cs-CZ', {
      day: '2-digit', month: '2-digit', year: 'numeric',
      hour: '2-digit', minute: '2-digit'
    });

    reply.appendChild(replyText);
    reply.appendChild(replyTime);
    chat.appendChild(reply);
    chat.scrollTop = chat.scrollHeight;
  } catch (e) {
    document.getElementById("chatbot-loading").remove();
    const error = document.createElement("div");
    error.className = "text-red-500 text-sm italic";
    error.textContent = "Chyba při komunikaci s asistentem.";
    chat.appendChild(error);
  }
}
