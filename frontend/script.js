// script.js - form handling, API calls and rendering for UCRP
"use strict";

const COUNTRIES = [
  "New Zealand", "Singapore", "United States", "Canada", "Japan", "South Korea", "Taiwan",
  "China", "United Kingdom", "Germany", "Netherlands", "France", "Sweden", "Switzerland", "Ireland",
];
const MAX_COUNTRIES = 3;
const TIER_ORDER = ["Highest", "Moderate", "Lowest", "Insufficient data"];
const CRITERIA_LABELS = {
  academic: "Academic", financial: "Financial", course: "Course",
  career: "Career", admission: "Admission", lifestyle: "Lifestyle",
};
const FIELD_LABELS = {
  university: "University", faculty: "Faculty", program_name: "Program", level: "Level",
  country: "Country", city: "City", duration_years: "Duration (years)",
  annual_tuition: "Annual tuition", tuition_currency: "Tuition currency",
  min_academic_percent: "Min. grade (%)", min_ielts: "Min. IELTS",
  application_deadline: "Deadline", keywords: "Keywords",
  career_outcomes: "Career outcomes", research_areas: "Research areas",
};

const $ = (sel) => document.querySelector(sel);

let currentAnalysisId = null;

/* ---------- helpers ---------- */

// Escape all text coming from the web/LLM before inserting it into HTML
function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (c) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
  ));
}

function safeUrl(url) {
  return /^https?:\/\//i.test(url || "") ? url : "";
}

function splitList(text) {
  return text.split(",").map((s) => s.trim()).filter(Boolean);
}

function numOrNull(id) {
  const v = $(id).value.trim();
  return v === "" ? null : Number(v);
}

function setStatus(message, isError = false) {
  const el = $("#status");
  el.textContent = message;
  el.classList.toggle("error", isError);
}

function scoreClass(score) {
  if (score === null || score === undefined) return "none";
  return score >= 70 ? "high" : score >= 50 ? "mid" : "low";
}

function formatValue(v) {
  if (Array.isArray(v)) return v.length ? v.join(", ") : "-";
  return v === null || v === undefined || v === "" ? "-" : v;
}

/* ---------- form setup ---------- */

function initCountries() {
  $("#countries").innerHTML = COUNTRIES.map((c) =>
    `<label><input type="checkbox" name="country" value="${esc(c)}" /> ${esc(c)}</label>`
  ).join("");

  $("#countries").addEventListener("change", () => {
    const checked = document.querySelectorAll('input[name="country"]:checked');
    document.querySelectorAll('input[name="country"]:not(:checked)').forEach((cb) => {
      cb.disabled = checked.length >= MAX_COUNTRIES;
    });
  });
}

function onModeChange() {
  const isInternational = $("#mode").value === "international";
  $("#countries-box").classList.toggle("hidden", !isInternational);
}

function buildProfile() {
  const mode = $("#mode").value;
  const countries = [...document.querySelectorAll('input[name="country"]:checked')].map((c) => c.value);
  return {
    mode,
    countries: mode === "international" ? countries : [],
    student_type: $("#student_type").value,
    level: $("#level").value,
    field_of_study: $("#field_of_study").value.trim(),
    interests: splitList($("#interests").value),
    academic_percent: numOrNull("#academic_percent"),
    ielts: numOrNull("#ielts"),
    budget_per_year: numOrNull("#budget_per_year"),
    currency: $("#currency").value,
    career_goal: $("#career_goal").value.trim(),
    preferred_locations: splitList($("#preferred_locations").value),
    max_results: Number($("#max_results").value),
  };
}

function validate(profile) {
  if (profile.field_of_study.length < 2) return "Please enter your field of study.";
  if (profile.mode === "international" && profile.countries.length === 0) return "Please choose at least one country.";
  return null;
}

/* ---------- API ---------- */

async function api(path, body, timeoutMs = 180000) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: controller.signal,
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      const detail = Array.isArray(data.detail) ? "Please check the form fields." : data.detail;
      throw new Error(detail || `Request failed (${res.status})`);
    }
    return data;
  } catch (err) {
    if (err.name === "AbortError") throw new Error("The request took too long. Please try again.");
    throw err;
  } finally {
    clearTimeout(timer);
  }
}

