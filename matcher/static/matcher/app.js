function getCookie(name) {
  const value = `; ${document.cookie}`;
  const parts = value.split(`; ${name}=`);
  if (parts.length === 2) return parts.pop().split(";").shift();
  return "";
}

function postForm(url, data) {
  return fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/x-www-form-urlencoded",
      "X-CSRFToken": getCookie("csrftoken"),
    },
    body: new URLSearchParams(data),
  }).then((response) => {
    if (!response.ok) throw new Error("Request failed");
    return response.json();
  });
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function formatCountdown(expiresAt) {
  const diff = Math.max(0, new Date(expiresAt).getTime() - Date.now());
  const totalSeconds = Math.floor(diff / 1000);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}

function initCountdowns() {
  const nodes = document.querySelectorAll(".js-countdown");
  if (!nodes.length) return;
  const tick = () => {
    nodes.forEach((node) => {
      const value = formatCountdown(node.dataset.expiresAt);
      node.textContent = value;
      if (value === "00:00") node.classList.add("expired");
    });
  };
  tick();
  window.setInterval(tick, 1000);
}

function cardTemplate(post) {
  const typeLabel = escapeHtml(post.activityLabel);
  return `
    <article class="activity-card" data-post-id="${post.id}" style="--teal:${escapeHtml(post.accent)}">
      <div class="card-topline">
        <span class="expiry js-countdown" data-expires-at="${escapeHtml(post.expiresAt)}">${post.minutesLeft}m left</span>
      </div>
      <div class="mini-illustration"></div>
      <h3>${escapeHtml(post.title)}</h3>
      <p>${escapeHtml(post.description)}</p>
      <div class="card-tags">
        <span>${typeLabel}</span>
        <span>${escapeHtml(post.startsLabel)}</span>
        <span>${escapeHtml(post.location)}</span>
      </div>
      <div class="card-footer">
        <span class="avatar">${escapeHtml(post.hostAlias.charAt(0) || "?")}</span>
        <div>
          <strong>${escapeHtml(post.hostAlias)}</strong>
          <small>${escapeHtml(post.vibeNote || "quick chat first")}</small>
        </div>
      </div>
    </article>
  `;
}

function initSwipeDeck() {
  const dataNode = document.getElementById("post-data");
  const stage = document.getElementById("swipe-stage");
  if (!dataNode || !stage) return;

  const posts = JSON.parse(dataNode.textContent);
  let index = 0;
  let drag = null;

  function visiblePosts() {
    return posts.slice(index, index + 3);
  }

  function render() {
    const visible = visiblePosts();
    if (!visible.length) {
      stage.innerHTML = '<div class="swipe-empty">No more active cards. Create a new Plus One or refresh demo data from the dashboard.</div>';
      return;
    }
    stage.innerHTML = visible.map(cardTemplate).join("");
    initCountdowns();
    attachDrag();
  }

  function topCard() {
    return stage.querySelector(".activity-card");
  }

  function attachDrag() {
    const card = topCard();
    if (!card) return;
    card.addEventListener("pointerdown", (event) => {
      drag = {
        startX: event.clientX,
        startY: event.clientY,
        card,
      };
      card.setPointerCapture(event.pointerId);
      card.style.transition = "none";
      card.style.cursor = "grabbing";
    });
    card.addEventListener("pointermove", (event) => {
      if (!drag) return;
      const dx = event.clientX - drag.startX;
      const dy = event.clientY - drag.startY;
      const rotate = dx / 18;
      drag.card.style.transform = `translate(${dx}px, ${dy}px) rotate(${rotate}deg)`;
    });
    card.addEventListener("pointerup", (event) => {
      if (!drag) return;
      const dx = event.clientX - drag.startX;
      const direction = dx > 90 ? "right" : dx < -90 ? "left" : null;
      drag.card.style.cursor = "grab";
      if (direction) {
        swipe(direction);
      } else {
        drag.card.style.transition = "transform 220ms ease";
        drag.card.style.transform = "";
      }
      drag = null;
    });
  }

  function swipe(direction) {
    const post = posts[index];
    const card = topCard();
    if (!post || !card) return;
    const exitX = direction === "right" ? 520 : -520;
    card.style.transition = "transform 260ms ease, opacity 260ms ease";
    card.style.transform = `translateX(${exitX}px) rotate(${direction === "right" ? 16 : -16}deg)`;
    card.style.opacity = "0";

    postForm("/api/swipe/", { post_id: post.id, direction })
      .then((result) => {
        index += 1;
        window.setTimeout(render, 150);
        if (result.matched) showMatch(result.chatUrl);
      })
      .catch(() => {
        card.style.transform = "";
        card.style.opacity = "1";
      });
  }

  document.querySelectorAll("[data-swipe-button]").forEach((button) => {
    button.addEventListener("click", () => swipe(button.dataset.swipeButton));
  });

  render();
}

