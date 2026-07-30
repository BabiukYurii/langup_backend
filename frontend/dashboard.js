"use strict";

// Dashboard: read-only progress overview. Everything here is computed from
// existing endpoints (no dedicated stats API) — vocabulary, review, quota, plan.
const $ = (id) => document.getElementById(id);

const MASTERY = ["NEW", "LEARNING", "REVIEW", "MASTERED"];

async function getJson(path) {
  const resp = await apiFetch(path);
  if (resp.status === 401) {
    location.href = "index.html";
    return null;
  }
  return resp.ok ? resp.json() : null;
}

function renderMastery(items) {
  const counts = { NEW: 0, LEARNING: 0, REVIEW: 0, MASTERED: 0 };
  for (const w of items) counts[w.mastery_level] = (counts[w.mastery_level] || 0) + 1;
  const total = items.length;

  $("mastery-empty").classList.toggle("hidden", total > 0);
  $("mastery-wrap").classList.toggle("hidden", total === 0);

  for (const level of MASTERY) {
    const key = level.toLowerCase();
    $("cnt-" + key).textContent = counts[level];
    const pct = total ? (counts[level] / total) * 100 : 0;
    $("seg-" + key).style.width = pct + "%";
  }
  $("stat-mastered").textContent = counts.MASTERED;
}

function renderPlan(sub) {
  const status = $("sub-status");
  const renew = $("sub-renew");
  if (!sub) {
    status.textContent = "Free";
    return;
  }
  const when = sub.current_period_end ? new Date(sub.current_period_end).toLocaleDateString() : null;
  if (sub.status === "TRIALING" && sub.is_active) {
    status.textContent = "Premium trial";
    if (when) {
      renew.textContent = `Trial ends on ${when}`;
      renew.classList.remove("hidden");
    }
  } else if (sub.is_active) {
    status.textContent = "Premium — active";
    if (when) {
      renew.textContent = sub.cancel_at_period_end ? `Ends on ${when}` : `Renews on ${when}`;
      renew.classList.remove("hidden");
    }
  } else {
    status.textContent = "Free";
  }
}

async function load() {
  // Fetch everything in parallel; each tile degrades to "—" on its own failure.
  const [vocab, due, quota, sub] = await Promise.all([
    getJson("/vocabulary?limit=1000"),
    getJson("/review/next?limit=100"),
    getJson("/exercises/quota"),
    getJson("/payments/subscription"),
  ]);

  if (vocab) {
    $("stat-total").textContent = vocab.total;
    renderMastery(vocab.items);
  }
  if (due) {
    // The endpoint caps at the limit; show 100+ if we hit it.
    $("stat-due").textContent = due.length >= 100 ? "100+" : due.length;
  }
  if (quota) {
    $("stat-gen").textContent = quota.unlimited ? `${quota.used} · ∞` : `${quota.used} / ${quota.limit}`;
  }
  renderPlan(sub);
}

document.addEventListener("DOMContentLoaded", () => {
  if (!TOKENS.access) {
    location.href = "index.html";
    return;
  }
  load();
});