/* ---------- rendering ---------- */

function renderCriteria(criteria) {
  return Object.entries(criteria).map(([key, c]) => {
    const score = c.score;
    const width = score === null ? 0 : score;
    return `
      <div class="crit-row" title="${esc(c.note)}">
        <div class="crit-label">
          <span>${CRITERIA_LABELS[key] || esc(key)} (${c.weight}%)</span>
          <span>${score === null ? "n/a" : score}</span>
        </div>
        <div class="bar"><span style="width:${width}%"></span></div>
      </div>`;
  }).join("");
}

function renderList(title, items) {
  if (!items.length) return "";
  return `<div><h4>${title}</h4><ul>${items.map((i) => `<li>${esc(i)}</li>`).join("")}</ul></div>`;
}

function renderFields(fields) {
  const rows = Object.entries(FIELD_LABELS).map(([key, label]) => {
    const f = fields[key];
    if (!f) return "";
    return `<tr>
      <td>${label}</td>
      <td>${esc(formatValue(f.value))}</td>
      <td><span class="badge ${esc(f.status)}">${esc(f.status.replace("_", " "))}</span></td>
    </tr>`;
  }).join("");
  return `<details><summary>Data details and verification</summary>
    <table class="fields-table">${rows}</table></details>`;
}

function renderCard(r) {
  const url = safeUrl(r.source_url);
  const cost = r.annual_cost_aud ? `~AUD ${r.annual_cost_aud.toLocaleString()} / year (estimated)` : "Cost not available";
  const location = [r.city, r.country].filter(Boolean).join(", ");
  return `
  <article class="result-card" data-id="${esc(r.id)}">
    <div class="result-top">
      <div class="result-title">
        <h3>${esc(r.program_name)}</h3>
        <p>${esc(r.university)}${r.faculty ? " · " + esc(r.faculty) : ""}</p>
        <p>${esc(r.level || "")}${location ? " · " + esc(location) : ""} · ${esc(cost)}</p>
        <label class="select-compare">
          <input type="checkbox" class="compare-check" value="${esc(r.id)}" /> Compare
        </label>
      </div>
      <div class="score-circle ${scoreClass(r.overall)}" title="Overall compatibility">
        ${r.overall === null ? "No score" : r.overall}
      </div>
    </div>

    ${r.tags.length ? `<div class="tags">${r.tags.map((t) => `<span class="tag">${esc(t)}</span>`).join("")}</div>` : ""}

    <div class="criteria">${renderCriteria(r.criteria)}</div>

    <div class="two-col">
      ${renderList("Strengths", r.strengths)}
      ${renderList("Weaknesses", r.weaknesses)}
    </div>

    <div class="risks">
      <span class="risk ${esc(r.risks.financial)}">Financial risk: ${esc(r.risks.financial)}</span>
      <span class="risk ${esc(r.risks.admission)}">Admission risk: ${esc(r.risks.admission)}</span>
      <span class="risk ${esc(r.risks.data)}">Data risk: ${esc(r.risks.data)}</span>
      <span class="risk unknown">Verified fields: ${esc(r.verified_fields)}</span>
    </div>

    ${r.explanation ? `<div class="explanation">${esc(r.explanation)}</div>` : ""}
    ${renderFields(r.fields)}

    <p class="source">${r.official ? "Official source" : "Non-official source"}:
      ${url ? `<a href="${esc(url)}" target="_blank" rel="noopener noreferrer">${esc(url)}</a>` : "n/a"}</p>
  </article>`;
}

function renderResults(results) {
  const container = $("#results");
  if (!results.length) {
    container.innerHTML = `<div class="card">No matching programs found. Try different keywords.</div>`;
    return;
  }
  container.innerHTML = TIER_ORDER.map((tier) => {
    const items = results.filter((r) => r.tier === tier);
    if (!items.length) return "";
    const label = tier === "Insufficient data" ? tier : `${tier} compatibility`;
    return `<h3 class="tier-title ${tier.split(" ")[0]}">${label}</h3>${items.map(renderCard).join("")}`;
  }).join("");
  updateCompareButton();
}

