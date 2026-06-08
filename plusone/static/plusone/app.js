function updateCountdowns() {
  const now = new Date();
  document.querySelectorAll(".countdown[data-deadline]").forEach((node) => {
    const deadline = new Date(node.dataset.deadline);
    const delta = deadline - now;
    if (Number.isNaN(deadline.getTime())) {
      node.textContent = "--";
      return;
    }
    if (delta <= 0) {
      node.textContent = "expired";
      node.classList.add("expired");
      return;
    }
    const totalSeconds = Math.floor(delta / 1000);
    const minutes = Math.floor(totalSeconds / 60);
    const seconds = totalSeconds % 60;
    node.textContent = `${minutes}m ${String(seconds).padStart(2, "0")}s`;
  });
}

function updateCreatePreview() {
  const titleInput = document.getElementById("id_title");
  const descriptionInput = document.getElementById("id_description");
  const activityInput = document.getElementById("id_activity_type");
  const locationInput = document.getElementById("id_location");
  const startInput = document.getElementById("id_start_time");
  const expireInput = document.getElementById("id_expire_minutes");
  const previewTitle = document.querySelector("[data-post-preview-title]");
  if (!previewTitle) return;

  const previewDescription = document.querySelector("[data-post-preview-description]");
  const previewActivity = document.querySelector("[data-post-preview-activity]");
  const previewLocation = document.querySelector("[data-post-preview-location]");
  const previewTime = document.querySelector("[data-post-preview-time]");
  const previewExpire = document.querySelector("[data-post-preview-expire]");
  const previewCard = previewTitle.closest(".activity-card");
  const selectedActivity = activityInput?.value || "other";

  previewTitle.textContent = titleInput?.value || "Your Plus One title";
  previewDescription.textContent = descriptionInput?.value || "The card preview updates as you edit the structured fields.";
  previewActivity.textContent = activityInput?.selectedOptions?.[0]?.textContent || "Other";
  previewLocation.textContent = locationInput?.selectedOptions?.[0]?.textContent || "Campus location";
  previewTime.textContent = startInput?.value || "Start time";
  previewExpire.textContent = expireInput?.value || "45";
  if (previewCard) {
    previewCard.classList.remove("color-food", "color-sports", "color-study", "color-club", "color-explore", "color-other");
    previewCard.classList.add(`color-${selectedActivity}`);
  }
}

function appendChatMessage(list, message) {
  const empty = list.querySelector("[data-empty-chat]");
  if (empty) {
    empty.remove();
  }

  const bubble = document.createElement("div");
  bubble.className = `bubble ${message.bubble_class}`;
  bubble.dataset.messageId = message.id;

  const meta = document.createElement("small");
  meta.textContent = `${message.sender_label} · ${message.created_at}${message.is_flagged ? " · flagged" : ""}`;

  const text = document.createElement("p");
  text.textContent = message.message;

  bubble.append(meta, text);
  list.append(bubble);
  list.dataset.lastMessageId = String(message.id);
  list.scrollTop = list.scrollHeight;
}

function setupChatPolling() {
  const panel = document.querySelector("[data-chat-endpoint]");
  const list = document.querySelector("[data-chat-messages]");
  if (!panel || !list) return;

  const endpoint = panel.dataset.chatEndpoint;
  const form = document.querySelector("[data-chat-form]");
  const input = form?.querySelector("input[name='message']");
  const submit = form?.querySelector("button[type='submit']");
  let pollTimer = null;

  async function fetchMessages() {
    const after = list.dataset.lastMessageId || "0";
    const response = await fetch(`${endpoint}?after=${encodeURIComponent(after)}`, {
      headers: { "Accept": "application/json" },
    });
    if (!response.ok) return;
    const data = await response.json();
    if (data.chat_status && panel.dataset.chatStatus && data.chat_status !== panel.dataset.chatStatus) {
      window.location.reload();
      return;
    }
    data.messages?.forEach((message) => appendChatMessage(list, message));
    if (form && data.chat_active === false) {
      form.remove();
      if (pollTimer) {
        clearInterval(pollTimer);
      }
    }
  }

  if (form && input) {
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const text = input.value.trim();
      if (!text) return;

      const formData = new FormData(form);
      if (submit) submit.disabled = true;
      try {
        const response = await fetch(endpoint, {
          method: "POST",
          body: formData,
          headers: { "Accept": "application/json" },
        });
        const data = await response.json();
        if (response.ok && data.message) {
          appendChatMessage(list, data.message);
          input.value = "";
        }
      } finally {
        if (submit) submit.disabled = false;
        input.focus();
      }
    });
  }

  fetchMessages();
  pollTimer = setInterval(fetchMessages, 2000);
}

function setupIdentityResetConfirm() {
  document.querySelectorAll("[data-confirm-reset]").forEach((form) => {
    form.addEventListener("submit", (event) => {
      const message = form.dataset.confirmReset;
      if (message && !window.confirm(message)) {
        event.preventDefault();
      }
    });
  });
}

document.addEventListener("DOMContentLoaded", () => {
  updateCountdowns();
  setInterval(updateCountdowns, 1000);
  updateCreatePreview();
  setupChatPolling();
  setupIdentityResetConfirm();
  ["id_title", "id_description", "id_activity_type", "id_location", "id_start_time", "id_expire_minutes"].forEach((id) => {
    const field = document.getElementById(id);
    if (field) {
      field.addEventListener("input", updateCreatePreview);
      field.addEventListener("change", updateCreatePreview);
    }
  });
});
