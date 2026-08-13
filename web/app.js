/* Pawprint-Local — interface logic.
   No framework and no bundler: the whole point is that this runs from a folder
   with the network switched off. */

const state = {
  lang: localStorage.getItem("pawprint.lang") || "tr",
  section: "profile",
  pet: null,
  status: null,
  busy: false,
};

const $  = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
const T  = (key) => t(key, state.lang);

/* ---------- Small helpers ---------- */

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || response.statusText);
  }
  return response.status === 204 ? null : response.json();
}

let toastTimer;
function toast(message) {
  const el = $("#toast");
  el.textContent = message;
  el.classList.add("is-visible");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove("is-visible"), 2600);
}

const num = (value, digits = 1) =>
  value === null || value === undefined ? "—" : Number(value).toFixed(digits);

function localDate(iso) {
  if (!iso) return "—";
  const locale = state.lang === "tr" ? "tr-TR" : "en-GB";
  return new Date(iso).toLocaleDateString(locale, {
    day: "2-digit", month: "short", year: "numeric",
  });
}

/* ---------- Language ---------- */

function applyLanguage() {
  document.documentElement.lang = state.lang;

  $$("[data-i18n]").forEach((el) => {
    el.textContent = T(el.dataset.i18n);
  });
  $$("[data-i18n-placeholder]").forEach((el) => {
    el.placeholder = T(el.dataset.i18nPlaceholder);
  });
  $$(".lang-btn").forEach((btn) => {
    btn.classList.toggle("is-active", btn.dataset.lang === state.lang);
  });

  $("#page-title").textContent = T(`nav.${state.section}`);
  $("#lang-note").textContent = T("ask.lang_note");
  $("#pdf-link").href = `/api/report.pdf?lang=${state.lang}`;

  renderSuggestions();
}

function setLanguage(lang) {
  state.lang = lang;
  localStorage.setItem("pawprint.lang", lang);
  applyLanguage();
  refreshSection(true);
}

/* ---------- Navigation ---------- */

function goTo(section) {
  state.section = section;
  $$(".nav-item").forEach((b) =>
    b.classList.toggle("is-active", b.dataset.section === section));
  $$(".section").forEach((s) =>
    s.classList.toggle("is-active", s.id === `section-${section}`));
  $("#page-title").textContent = T(`nav.${section}`);
  refreshSection();
}

function refreshSection(force = false) {
  if (state.section === "records") loadRecords();
  if (state.section === "insights") loadInsights();
  if (state.section === "report") loadReport();
  if (state.section === "profile" && force) fillPetForm();
}

/* ---------- Header ---------- */

function renderPetLine() {
  const pet = state.pet;
  $("#pet-line").textContent = pet
    ? [pet.name, pet.breed, pet.age_text].filter(Boolean).join(" · ")
    : "—";
}

/* ---------- Profile ---------- */

function fillPetForm() {
  const form = $("#pet-form");
  const pet = state.pet;
  if (!pet) return;
  for (const [key, value] of Object.entries(pet)) {
    const input = form.elements[key];
    if (input && value !== null && value !== undefined) input.value = value;
  }
}

async function savePet(event) {
  event.preventDefault();
  const data = Object.fromEntries(new FormData(event.target));
  const body = {
    id: state.pet ? state.pet.id : null,
    name: data.name,
    species: data.species,
    breed: data.breed || null,
    birth_date: data.birth_date || null,
    sex: data.sex || null,
    target_weight_kg: data.target_weight_kg ? Number(data.target_weight_kg) : null,
    owner_name: data.owner_name || null,
  };
  try {
    state.pet = await api(`/api/pet?lang=${state.lang}`, {
      method: "PUT", body: JSON.stringify(body),
    });
    renderPetLine();
    toast(T("toast.saved"));
  } catch (err) {
    toast(T("toast.error"));
    console.error(err);
  }
}

/* ---------- Records ---------- */

async function addRecord(event) {
  event.preventDefault();
  const form = event.target;
  const kind = form.dataset.record;
  const raw = Object.fromEntries(new FormData(form));

  const body = { recorded_on: raw.recorded_on };
  if (kind === "weight") {
    body.weight_kg = Number(raw.weight_kg);
  } else if (kind === "feeding") {
    body.food_brand = raw.food_brand;
    body.portion_cups = Number(raw.portion_cups);
    body.meals_per_day = raw.meals_per_day ? Number(raw.meals_per_day) : null;
  } else {
    body.quality = raw.quality;
    body.frequency_per_day = raw.frequency_per_day
      ? Number(raw.frequency_per_day) : null;
  }

  try {
    await api(`/api/records/${kind}`, { method: "POST", body: JSON.stringify(body) });
    form.reset();
    setToday(form);
    toast(T("toast.added"));
    loadRecords();
  } catch (err) {
    toast(T("toast.error"));
    console.error(err);
  }
}