function renderComparison(data) {
  const items = data.items;
  const head = `<tr><th></th>${items.map((i) => `<th>${esc(i.program_name)}<br><small>${esc(i.university)}</small></th>`).join("")}</tr>`;

  const rows = [
    ["Overall score", (i) => i.overall ?? "n/a"],
    ["Tier", (i) => i.tier],
    ["Tags", (i) => (i.tags.length ? i.tags.join(", ") : "-")],
    ["Faculty", (i) => i.faculty || "-"],
    ["Level", (i) => i.level || "-"],
    ["Location", (i) => [i.city, i.country].filter(Boolean).join(", ") || "-"],
    ["Yearly cost (AUD, est.)", (i) => (i.annual_cost_aud ? i.annual_cost_aud.toLocaleString() : "n/a")],
    ...Object.entries(CRITERIA_LABELS).map(([k, label]) => [label, (i) => i.criteria[k] ?? "n/a"]),
    ["Financial risk", (i) => i.risks.financial],
    ["Admission risk", (i) => i.risks.admission],
    ["Data risk", (i) => i.risks.data],
  ];

  const body = rows.map(([label, fn]) =>
    `<tr><td>${esc(label)}</td>${items.map((i) => `<td>${esc(fn(i))}</td>`).join("")}</tr>`
  ).join("");

  const links = `<tr><td>Source</td>${items.map((i) => {
    const u = safeUrl(i.source_url);
    return `<td>${u ? `<a href="${esc(u)}" target="_blank" rel="noopener noreferrer">Open</a>` : "n/a"}</td>`;
  }).join("")}</tr>`;

  $("#compare-table").innerHTML = `<table class="compare-table">${head}${body}${links}</table>`;
  $("#compare-section").classList.remove("hidden");
  $("#compare-section").scrollIntoView({ behavior: "smooth" });
}

/* ---------- compare selection ---------- */

function selectedIds() {
  return [...document.querySelectorAll(".compare-check:checked")].map((c) => c.value);
}

function updateCompareButton() {
  const n = selectedIds().length;
  const btn = $("#compare-btn");
  btn.textContent = `Compare selected (${n})`;
  btn.disabled = n < 2 || n > 4;
  // Limit selection to 4 programs
  document.querySelectorAll(".compare-check:not(:checked)").forEach((c) => { c.disabled = n >= 4; });
}

/* ---------- events ---------- */

async function onSubmit(event) {
  event.preventDefault();
  const profile = buildProfile();
  const error = validate(profile);
  if (error) return setStatus(error, true);

  const btn = $("#submit-btn");
  btn.disabled = true;
  setStatus("Researching official sources and scoring programs. This can take up to a minute...");
  $("#compare-section").classList.add("hidden");

  try {
    const data = await api("/api/analyze", profile);
    currentAnalysisId = data.analysis_id;
    renderResults(data.results);
    $("#results-section").classList.remove("hidden");
    setStatus(data.message || `Done. ${data.results.length} program(s) analyzed.`);
    $("#results-section").scrollIntoView({ behavior: "smooth" });
  } catch (err) {
    setStatus(err.message, true);
  } finally {
    btn.disabled = false;
  }
}

async function onCompare() {
  const ids = selectedIds();
  if (!currentAnalysisId || ids.length < 2) return;
  try {
    const data = await api("/api/compare", { analysis_id: currentAnalysisId, program_ids: ids });
    renderComparison(data);
  } catch (err) {
    setStatus(err.message, true);
  }
}

document.addEventListener("DOMContentLoaded", () => {
  initCountries();
  onModeChange();
  $("#mode").addEventListener("change", onModeChange);
  $("#profile-form").addEventListener("submit", onSubmit);
  $("#compare-btn").addEventListener("click", onCompare);
  $("#results").addEventListener("change", (e) => {
    if (e.target.classList.contains("compare-check")) updateCompareButton();
  });
});