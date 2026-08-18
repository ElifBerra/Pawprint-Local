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
  const load = {
    weight: loadWeight,
    feeding: loadFeeding,
    stool: loadStool,
    vaccines: loadVaccines,
    records: loadRecords,
    insights: loadInsights,
    report: loadReport,
  }[state.section];
  if (load) load();
  if (state.section === "profile" && force) fillPetForm();
}

function fmt(key, values) {
  return Object.entries(values || {}).reduce(
    (text, [k, v]) => text.replace(`{${k}}`, v), T(key));
}

/* ---------- Header ---------- */

function renderPetLine() {
  const pet = state.pet;
  $("#pet-line").textContent = pet
    ? [pet.name, pet.breed, pet.age_text].filter(Boolean).join(" · ")
    : "—";
}

function renderReminder() {
  const button = $("#reminder");
  const badge = $("#vaccine-badge");
  const reminder = state.status && state.status.reminder;

  if (!reminder) {
    button.hidden = true;
    badge.hidden = true;
    return;
  }

  const overdue = reminder.status === "overdue";
  const days = Math.abs(reminder.days_until);
  button.hidden = false;
  button.classList.toggle("is-overdue", overdue);
  button.textContent = `💉 ${reminder.name.split("(")[0].trim()} · ` +
    fmt(overdue ? "vac.overdue" : "vac.due_soon", { days });
  button.onclick = () => goTo("vaccines");

  badge.hidden = !overdue;
  badge.textContent = "!";
}

/* ---------- Profile ---------- */