function showMatch(chatUrl) {
  const modal = document.getElementById("match-modal");
  const link = document.getElementById("match-chat-link");
  if (!modal || !link) return;
  link.href = chatUrl;
  modal.hidden = false;
}

function initModal() {
  document.querySelectorAll("[data-close-modal]").forEach((button) => {
    button.addEventListener("click", () => {
      const modal = document.getElementById("match-modal");
      if (modal) modal.hidden = true;
    });
  });
}

function initCreatePreview() {
  const form = document.querySelector("[data-create-form]");
  if (!form) return;
  const title = document.getElementById("title");
  const startsAt = document.getElementById("starts_at");
  const location = document.getElementById("location");
  const expires = document.getElementById("expires_after");
  const expiresValue = document.getElementById("expires-value");
  const previewTitle = document.getElementById("preview-title");
  const previewMeta = document.getElementById("preview-meta");
  const previewType = document.getElementById("preview-type");
  const previewCard = document.getElementById("preview-card");
  const colors = {
    food: "#FFD95A",
    sports: "#FF4F93",
    study: "#12C6C1",
    explore: "#6C63FF",
    club: "#111827",
  };

  function selectedType() {
    return form.querySelector('input[name="activity_type"]:checked');
  }

  function update() {
    const selected = selectedType();
    const date = startsAt.value ? new Date(startsAt.value) : null;
    const time = date ? date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "Soon";
    previewTitle.textContent = title.value || "New Plus One";
    previewMeta.textContent = `${time} | ${location.value || "Campus"}`;
    previewType.textContent = selected ? selected.nextElementSibling.textContent : "Explore";
    expiresValue.textContent = `${expires.value} min`;
    const color = colors[selected ? selected.value : "explore"];
    previewCard.style.background = `linear-gradient(135deg, #12c6c1, ${color})`;
    form.querySelectorAll(".type-choice").forEach((label) => {
      label.classList.toggle("selected", label.querySelector("input").checked);
    });
  }

  form.addEventListener("input", update);
  form.addEventListener("change", update);
  update();
}

function appendBubble(list, sender, body) {
  const bubble = document.createElement("div");
  bubble.className = `bubble ${sender}`;
  bubble.textContent = body;
  list.appendChild(bubble);
  list.scrollTop = list.scrollHeight;
}

function initChat() {
  const screen = document.querySelector("[data-chat]");
  if (!screen) return;
  const matchId = screen.dataset.chat;
  const form = document.querySelector("[data-message-form]");
  const list = document.getElementById("message-list");
  const agree = document.querySelector("[data-agree-button]");
  const status = document.getElementById("agree-status");

  function send(body) {
    if (!body.trim()) return;
    postForm(`/api/chat/${matchId}/send/`, { body })
      .then((result) => {
        result.messages.forEach((message) => appendBubble(list, message.sender, message.body));
      });
  }

  if (form) {
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      const input = form.querySelector("input");
      send(input.value);
      input.value = "";
    });
  }

  document.querySelectorAll("[data-quick-reply]").forEach((button) => {
    button.addEventListener("click", () => send(button.dataset.quickReply));
  });

  if (agree) {
    agree.addEventListener("click", () => {
      postForm(`/api/match/${matchId}/agree/`, {})
      .then(() => {
        agree.textContent = "Meeting agreed";
        agree.disabled = true;
        status.textContent = "Both sides agreed. Names can unlock in the next implementation step.";
      });
    });
  }
}

document.addEventListener("DOMContentLoaded", () => {
  initCountdowns();
  initSwipeDeck();
  initModal();
  initCreatePreview();
  initChat();
});