async function loadRecords() {
  let data;
  try {
    data = await api("/api/records");
  } catch {
    return;
  }

  const rows = [];
  data.weights.forEach((r) => rows.push({
    date: r.recorded_on, kind: T("rec.weight"),
    value: `${num(r.weight_kg)} kg`, note: "",
  }));
  data.feedings.forEach((r) => rows.push({
    date: r.recorded_on, kind: T("rec.feeding"),
    value: `${num(r.portion_cups)} ${state.lang === "tr" ? "bardak" : "cups"}`,
    note: r.recommended_cups
      ? `${r.food_brand} · ${state.lang === "tr" ? "önerilen" : "guideline"} ${num(r.recommended_cups)}`
      : r.food_brand,
  }));
  data.stools.slice(-10).forEach((r) => rows.push({
    date: r.recorded_on, kind: T("rec.stool"),
    value: T(`stool.${r.quality}`), note: "",
  }));

  rows.sort((a, b) => b.date.localeCompare(a.date));

  $("#records-list").innerHTML = rows.slice(0, 24).map((row) => `
    <div class="record-row">
      <span class="record-date">${localDate(row.date)}</span>
      <span class="record-kind">${row.kind}</span>
      <span class="record-note">${row.note}</span>
      <span class="record-value">${row.value}</span>
    </div>`).join("");
}

function setToday(root = document) {
  const today = new Date().toISOString().slice(0, 10);
  $$('input[type="date"][name="recorded_on"]', root).forEach((input) => {
    if (!input.value) input.value = today;
  });
}

/* ---------- Ask ---------- */

function renderSuggestions() {
  const box = $("#suggestions");
  if (!box) return;
  box.innerHTML = (SUGGESTIONS[state.lang] || SUGGESTIONS.en)
    .map((q) => `<button class="chip">${q}</button>`).join("");
  $$(".chip", box).forEach((chip) => {
    chip.onclick = () => { $("#question").value = chip.textContent; askQuestion(); };
  });
}

function addMessage(role, html) {
  $("#chat-empty")?.remove();
  const wrap = document.createElement("div");
  wrap.className = `msg msg-${role}`;
  wrap.innerHTML = `
    <div class="avatar">${role === "user" ? "🙂" : "🐾"}</div>
    <div class="bubble">${html}</div>`;
  $("#chat").append(wrap);
  $("#chat").scrollTop = $("#chat").scrollHeight;
  return $(".bubble", wrap);
}

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

async function askQuestion(event) {
  if (event) event.preventDefault();
  const input = $("#question");
  const question = input.value.trim();
  if (!question || state.busy) return;

  state.busy = true;
  $("#ask-btn").disabled = true;
  input.value = "";

  addMessage("user", escapeHtml(question));
  const bubble = addMessage("bot",
    `<span class="typing"><i></i><i></i><i></i></span>`);

  try {
    const response = await fetch("/api/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, lang: state.lang }),
    });

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "", answer = "", done = null;

    while (true) {
      const { value, done: finished } = await reader.read();
      if (finished) break;
      buffer += decoder.decode(value, { stream: true });

      const lines = buffer.split("\n");
      buffer = lines.pop();

      for (const line of lines) {
        if (!line.trim()) continue;
        const event = JSON.parse(line);
        if (event.type === "token") {
          answer += event.text;
          bubble.innerHTML = escapeHtml(answer);
          $("#chat").scrollTop = $("#chat").scrollHeight;
        } else if (event.type === "done") {
          done = event;
        } else if (event.type === "error") {
          bubble.innerHTML = `<em>${escapeHtml(event.message)}</em>`;
        }
      }
    }

    if (done) bubble.innerHTML = escapeHtml(done.text || answer) + metaHtml(done);
  } catch (err) {
    bubble.innerHTML = `<em>${T("toast.error")}</em>`;
    console.error(err);
  } finally {
    state.busy = false;
    $("#ask-btn").disabled = false;
    $("#chat").scrollTop = $("#chat").scrollHeight;
  }
}

