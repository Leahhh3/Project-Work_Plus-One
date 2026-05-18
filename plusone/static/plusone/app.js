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

  previewTitle.textContent = titleInput?.value || "Your Plus One title";
  previewDescription.textContent = descriptionInput?.value || "The card preview updates as you edit the structured fields.";
  previewActivity.textContent = activityInput?.selectedOptions?.[0]?.textContent || "Other";
  previewLocation.textContent = locationInput?.selectedOptions?.[0]?.textContent || "Campus location";
  previewTime.textContent = startInput?.value || "Start time";
  previewExpire.textContent = expireInput?.value || "45";
}

document.addEventListener("DOMContentLoaded", () => {
  updateCountdowns();
  setInterval(updateCountdowns, 1000);
  updateCreatePreview();
  ["id_title", "id_description", "id_activity_type", "id_location", "id_start_time", "id_expire_minutes"].forEach((id) => {
    const field = document.getElementById(id);
    if (field) {
      field.addEventListener("input", updateCreatePreview);
      field.addEventListener("change", updateCreatePreview);
    }
  });
});
