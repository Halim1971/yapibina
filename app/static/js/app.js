"use strict";

const desktopView = window.matchMedia("(min-width: 1024px)");

function savedView(key) {
  try {
    return window.localStorage.getItem(`yapibina-view-${key}`);
  } catch {
    return null;
  }
}

function storeView(key, view) {
  try {
    window.localStorage.setItem(`yapibina-view-${key}`, view);
  } catch {
    // The view still works when browser storage is unavailable.
  }
}

function applyView(toggle, requestedView) {
  const key = toggle.dataset.viewToggle;
  const list = document.querySelector(`[data-view-list="${key}"]`);
  if (!list) {
    return;
  }

  const view = desktopView.matches && requestedView === "rows" ? "rows" : "cards";
  list.dataset.view = view;
  toggle.querySelectorAll("[data-view-option]").forEach((button) => {
    const active = button.dataset.viewOption === view;
    button.classList.toggle("is-active", active);
    button.setAttribute("aria-pressed", String(active));
  });
}

document.querySelectorAll("[data-view-toggle]").forEach((toggle) => {
  const key = toggle.dataset.viewToggle;
  applyView(toggle, savedView(key));
  toggle.addEventListener("click", (event) => {
    const button = event.target.closest("[data-view-option]");
    if (!button || !desktopView.matches) {
      return;
    }
    storeView(key, button.dataset.viewOption);
    applyView(toggle, button.dataset.viewOption);
  });
});

desktopView.addEventListener("change", () => {
  document.querySelectorAll("[data-view-toggle]").forEach((toggle) => {
    applyView(toggle, savedView(toggle.dataset.viewToggle));
  });
});