function metaHtml(done) {
  const tags = [];
  if (done.used_pet_record) {
    tags.push(`<span class="tag tag-record">🐾 ${T("ask.records_used")}</span>`);
  }
  done.sources.forEach((s) => tags.push(`<span class="tag">${s}</span>`));
  if (!done.sources.length && !done.used_pet_record) {
    tags.push(`<span class="tag">${T("ask.no_match")}</span>`);
  }

  let html = `<div class="meta">${tags.join("")}<span>${done.latency_s}s</span></div>`;

  if (done.retrieved && done.retrieved.length) {
    html += `<details class="passages"><summary>${T("ask.passages")}</summary>` +
      done.retrieved.map((r) => `
        <div class="passage">
          <b>${r.source}</b> · chunk ${r.chunk_index} · ${r.score}<br>
          ${escapeHtml(r.content)}
        </div>`).join("") +
      `</details>`;
  }
  return html;
}

/* ---------- Insights ---------- */

async function loadInsights() {
  let data;
  try {
    data = await api(`/api/insights?lang=${state.lang}`);
  } catch {
    return;
  }

  const s = data.summary;
  const change = s.weight_change_kg;
  const changeClass = change > 0 ? "up" : change < 0 ? "down" : "flat";
  const arrow = change > 0 ? "▲" : change < 0 ? "▼" : "—";

  let targetNote = T("ins.ontarget");
  if (s.over_target_kg > 0) targetNote = `${num(s.over_target_kg)} kg ${T("ins.over")}`;
  else if (s.over_target_kg < 0) targetNote = `${num(Math.abs(s.over_target_kg))} kg ${T("ins.under")}`;

  $("#metrics").innerHTML = `
    <div class="metric">
      <div class="metric-value">${num(s.current_weight_kg)}</div>
      <div class="metric-label">${T("ins.current")}</div>
      <div class="metric-delta ${changeClass}">
        ${change === null ? T("ins.nodata")
          : `${arrow} ${change > 0 ? "+" : ""}${num(change)} kg · ${s.weight_change_weeks} ${T("ins.weeks")}`}
      </div>
    </div>
    <div class="metric">
      <div class="metric-value">${num(s.target_weight_kg)}</div>
      <div class="metric-label">${T("ins.target")}</div>
      <div class="metric-delta ${s.over_target_kg > 0 ? "up" : "down"}">${targetNote}</div>
    </div>
    <div class="metric">
      <div class="metric-value">${s.stool_normal_pct === null ? "—" : `%${s.stool_normal_pct}`}</div>
      <div class="metric-label">${T("ins.stool")}</div>
      <div class="metric-delta ${s.stool_normal_pct >= 90 ? "down" : "up"}">
        ${s.stool_normal_pct === null ? T("ins.nodata") : `✓ ${T("ins.normal")}`}
      </div>
    </div>`;

  drawChart(data.weights, s.target_weight_kg);

  $("#insight-list").innerHTML = data.insights.map((i) => `
    <div class="insight insight-${i.level}">
      <span class="pill pill-${i.level}">${T(`level.${i.level}`)}</span>
      <div class="insight-body">
        <div class="insight-title">${i.title}</div>
        <div class="insight-detail">${i.detail}</div>
      </div>
    </div>`).join("") || `<p class="insight-detail">${T("ins.nodata")}</p>`;
}

/* Inline SVG rather than a charting library: one dependency fewer, and no CDN
   for something that has to work offline. */
function drawChart(points, target) {
  if (!points || points.length < 2) {
    $("#chart").innerHTML = `<p class="insight-detail">${T("ins.nodata")}</p>`;
    return;
  }

  const W = 720, H = 240, padX = 34, padTop = 18, padBottom = 30;
  const values = points.map((p) => p.weight_kg);
  const lo = Math.min(...values, target || Infinity) - 0.5;
  const hi = Math.max(...values, target || -Infinity) + 0.5;
  const span = hi - lo || 1;

  const plotH = H - padTop - padBottom;
  const y = (v) => padTop + plotH - ((v - lo) / span) * plotH;
  const slot = (W - padX * 2) / points.length;
  const barW = Math.min(slot * 0.56, 34);

  const bars = points.map((p, i) => {
    const cx = padX + slot * i + slot / 2;
    const top = y(p.weight_kg);
    const last = i === points.length - 1;
    return `
      <rect class="bar ${last ? "bar-last" : ""}" rx="4"
            x="${cx - barW / 2}" y="${top}"
            width="${barW}" height="${Math.max(H - padBottom - top, 2)}">
        <title>${p.recorded_on}: ${p.weight_kg} kg</title>
      </rect>
      <text class="axis" x="${cx}" y="${H - 10}" text-anchor="middle">
        ${p.recorded_on.slice(5).replace("-", "/")}
      </text>`;
  }).join("");

  const targetLine = target ? `
    <line class="target-line" x1="${padX}" x2="${W - padX}"
          y1="${y(target)}" y2="${y(target)}"></line>
    <text class="target-label" x="${W - padX}" y="${y(target) - 5}"
          text-anchor="end">${T("ins.target")} ${target}</text>` : "";

  $("#chart").innerHTML = `
    <svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="xMidYMid meet">
      ${targetLine}${bars}
    </svg>`;
}