function fillPetForm() {
  const form = $("#pet-form");
  const pet = state.pet;
  if (!pet) return;
  for (const [key, value] of Object.entries(pet)) {
    const input = form.elements[key];
    if (!input || value === null || value === undefined) continue;
    input.value = key === "neutered" ? String(value) : value;
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
    neutered: data.neutered === "" ? null : data.neutered === "true",
  };
  try {
    state.pet = await api(`/api/pet?lang=${state.lang}`, {
      method: "PUT", body: JSON.stringify(body),
    });
    renderPetLine();
    renderSuggestions();
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

  let path = `/api/records/${kind}`;
  let body;

  if (kind === "weight") {
    body = { recorded_on: raw.recorded_on, weight_kg: Number(raw.weight_kg) };
  } else if (kind === "stool") {
    body = {
      recorded_on: raw.recorded_on,
      quality: raw.quality,
      frequency_per_day: raw.frequency_per_day
        ? Number(raw.frequency_per_day) : null,
    };
  } else if (kind === "vaccine") {
    path = "/api/vaccines";
    body = {
      given_on: raw.given_on,
      vaccine_key: raw.vaccine_key,
      vet_name: raw.vet_name || null,
      next_due_on: raw.next_due_on || null,
    };
  } else {
    body = {
      recorded_on: raw.recorded_on,
      grams: Number(raw.grams),
      meals_per_day: raw.meals_per_day ? Number(raw.meals_per_day) : null,
    };
    if (raw.food_id === "other") {
      // A number input still accepts "e" — it is valid scientific notation to
      // the browser. Number("E") is NaN, JSON turns NaN into null, and what
      // reached the database was a food with no energy density. The vet report
      // then asked for 26 kg of food a day.
      const numeric = (value, fallback = null) => {
        if (value === undefined || value === null || String(value).trim() === "") {
          return fallback;
        }
        const parsed = Number(String(value).replace(",", "."));
        return Number.isFinite(parsed) ? parsed : undefined;   // undefined = bad
      };

      const fields = {
        protein_pct: numeric(raw.nf_protein_pct),
        fat_pct: numeric(raw.nf_fat_pct),
        fibre_pct: numeric(raw.nf_fibre_pct, 0),
        moisture_pct: numeric(raw.nf_moisture_pct, 10),
        ash_pct: numeric(raw.nf_ash_pct, 0),
        pack_size_g: numeric(raw.nf_pack_size_g),
        kcal_per_100g: numeric(raw.nf_kcal_per_100g),
      };

      if (Object.values(fields).some((v) => v === undefined)) {
        toast(T("food.bad_number"));
        return;
      }
      if (!raw.nf_name || !raw.nf_name.trim()) {
        toast(T("food.need_name"));
        return;
      }
      if (fields.protein_pct === null || fields.fat_pct === null) {
        toast(T("food.need_macros"));
        return;
      }

      const total = fields.protein_pct + fields.fat_pct + fields.fibre_pct +
                    fields.moisture_pct + fields.ash_pct;
      if (total > 100) {
        toast(T("food.over_100"));
        return;
      }

      body.new_food = {
        name: raw.nf_name.trim(),
        species: (state.pet && state.pet.species) || "both",
        pack_size_g: fields.pack_size_g,
        kcal_per_100g: fields.kcal_per_100g || estimateKcal(fields),
        protein_pct: fields.protein_pct,
        fat_pct: fields.fat_pct,
        fibre_pct: fields.fibre_pct,
        moisture_pct: fields.moisture_pct,
        ash_pct: fields.ash_pct,
      };
    } else {
      body.food_id = Number(raw.food_id);
    }
  }

  // The same form both creates and updates; only the verb and the URL differ.
  const editing = state.editing && state.editing.kind === kind;
  const method = editing ? "PUT" : "POST";
  if (editing) path = `${ENDPOINT_FOR[kind]}/${state.editing.id}`;

  try {
    await api(path, { method, body: JSON.stringify(body) });
    state.editing = null;
    form.reset();
    setToday(form);
    markEditing(form, false);
    $("#new-food").hidden = true;
    toast(T(editing ? "toast.updated" : "toast.added"));
    await loadFoods();
    refreshSection();
    state.status = await api(`/api/status?lang=${state.lang}`);
    renderReminder();
  } catch (err) {
    toast(T("toast.error"));
    console.error(err);
  }
}

/* Atwater-style estimate, used only when the label omits the calorie figure —
   many bags do. Protein and carbohydrate ~3.5 kcal/g, fat ~8.5 kcal/g, with
   carbohydrate taken as whatever is left after the other fractions. */
function estimateKcal(f) {
  const carbs = Math.max(0, 100 - f.protein_pct - f.fat_pct - f.fibre_pct -
                            f.moisture_pct - f.ash_pct);
  return Math.round(f.protein_pct * 3.5 + f.fat_pct * 8.5 + carbs * 3.5);
}

function rowsHtml(rows, editable = null) {
  if (!rows.length) return `<p class="hint">—</p>`;
  return rows.map((row) => `
    <div class="record-row" ${row.id ? `data-id="${row.id}"` : ""}>
      <span class="record-date">${localDate(row.date)}</span>
      ${row.kind ? `<span class="record-kind">${row.kind}</span>` : ""}
      <span class="record-note">${row.note || ""}</span>
      <span class="record-value">${row.value}</span>
      ${editable && row.id ? `
        <span class="row-actions">
          <button class="icon-btn" data-act="edit" data-kind="${editable}"
                  data-id="${row.id}" title="${T("action.edit")}">✎</button>
          <button class="icon-btn danger" data-act="del" data-kind="${editable}"
                  data-id="${row.id}" title="${T("action.delete")}">🗑</button>
        </span>` : ""}
    </div>`).join("");
}

/* Wire the edit and delete buttons inside a list. */
function bindRowActions(container) {
  $$(".icon-btn", $(container)).forEach((button) => {
    button.onclick = (event) => {
      event.stopPropagation();
      const { act, kind, id } = button.dataset;
      if (act === "edit") startEdit(kind, Number(id));
      else deleteRecord(kind, Number(id));
    };
  });
}

/* ---------- Editing ---------- */

const FORM_FOR = {
  weight: 'form[data-record="weight"]',
  feeding: 'form[data-record="feeding"]',
  stool: 'form[data-record="stool"]',
  vaccine: 'form[data-record="vaccine"]',
};

const ENDPOINT_FOR = {
  weight: "/api/records/weight",
  feeding: "/api/records/feeding",
  stool: "/api/records/stool",
  vaccine: "/api/vaccines",
};

async function startEdit(kind, id) {
  const form = $(FORM_FOR[kind]);
  if (!form) return;

  let record;
  try {
    const data = kind === "vaccine"
      ? (await api(`/api/vaccines?lang=${state.lang}`)).records.find((r) => r.id === id)
      : (await api("/api/records"))[
          { weight: "weights", feeding: "feedings", stool: "stools" }[kind]
        ].find((r) => r.id === id);
    record = data;
  } catch {
    toast(T("toast.error"));
    return;
  }
  if (!record) return;

  if (kind === "weight") {
    form.elements.recorded_on.value = record.recorded_on;
    form.elements.weight_kg.value = record.weight_kg;
  } else if (kind === "stool") {
    form.elements.recorded_on.value = record.recorded_on;
    form.elements.quality.value = record.quality;
    form.elements.frequency_per_day.value = record.frequency_per_day ?? "";
  } else if (kind === "feeding") {
    form.elements.recorded_on.value = record.recorded_on;
    form.elements.grams.value = record.grams;
    form.elements.meals_per_day.value = record.meals_per_day ?? "";
    if (record.food_id) form.elements.food_id.value = String(record.food_id);
    $("#new-food").hidden = true;
  } else {
    form.elements.given_on.value = record.given_on;
    form.elements.vaccine_key.value = record.vaccine_key;
    form.elements.vet_name.value = record.vet_name ?? "";
    form.elements.next_due_on.value = record.next_due_on ?? "";
  }

  state.editing = { kind, id };
  markEditing(form, true);
  form.scrollIntoView({ behavior: "smooth", block: "center" });
}

function markEditing(form, on) {
  form.classList.toggle("is-editing", on);
  const submit = $("button.btn-primary", form);
  if (submit) submit.textContent = on ? T("action.update") : T("action.add");

  let cancel = $(".cancel-edit", form);
  if (on && !cancel) {
    cancel = document.createElement("button");
    cancel.type = "button";
    cancel.className = "btn btn-ghost cancel-edit";
    cancel.textContent = T("action.cancel");
    cancel.onclick = () => cancelEdit(form);
    $(".actions", form).prepend(cancel);
  } else if (!on && cancel) {
    cancel.remove();
  }
}

function cancelEdit(form) {
  state.editing = null;
  form.reset();
  setToday(form);
  markEditing(form, false);
  $("#new-food").hidden = true;
}

async function deleteRecord(kind, id) {
  if (!confirm(T("confirm.delete"))) return;
  try {
    await api(`${ENDPOINT_FOR[kind]}/${id}`, { method: "DELETE" });
    toast(T("toast.deleted"));
    if (state.editing && state.editing.id === id) {
      cancelEdit($(FORM_FOR[kind]));
    }
    refreshSection();
    state.status = await api(`/api/status?lang=${state.lang}`);
    renderReminder();
  } catch (err) {
    toast(T("toast.error"));
    console.error(err);
  }
}

async function fetchRecords() {
  try {
    return await api("/api/records");
  } catch {
    return null;
  }
}

async function loadWeight() {
  const data = await fetchRecords();
  if (!data) return;
  const rows = [...data.weights].reverse().map((r) => ({
    id: r.id, date: r.recorded_on, value: `${num(r.weight_kg)} kg`,
  }));
  $("#weight-list").innerHTML = rowsHtml(rows, "weight");
  bindRowActions("#weight-list");

  const points = data.weights.slice(-12).map((r) => ({
    recorded_on: r.recorded_on, weight_kg: r.weight_kg,
  }));
  drawChart(points, state.pet && state.pet.target_weight_kg, "#weight-chart");
}

async function loadStool() {
  const data = await fetchRecords();
  if (!data) return;
  const rows = [...data.stools].reverse().map((r) => ({
    id: r.id, date: r.recorded_on,
    value: T(`stool.${r.quality}`),
    note: r.frequency_per_day ? `${num(r.frequency_per_day)} / ${state.lang === "tr" ? "gün" : "day"}` : "",
  }));
  $("#stool-list").innerHTML = rowsHtml(rows, "stool");
  bindRowActions("#stool-list");
}

async function loadRecords() {
  const data = await fetchRecords();
  if (!data) return;

  const rows = [];
  data.weights.forEach((r) => rows.push({
    date: r.recorded_on, kind: T("nav.weight"), value: `${num(r.weight_kg)} kg`,
  }));
  data.feedings.forEach((r) => rows.push({
    date: r.recorded_on, kind: T("nav.feeding"),
    value: `${num(r.grams, 0)} g`, note: r.food_brand || "",
  }));
  data.stools.forEach((r) => rows.push({
    date: r.recorded_on, kind: T("nav.stool"), value: T(`stool.${r.quality}`),
  }));

  try {
    const vac = await api(`/api/vaccines?lang=${state.lang}`);
    vac.records.forEach((r) => rows.push({
      date: r.given_on, kind: T("nav.vaccines"),
      value: r.name.split("(")[0].trim(), note: r.vet_name || "",
    }));
  } catch { /* vaccines are optional here */ }

  rows.sort((a, b) => b.date.localeCompare(a.date));
  $("#records-list").innerHTML = rowsHtml(rows.slice(0, 40));
}

function setToday(root = document) {
  const today = new Date().toISOString().slice(0, 10);
  $$('input[type="date"][name="recorded_on"], input[type="date"][name="given_on"]',
     root).forEach((input) => {
    // The API rejects future dates; stop them at the picker so the user gets
    // a constraint rather than an error.
    input.max = today;
    if (!input.value) input.value = today;
  });
}

/* ---------- Foods and feeding ---------- */

async function loadFoods() {
  const select = $("#food-select");
  if (!select) return;

  let foods = [];
  try {
    foods = (await api("/api/foods")).foods;
  } catch { /* fall through to the Other option */ }

  state.foods = foods;
  const options = foods.map((f) => {
    const flag = f.is_sample ? ` (${T("food.sample")})` : "";
    const pack = f.pack_size_g ? ` · ${num(f.pack_size_g, 0)} g` : "";
    return `<option value="${f.id}">${escapeHtml(f.name)}${pack}${flag}</option>`;
  });
  options.push(`<option value="other">${T("food.other")}</option>`);
  select.innerHTML = options.join("");

  select.onchange = () => {
    const other = select.value === "other";
    $("#new-food").hidden = !other;
    $$("#new-food input").forEach((i) => {
      if (i.name === "nf_name") i.required = other;
    });
  };

  if (!foods.length) {
    select.value = "other";
    select.onchange();
  }
}

async function loadFeeding() {
  await loadFoods();

  const data = await fetchRecords();
  if (data) {
    const rows = [...data.feedings].reverse();
    $("#feeding-list").innerHTML = rows.length ? rows.map((r) => `
      <div class="record-row is-clickable" data-record-id="${r.id}">
        <span class="record-date">${localDate(r.recorded_on)}</span>
        <span class="record-note">${escapeHtml([r.food_brand, r.meals_per_day
          ? `${r.meals_per_day} ${state.lang === "tr" ? "öğün" : "meals"}` : ""]
          .filter(Boolean).join(" · "))}</span>
        <span class="record-value">${num(r.grams, 0)} g</span>
        <span class="row-actions">
          <button class="icon-btn" data-act="edit" data-kind="feeding"
                  data-id="${r.id}" title="${T("action.edit")}">✎</button>
          <button class="icon-btn danger" data-act="del" data-kind="feeding"
                  data-id="${r.id}" title="${T("action.delete")}">🗑</button>
        </span>
      </div>
      <div class="record-detail" id="detail-${r.id}" hidden></div>`).join("")
      : `<p class="hint">—</p>`;

    $$("#feeding-list .record-row").forEach((row) => {
      row.onclick = () => toggleRecord(Number(row.dataset.recordId), row);
    });
    bindRowActions("#feeding-list");
  }

  await loadNutrition();
}

/* Clicking a feeding row opens that record on its own — what that amount of
   that food delivers, and per meal if the number of meals was recorded. */
async function toggleRecord(id, row) {
  const box = $(`#detail-${id}`);
  if (!box) return;

  if (!box.hidden) {
    box.hidden = true;
    row.classList.remove("is-open");
    return;
  }

  $$(".record-detail").forEach((d) => (d.hidden = true));
  $$("#feeding-list .record-row").forEach((r) => r.classList.remove("is-open"));

  let data;
  try {
    data = await api(`/api/nutrition/record/${id}`);
  } catch {
    box.innerHTML = `<p class="hint">${T("nut.no_food")}</p>`;
    box.hidden = false;
    return;
  }

  const s = data.served;
  const line = (label, value) =>
    `<div class="nut-row"><span class="label">${label}</span>` +
    `<span class="value">${value}</span></div>`;

  const delta = (value, unit) => {
    if (value === undefined || Math.abs(value) < 0.5) return "";
    const cls = value > 0 ? "delta-over" : "delta-under";
    const word = value > 0 ? T("nut.over") : T("nut.under");
    return ` &nbsp;<span class="${cls}">${Math.abs(value).toFixed(0)} ${unit} ${word}</span>`;
  };
  const d = data.deltas || {};

  box.innerHTML = `
    <div class="nut-rows">
      ${line(escapeHtml(data.food.name) + (data.food.is_sample
        ? `<span class="sample-flag">${T("food.sample")}</span>` : ""),
        `${data.food.kcal_per_100g} kcal/100 g`)}
      ${line(T("nut.energy"), `${s.kcal.toFixed(0)} kcal${delta(d.kcal, "kcal")}`)}
      ${line(T("nut.protein"), `${s.protein_g.toFixed(1)} g · ${s.protein_dm_pct}% DM${delta(d.protein_g, "g")}`)}
      ${line(T("nut.fat"), `${s.fat_g.toFixed(1)} g · ${s.fat_dm_pct}% DM${delta(d.fat_g, "g")}`)}
      ${data.per_meal ? line(T("nut.per_meal"),
        `${data.per_meal.grams.toFixed(0)} g · ${data.per_meal.kcal.toFixed(0)} kcal · ${data.per_meal.protein_g.toFixed(1)} g protein`) : ""}
    </div>
    ${!data.meets_protein_minimum
      ? `<p class="hint" style="color:var(--danger)">${T("nut.below_protein")}</p>` : ""}`;

  box.hidden = false;
  row.classList.add("is-open");
}

function ring(percent, value, label, sub, colour) {
  const radius = 32, circumference = 2 * Math.PI * radius;
  const filled = Math.min(percent, 150) / 100 * circumference;
  return `
    <div class="ring">
      <svg viewBox="0 0 84 84">
        <circle class="ring-track" cx="42" cy="42" r="${radius}"></circle>
        <circle class="ring-fill" cx="42" cy="42" r="${radius}"
                stroke="${colour}"
                stroke-dasharray="${filled} ${circumference}"></circle>
        <text class="ring-value" x="42" y="42">${value}</text>
      </svg>
      <div class="ring-label">${label}</div>
      <div class="ring-sub">${sub}</div>
    </div>`;
}

async function loadNutrition() {
  const box = $("#nutrition-body");
  if (!box) return;

  const period = state.period || "day";
  $$("#period-switch .seg").forEach((b) =>
    b.classList.toggle("is-active", b.dataset.period === period));

  let data;
  try {
    data = await api(`/api/nutrition?period=${period}`);
  } catch {
    box.innerHTML = "";
    return;
  }

  if (!data.available) {
    box.innerHTML = `<p class="hint">${
      T(data.reason === "no_weight" ? "nut.no_weight" : "nut.no_food")}</p>`;
    return;
  }

  if (period !== "day") return renderPeriod(box, data);

  const { energy, food, served, required, deltas } = data;
  const pct = (a, b) => (b ? Math.round(a / b * 100) : 0);

  const energyPct = pct(served.kcal, energy.mer_kcal);
  const proteinPct = pct(served.protein_g, required.protein_g);
  const fatPct = pct(served.fat_g, required.fat_g);
  const gramsPct = pct(served.grams, required.food_grams);

  const colour = (p, floorIsMinimum) => {
    if (floorIsMinimum) return p >= 100 ? "var(--success)" : "var(--danger)";
    if (p > 110) return "var(--warning)";
    if (p < 90) return "var(--accent)";
    return "var(--success)";
  };

  const deltaText = (value, unit) => {
    if (Math.abs(value) < 0.5) return `<span class="delta-ok">✓</span>`;
    const cls = value > 0 ? "delta-over" : "delta-under";
    const word = value > 0 ? T("nut.over") : T("nut.under");
    return `<span class="${cls}">${Math.abs(value).toFixed(0)} ${unit} ${word}</span>`;
  };

  const bagDays = food.pack_size_g && served.grams
    ? Math.floor(food.pack_size_g / served.grams) : null;

  box.innerHTML = `
    <div class="rings">
      ${ring(energyPct, `${energyPct}%`, T("nut.energy"),
             `${served.kcal.toFixed(0)} / ${energy.mer_kcal} kcal`,
             colour(energyPct))}
      ${ring(gramsPct, `${served.grams.toFixed(0)}g`, T("nut.amount"),
             `${T("nut.need")} ${required.food_grams.toFixed(0)} g`,
             colour(gramsPct))}
      ${ring(proteinPct, `${served.protein_g.toFixed(0)}g`, T("nut.protein"),
             `${T("nut.minimum")} ${required.protein_g.toFixed(0)} g`,
             colour(proteinPct, true))}
      ${ring(fatPct, `${served.fat_g.toFixed(0)}g`, T("nut.fat"),
             `${T("nut.minimum")} ${required.fat_g.toFixed(0)} g`,
             colour(fatPct, true))}
    </div>

    <div class="nut-rows">
      <div class="nut-row">
        <span class="label">${escapeHtml(food.name)}${
          food.is_sample ? `<span class="sample-flag">${T("food.sample")}</span>` : ""}</span>
        <span class="value">${food.kcal_per_100g} kcal/100 g</span>
      </div>
      <div class="nut-row">
        <span class="label">${T("nut.energy")}</span>
        <span class="value">${served.kcal.toFixed(0)} / ${energy.mer_kcal} kcal &nbsp; ${deltaText(deltas.kcal, "kcal")}</span>
      </div>
      <div class="nut-row">
        <span class="label">${T("nut.protein")}</span>
        <span class="value">${served.protein_g.toFixed(0)} g · ${served.protein_dm_pct}% DM &nbsp; ${deltaText(deltas.protein_g, "g")}</span>
      </div>
      <div class="nut-row">
        <span class="label">${T("nut.fat")}</span>
        <span class="value">${served.fat_g.toFixed(0)} g · ${served.fat_dm_pct}% DM &nbsp; ${deltaText(deltas.fat_g, "g")}</span>
      </div>
      ${bagDays ? `<div class="nut-row">
        <span class="label">${T("food.pack")}</span>
        <span class="value">${fmt("nut.bag_lasts", { days: bagDays })}</span>
      </div>` : ""}
    </div>

    <p class="hint">
      ${fmt("nut.formula", { rer: energy.rer_kcal, factor: energy.factor,
                             mer: energy.mer_kcal })} —
      ${fmt(energy.basis === "target" ? "nut.basis_target" : "nut.basis_current",
            { kg: energy.weight_kg })}
    </p>
    <p class="hint">${T("nut.minimums_note").replace(/\*\*(.+?)\*\*/g, "<b>$1</b>")}</p>`;
}

/* Weekly and monthly: the same daily requirement, against the average of the
   period. Records say "from this date, this amount", so the days between two
   records are filled with the earlier one — nobody logs an identical row every
   morning. */
function renderPeriod(box, data) {
  const { energy, average, total, deltas, series, covered_days, days } = data;
  const need = energy.mer_kcal;
  const pct = Math.round(average.kcal / need * 100);

  const bars = series.map((d) => {
    if (d.kcal === null) {
      return `<div class="spark-bar empty" title="${d.date}"></div>`;
    }
    const height = Math.min(d.kcal / (need * 1.6), 1) * 100;
    const over = d.kcal > need * 1.1;
    return `<div class="spark-bar ${over ? "over" : ""}"
                 style="height:${Math.max(height, 4)}%"
                 title="${d.date}: ${d.kcal.toFixed(0)} kcal"></div>`;
  }).join("");

  const deltaText = Math.abs(deltas.kcal) < 1
    ? `<span class="delta-ok">✓</span>`
    : `<span class="${deltas.kcal > 0 ? "delta-over" : "delta-under"}">` +
      `${Math.abs(deltas.kcal).toFixed(0)} kcal ` +
      `${deltas.kcal > 0 ? T("nut.over") : T("nut.under")}</span>`;

  const line = (label, value) =>
    `<div class="nut-row"><span class="label">${label}</span>` +
    `<span class="value">${value}</span></div>`;

  box.innerHTML = `
    <div class="spark">${bars}</div>
    <div class="nut-rows">
      ${line(T("nut.avg_daily"), `${average.kcal.toFixed(0)} / ${need} kcal &nbsp; ${deltaText}`)}
      ${line(T("nut.avg_amount"), `${average.grams.toFixed(0)} g`)}
      ${line(T("nut.avg_protein"), `${average.protein_g.toFixed(0)} g`)}
      ${line(T("nut.total"), `${total.kcal.toLocaleString()} kcal · ${(total.grams / 1000).toFixed(1)} kg`)}
      ${line(T("nut.foods_used"), escapeHtml((data.foods || []).join(", ") || "—"))}
    </div>
    <p class="hint">${fmt("nut.coverage", { covered: covered_days, days })}</p>`;
}

/* ---------- Vaccines ---------- */

async function loadVaccines() {
  let data;
  try {
    data = await api(`/api/vaccines?lang=${state.lang}`);
  } catch {
    return;
  }

  $("#vaccine-select").innerHTML = data.catalogue.map((v) =>
    `<option value="${v.key}">${escapeHtml(v.name)}</option>`).join("");

  $("#vaccine-due").innerHTML = data.due.map((d) => {
    const days = d.days_until;
    let when = T("vac.unknown"), cls = "ok";
    if (d.status === "overdue") {
      when = fmt("vac.overdue", { days: Math.abs(days) }); cls = "overdue";
    } else if (d.status === "due_soon") {
      when = fmt("vac.due_soon", { days }); cls = "soon";
    } else if (d.status === "scheduled") {
      when = fmt("vac.scheduled", { days }); cls = "ok";
    }

    const history = d.doses_given
      ? fmt("vac.last", { date: localDate(d.last_given) })
      : T("vac.never");

    return `
      <div class="due due-${d.status}">
        <div class="due-body">
          <div class="due-name">
            ${escapeHtml(d.name)}
            ${d.core ? `<span class="core-tag">${T("vac.core")}</span>` : ""}
          </div>
          <div class="due-meta">${history} · ${escapeHtml(d.reason)}</div>
        </div>
        <div class="due-when">
          <div class="due-date">${d.due_on ? localDate(d.due_on) : "—"}</div>
          <div class="due-days ${cls}">${when}</div>
        </div>
      </div>`;
  }).join("");

  const rows = data.records.map((r) => ({
    id: r.id,
    date: r.given_on,
    value: r.name.split("(")[0].trim(),
    note: [r.vet_name, r.batch].filter(Boolean).join(" · "),
  }));
  $("#vaccine-list").innerHTML = rows.length
    ? rowsHtml(rows, "vaccine") : `<p class="hint">${T("vac.empty")}</p>`;
  bindRowActions("#vaccine-list");
}

/* ---------- Ask ---------- */

function renderSuggestions() {
  const box = $("#suggestions");
  if (!box) return;
  box.innerHTML = suggestions(state.pet)
    .map((q) => `<button class="chip">${escapeHtml(q)}</button>`).join("");
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
        if (event.type === "retrieved") {
          // Retrieval is done long before the first word arrives. Show what
          // was found straight away, so the wait is filled by the system
          // visibly working rather than an empty bubble.
          bubble.innerHTML =
            `<span class="typing"><i></i><i></i><i></i></span>` +
            metaHtml({
              sources: event.sources,
              used_pet_record: event.used_pet_record,
              retrieved: event.retrieved,
              latency_s: null,
            });
          $("#chat").scrollTop = $("#chat").scrollHeight;
        } else if (event.type === "token") {
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

  let html = `<div class="meta">${tags.join("")}${
    done.latency_s === null ? "" : `<span>${done.latency_s}s</span>`}</div>`;

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
function drawChart(points, target, selector = "#chart") {
  const host = $(selector);
  if (!host) return;
  if (!points || points.length < 2) {
    host.innerHTML = `<p class="hint">${T("ins.nodata")}</p>`;
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

  host.innerHTML = `
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
      ${n.grams !== null ? row(L.portion, `${num(n.grams, 0)} g${
        n.served_kcal ? ` · ${num(n.served_kcal, 0)} kcal` : ""}`) : ""}
      ${n.daily_kcal_need ? row(L.energy_need, `${num(n.daily_kcal_need, 0)} kcal${
        n.recommended_grams ? ` · ${num(n.recommended_grams, 0)} g` : ""}`) : ""}
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
  $$("#period-switch .seg").forEach((b) => b.onclick = () => {
    state.period = b.dataset.period;
    loadNutrition();
  });

  setToday();
  applyLanguage();

  try {
    state.status = await api(`/api/status?lang=${state.lang}`);
    state.pet = state.status.pet;
    renderPetLine();
    fillPetForm();
    renderSuggestions();   // needs the pet, so it runs again once loaded
    renderReminder();
    if (!state.pet) toast(T("toast.nopet"));
  } catch (err) {
    toast(T("toast.error"));
    console.error(err);
  }

  // Load the models in the background so the first question is not the slow one.
  fetch("/api/warmup", { method: "POST" }).catch(() => {});
}

init();
