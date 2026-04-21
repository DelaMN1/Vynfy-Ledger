function followRowLink(target) {
  if (target.closest("a, button, input, textarea, select, label, form")) {
    return;
  }
  const row = target.closest("[data-row-link]");
  if (!row) {
    return;
  }
  window.location.assign(row.dataset.rowLink);
}

document.addEventListener("click", (event) => {
  followRowLink(event.target);
});

document.addEventListener("keydown", (event) => {
  if (event.key !== "Enter" && event.key !== " ") {
    return;
  }
  const row = event.target.closest("[data-row-link]");
  if (!row) {
    return;
  }
  event.preventDefault();
  window.location.assign(row.dataset.rowLink);
});

function setPasswordVisibility(button, showPassword) {
  const inputId = button.dataset.passwordToggle;
  if (!inputId) {
    return;
  }
  const input = document.getElementById(inputId);
  if (!input) {
    return;
  }
  input.type = showPassword ? "text" : "password";
  button.setAttribute("aria-pressed", showPassword ? "true" : "false");
  button.setAttribute("aria-label", showPassword ? "Hide password" : "Show password");
  const showIcon = button.querySelector("[data-password-icon='show']");
  const hideIcon = button.querySelector("[data-password-icon='hide']");
  if (showIcon) {
    showIcon.hidden = showPassword;
  }
  if (hideIcon) {
    hideIcon.hidden = !showPassword;
  }
}

document.addEventListener("click", (event) => {
  const button = event.target.closest("[data-password-toggle]");
  if (!button) {
    return;
  }
  setPasswordVisibility(button, button.getAttribute("aria-pressed") != "true");
});