/* ---------- Report ---------- */

async function loadReport() {
  let data;
  try {
    data = await api(`/api/report?lang=${state.lang}`);
  } catch {
    return;
  }

  const L = data.labels;
  const row = (label, value) =>
    `<div class="report-row"><span>${label}</span><span>${value}</span></div>`;

  const p = data.patient, w = data.weight, n = data.nutrition;
  const cups = state.lang === "tr" ? "bardak" : "cups";

  let html = `
    <div class="report-block">
      <h3>${L.patient}</h3>
      ${row(L.name, p.name)}
      ${row(L.species_breed, p.species_breed)}
      ${row(L.age, p.age)}
      ${row(L.sex, p.sex)}
      ${row(L.owner, p.owner)}
    </div>

    <div class="report-block">
      <h3>${L.weight}</h3>
      ${row(L.target, `${num(w.target_kg)} kg`)}
      ${row(L.current, `${num(w.current_kg)} kg${w.over_pct !== null
        ? ` (${w.over_pct > 0 ? "+" : ""}${num(w.over_pct)}%)` : ""}`)}
      ${row(L.measured, localDate(w.measured_on))}
      ${w.change_kg !== null
        ? row(L.change, `${w.change_kg > 0 ? "+" : ""}${num(w.change_kg)} kg`) : ""}
    </div>

    <div class="report-block">
      <h3>${L.nutrition}</h3>
      ${row(L.food, n.brand || "—")}
      ${row(L.portion, `${num(n.portion_cups)} ${cups}${n.recommended_cups
        ? ` (${L.recommended}: ${num(n.recommended_cups)})` : ""}`)}
      ${n.meals_per_day ? row(L.meals, n.meals_per_day) : ""}
      ${n.last_change_on
        ? row(L.last_change, `${localDate(n.last_change_on)} · ${n.last_change_to}`) : ""}
    </div>`;

  if (data.digestion.stool_normal_pct !== null) {
    html += `
      <div class="report-block">
        <h3>${L.digestion}</h3>
        ${row(L.stool_normal, `%${data.digestion.stool_normal_pct}`)}
      </div>`;
  }

  if (data.assessment.length) {
    html += `<div class="report-block"><h3>${L.assessment}</h3>` +
      data.assessment.map((a) => `<div class="report-note">${a.detail}</div>`).join("") +
      `</div>`;
  }

  if (data.recommendations.length) {
    html += `<div class="report-block"><h3>${L.recommendations}</h3><ol class="report-list">` +
      data.recommendations.map((r) => `<li>${r.detail}</li>`).join("") +
      `</ol></div>`;
  }

  html += `<p class="report-foot">${L.footer}<br>${L.generated}: ${localDate(data.generated_on)}</p>`;

  $("#report-body").innerHTML = html;
}

/* ---------- Start ---------- */

async function init() {
  $$(".nav-item").forEach((b) => b.onclick = () => goTo(b.dataset.section));
  $$(".lang-btn").forEach((b) => b.onclick = () => setLanguage(b.dataset.lang));
  $("#pet-form").onsubmit = savePet;
  $$('form[data-record]').forEach((f) => f.onsubmit = addRecord);
  $("#ask-form").onsubmit = askQuestion;

  setToday();
  applyLanguage();

  try {
    state.status = await api(`/api/status?lang=${state.lang}`);
    state.pet = state.status.pet;
    renderPetLine();
    fillPetForm();
    if (!state.pet) toast(T("toast.nopet"));
  } catch (err) {
    toast(T("toast.error"));
    console.error(err);
  }

  // Load the models in the background so the first question is not the slow one.
  fetch("/api/warmup", { method: "POST" }).catch(() => {});
}

init();
