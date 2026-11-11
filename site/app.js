"use strict";
// Plain JS + SVG. No libraries, no map tiles, no API keys, no network calls except this site's own files. Needs http (fetch), see README.
// All user-visible text lives in i18n/{en,de,ar}.json and is looked up with t()/tm(); this file contains no prose.
const ZONE_COLOR = {"50Hertz": "#0072B2", "Amprion": "#E69F00", "TenneT": "#009E73", "TransnetBW": "#CC79A7"};
const SVGNS = "http://www.w3.org/2000/svg";
const LANGS = {en: {label: "English", dir: "ltr", locale: "en-GB"}, ar: {label: "العربية", dir: "rtl", locale: "ar-u-nu-latn"}, de: {label: "Deutsch", dir: "ltr", locale: "de-DE"}};
const LINKS = {ccby: "https://creativecommons.org/licenses/by/4.0/", openmeteo: "https://open-meteo.com/", dlde: "https://www.govdata.de/dl-de/by-2-0",
  datenquellen: "https://sg.geodatenzentrum.de/web_public/gdz/datenquellen/datenquellen_vg_nuts.pdf", controlarea: "https://www.smard.de/page/en/wiki-article/5884/205642"};
const $ = id => document.getElementById(id);
const cache = {}, fcache = {}, msgs = {};
let M = null, lang = "en", loc = "en-GB", meta, fmeta = null, states, cur = null;  // cur = {state, zone, data, fdata, day, future}

/* ---------- translation helpers ---------- */
const esc = s => String(s).replace(/[&<>"]/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]));
const P = (text, dir) => ({t: String(text), h: `<bdi${dir ? ` dir="${dir}"` : ""}>${esc(text)}</bdi>`});   // parameter: plain text + isolated html
const L = text => P(text, "ltr");                                                                            // numbers, units, times: always left-to-right
const H = (html, text) => ({t: text, h: html});
const prm = v => (v && typeof v === "object") ? v : P(v);
function t(key, params = {}) {   // plain text (textContent, aria-label)
  if (!(key in M)) throw new Error("missing_key:" + key);
  return M[key].replace(/\*\*/g, "").replace(/\{(\w+)\}/g, (m, k) => k in params ? prm(params[k]).t : m);
}
function tm(key, params = {}) {  // html: **bold** and isolated parameters
  if (!(key in M)) throw new Error("missing_key:" + key);
  return esc(M[key]).replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>").replace(/\{(\w+)\}/g, (m, k) => k in params ? prm(params[k]).h : m);
}
const nfc = {}, pfc = {}, dfc = {};
const nf = (x, d = 0) => (nfc[lang + d] || (nfc[lang + d] = new Intl.NumberFormat(loc, {minimumFractionDigits: d, maximumFractionDigits: d}))).format(x);
const pf = (x, d = 0) => (pfc[lang + d] || (pfc[lang + d] = new Intl.NumberFormat(loc, {style: "percent", minimumFractionDigits: d, maximumFractionDigits: d}))).format(x / 100);
const dateF = () => dfc[lang + "d"] || (dfc[lang + "d"] = new Intl.DateTimeFormat(loc, {day: "numeric", month: "short", year: "numeric", timeZone: "UTC"}));
const dtF = () => dfc[lang + "dt"] || (dfc[lang + "dt"] = new Intl.DateTimeFormat(loc, {day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit", hourCycle: "h23", timeZone: "UTC"}));
const hrF = () => dfc[lang + "h"] || (dfc[lang + "h"] = new Intl.DateTimeFormat(loc, {hour: "2-digit", minute: "2-digit", hourCycle: "h23", timeZone: "UTC"}));
const fmtDate = iso => P(dateF().format(new Date(iso + "T12:00:00Z")));
const fmtDT = s => P(dtF().format(new Date(s.replace(" ", "T").replace(/Z?$/, "Z"))) + " UTC");   // "YYYY-MM-DD HH:MM" or "...THH:00Z" (UTC)
const fmtHour = h => hrF().format(new Date(Date.UTC(2000, 0, 1, h)));
const N = (x, d = 0) => L(nf(x, d)), MW = x => L(nf(x) + " MWh/h"), PCT = (x, d = 0) => L(pf(x, d));
const names = arr => new Intl.ListFormat(loc, {type: "conjunction"}).format(arr);
const stateName = p => t("state_" + p.id);

async function getJSON(url) { const r = await fetch(url); if (!r.ok) throw new Error(url + " -> HTTP " + r.status); return r.json(); }
async function loadMessages(l) { return msgs[l] || (msgs[l] = await getJSON(`i18n/${l}.json`)); }
function pickLang() {
  const q = new URLSearchParams(location.search).get("lang"); if (q in LANGS) return q;
  try { const s = localStorage.getItem("lang"); if (s in LANGS) return s; } catch (e) { /* storage may be blocked */ }
  for (const l of navigator.languages || [navigator.language]) { const c = String(l || "").slice(0, 2).toLowerCase(); if (c in LANGS) return c; }
  return "en";
}
function applyStatic() {
  document.documentElement.lang = lang; document.documentElement.dir = LANGS[lang].dir; document.title = t("page_title");
  document.querySelectorAll("[data-i18n]").forEach(e => { e.textContent = t(e.dataset.i18n); });
  document.querySelectorAll("[data-i18n-aria]").forEach(e => e.setAttribute("aria-label", t(e.dataset.i18nAria)));
  document.querySelectorAll("#langs button").forEach(b => b.setAttribute("aria-pressed", String(b.dataset.lang === lang)));
}
async function setLang(l, save = true) {
  try { M = await loadMessages(l); lang = l; } catch (e) { M = await loadMessages("en"); lang = "en"; }
  loc = LANGS[lang].locale; applyStatic();
  if (save) { try { localStorage.setItem("lang", lang); } catch (e) { /* ignore */ } const u = new URL(location.href); u.searchParams.set("lang", lang); history.replaceState(null, "", u); }
  if (states) { updateMapLabels(); renderIntro(); renderSnapshot(); renderLicences(); }
  if (cur && $("popup").open) { const d = $("date").value, h = $("hour").value; await openPopup(cur.state, d, h); }
}
function renderIntro() { if (meta) $("intro").innerHTML = tm("intro", {pastStart: fmtDate(meta.first_full_local_day), pastEnd: fmtDate(meta.last_full_local_day)}); }
function renderLicences() {
  const a = (url, text) => H(`<a href="${url}">${esc(text)}</a>`, text);
  const p = {smard: H("<strong>Bundesnetzagentur | SMARD.de</strong>", "Bundesnetzagentur | SMARD.de"), ccby: a(LINKS.ccby, "CC BY 4.0"), openmeteo: a(LINKS.openmeteo, "Weather data by Open-Meteo.com"),
    lightgbm: "LightGBM", dlde: a(LINKS.dlde, "dl-de/by-2-0"), datenquellen: a(LINKS.datenquellen, "Datenquellen"), controlarea: a(LINKS.controlarea, "SMARD Control area")};
  $("licBody").innerHTML = ["licences_load", "licences_weather", "licences_models", "licences_states", "licences_zones", "licences_notprod"].map(k => `<p>${tm(k, p)}</p>`).join("");
}

function el(name, attrs = {}, parent) { const e = document.createElementNS(SVGNS, name); for (const k in attrs) e.setAttribute(k, attrs[k]); if (parent) parent.appendChild(e); return e; }
async function zoneData(z) { return cache[z] || (cache[z] = await getJSON(`data/${z}.json`)); }
async function futureData(z) { if (!fmeta) return null; return fcache[z] || (fcache[z] = await getJSON(`data/future/${z}.json`)); }

/* ---------- map ---------- */
function project(lon, lat) { const k = Math.cos(51 * Math.PI / 180); return [(lon - 5.8) * k * 100, (55.1 - lat) * 100]; }
function pathOf(geom) {
  const polys = geom.type === "Polygon" ? [geom.coordinates] : geom.coordinates;
  return polys.map(p => p.map(ring => "M" + ring.map(c => project(c[0], c[1]).map(v => v.toFixed(1)).join(",")).join("L") + "Z").join("")).join("");
}
function highlightZone(zone) { $("map").classList.toggle("hovering", !!zone); document.querySelectorAll("#map path").forEach(p => p.classList.toggle("hl", !!zone && p.dataset.zone === zone)); }
function drawMap() {
  const svg = $("map"); const k = Math.cos(51 * Math.PI / 180);
  svg.setAttribute("viewBox", `-5 -5 ${(15.1 - 5.8) * k * 100 + 10} ${(55.1 - 47.2) * 100 + 10}`);
  for (const f of states.features) {   // one solid colour per state: its dominant zone
    const p = f.properties;
    const path = el("path", {d: pathOf(f.geometry), fill: ZONE_COLOR[p.zone], tabindex: 0, role: "button", "data-id": p.id, "data-zone": p.zone}, svg);
    path.addEventListener("mouseenter", () => highlightZone(p.zone));
    path.addEventListener("mousemove", e => showTip(e, p)); path.addEventListener("mouseleave", () => { hideTip(); highlightZone(null); });
    path.addEventListener("focus", () => { highlightZone(p.zone); const r = path.getBoundingClientRect(); showTip({clientX: r.left + r.width / 2, clientY: r.top + r.height / 2}, p); });
    path.addEventListener("blur", () => { hideTip(); highlightZone(null); });
    path.addEventListener("click", () => openPopup(p));
    path.addEventListener("keydown", e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); openPopup(p); } });
  }
  updateMapLabels();
}
function updateMapLabels() {
  for (const f of states.features) {
    const p = f.properties, path = document.querySelector(`#map path[data-id="${p.id}"]`);
    path.setAttribute("aria-label", p.split ? t("state_aria_split", {state: stateName(p), zone: p.zone, others: names(p.also_served_by)}) : t("state_aria", {state: stateName(p), zone: p.zone}));
  }
  $("legend").innerHTML = Object.entries(ZONE_COLOR).map(([z, c]) => `<li><i style="background:${c}"></i>${esc(z)}</li>`).join("");
}
function showTip(e, p) {
  const tip = $("tip"); tip.hidden = false;
  tip.textContent = t("tip", {state: stateName(p), zone: p.zone});
  const w = tip.offsetWidth || 240, x = LANGS[lang].dir === "rtl" ? e.clientX - 14 - w : e.clientX + 14;
  tip.style.left = Math.max(4, Math.min(x, innerWidth - w - 4)) + "px"; tip.style.top = (e.clientY + 14) + "px";
}
function hideTip() { $("tip").hidden = true; }

/* ---------- popup ---------- */
async function openPopup(p, date, hour) {
  hideTip(); const zone = p.zone;
  cur = {state: p, zone, data: await zoneData(zone), fdata: await futureData(zone), day: null, future: false};
  $("pTitle").textContent = stateName(p);
  $("zoneStmt").textContent = t("zone_stmt", {zone});
  const sp = $("splitStmt");
  if (p.split) { sp.hidden = false; sp.textContent = t("split_stmt", {state: stateName(p), zone, others: names(p.also_served_by)}); }
  else sp.hidden = true;
  const d = $("date"); d.min = meta.first_full_local_day; d.max = fmeta ? fmeta.covers_last_local_date : meta.last_full_local_day;
  const want = date || d.value || "2026-01-14"; d.value = (want < d.min) ? d.min : (want > d.max ? d.max : want);
  $("jumpPast").hidden = $("jumpFuture").hidden = !fmeta;
  const pop = $("popup"); if (!pop.open) pop.showModal();
  renderDay(hour);
  history.replaceState(null, "", `${location.search}#state=${p.id}&date=${$("date").value}&hour=${$("hour").value}`);
}
function hourLabel(day, i) {
  const h = day.h[i], dup = day.h.filter(x => x === h).length > 1, second = dup && day.h.indexOf(h) !== i;
  return fmtHour(h) + (dup ? " " + t(second ? "hour_second" : "hour_first") : "");
}
function setHash() { history.replaceState(null, "", `${location.search}#state=${cur.state.id}&date=${$("date").value}&hour=${$("hour").value}`); }
function renderDay(preferHour) {
  const date = $("date").value, past = cur.data.days[date], fut = cur.fdata ? cur.fdata.days[date] : null, day = past || fut || null; cur.day = day; cur.future = !past && !!fut;
  const sel = $("hour"); sel.innerHTML = "";
  const badge = $("badge"), info = $("dayInfo"), chart = $("chart"), table = $("hourTable");
  chart.innerHTML = ""; table.innerHTML = ""; $("fcNote").hidden = true; $("covStmt").hidden = true; $("backtestNote").hidden = !!fut && !past;
  $("popup").classList.toggle("is-future", cur.future); $("date").classList.toggle("unavailable", !day);
  document.querySelectorAll(".k-act-li").forEach(e => e.hidden = cur.future);
  if (!day) {
    badge.className = "badge"; badge.textContent = t("badge_none");
    const lastPast = meta.last_full_local_day, f0 = fmeta ? fmeta.covers_first_local_date : null;
    info.textContent = (date > lastPast && f0 && date < f0) ? t("nodata_gap", {lastPast: fmtDate(lastPast), firstFuture: fmtDate(f0)})
      : (fmeta && date > fmeta.covers_last_local_date) ? t("nodata_after", {lastFuture: fmtDate(fmeta.covers_last_local_date)}) : t("nodata_other");
    return;
  }
  const o = document.createElement("option"); o.value = "day"; o.textContent = t("full_day"); sel.appendChild(o);
  day.h.forEach((h, i) => { const op = document.createElement("option"); op.value = i; op.textContent = hourLabel(day, i); sel.appendChild(op); });
  sel.value = (preferHour !== undefined && [...sel.options].some(x => x.value === String(preferHour))) ? String(preferHour) : "day";
  if (cur.future) { renderFutureHeader(day, date); drawChart(day); renderHour(); return; }
  const nTest = day.s.reduce((a, b) => a + b, 0), n = day.s.length;
  if (nTest === n) { badge.className = "badge test"; badge.textContent = t("badge_test"); }
  else if (nTest === 0) { badge.className = "badge val"; badge.textContent = t("badge_val"); }
  else { badge.className = "badge val mixed"; badge.textContent = t("badge_mixed", {nVal: N(n - nTest), nTest: N(nTest)}); }
  const miss = expectedHours(date) - n;
  info.textContent = miss > 0 ? t("missing_hours", {n: N(miss)}) : "";
  const c = meta.test_coverage_cqr_by_zone[cur.zone], m = meta.test_coverage_cqr_mean; $("covStmt").hidden = false;
  $("covStmt").textContent = t("cov_stmt", {m80: PCT(m["80"], 1), m95: PCT(m["95"], 1), zone: cur.zone, z80: PCT(c["80"], 1), z95: PCT(c["95"], 1)});
  drawChart(day); renderHour();
}
function renderFutureHeader(day, date) {
  const badge = $("badge"), info = $("dayInfo"), ds = day.d, k = [...new Set(day.k)], dmin = Math.min(...ds), dmax = Math.max(...ds), outlook = dmax >= fmeta.outlook_first_day;
  badge.className = "badge fcst"; badge.textContent = t(outlook && dmin >= fmeta.outlook_first_day ? "badge_outlook" : "badge_future");
  const hz = dmin === dmax ? nf(dmin) : `${nf(dmin)}–${nf(dmax)}`;
  info.innerHTML = tm("future_info", {gen: fmtDT(fmeta.generated_utc), first: fmtDT(fmeta.covers_first_utc), last: fmtDT(fmeta.covers_last_utc), hz: L(hz), origin: fmtDT(fmeta.origin_utc)}) + (day.h.length < 24 ? esc(t("future_partial")) : "");
  const fc = $("fcNote"); fc.hidden = false;
  const cell = s => `<td>${s}</td>`, pc = x => pf(x, 1);
  const rows = k.map(kk => { const a = fmeta.accuracy[`${cur.zone}|${kk}`];
    return `<tr>${cell(esc(kk === 21 ? t("acc_model_outlook") : t("acc_model_day", {k: N(kk)})))}${cell(esc(t("cfg_" + a.config)))}` +
      `${cell(L(`${nf(a.val_mae)} / ${nf(a.val_baseline_mae)} (−${pf(a.val_gain_pct)})`).h)}` +
      `${cell(L(`${pc(a.val_cov80_swapped_mean)} / ${pc(a.val_cov95_swapped_mean)}`).h + " (" + esc(t("acc_worst", {a: L(pc(a.val_cov80_swapped_min)), b: L(pc(a.val_cov95_swapped_min))})) + ")")}` +
      `${cell(L(`${nf(a.test_mae)} / ${nf(a.test_baseline_mae)} (−${pf(a.test_gain_pct)})`).h)}${cell(L(`${pc(a.test_cov80)} / ${pc(a.test_cov95)}`).h)}</tr>`; }).join("");
  const a1 = fmeta.accuracy[`${cur.zone}|1`], Lh = fmeta.outlook_included ? 21 : 16, aL = fmeta.accuracy[`${cur.zone}|${Lh}`];
  const th = key => `<th>${esc(t(key))}</th>`;
  fc.innerHTML = `<p>${tm("acc_intro", {zone: cur.zone, a1: MW(a1.test_mae), aL: MW(aL.test_mae), L: N(Lh), b1: N(a1.test_baseline_mae), bL: N(aL.test_baseline_mae)})}</p>` +
    `<div class="tscroll"><table class="acc"><thead><tr>${th("acc_h_model")}${th("acc_h_inputs")}${th("acc_h_val")}${th("acc_h_valcov")}${th("acc_h_test")}${th("acc_h_testcov")}</tr></thead><tbody>${rows}</tbody></table></div>` +
    `<p class="warnline">${tm("acc_warn")}</p>` +
    `<p class="small">${esc(t("acc_weather", {v0: fmtDate(meta.val_start.slice(0, 10)), v1: fmtDate(meta.test_start.slice(0, 10))}))}</p>`;
}
function expectedHours(date) { // 24, or 23/25 on the Berlin DST change days
  const f = (y, m) => { const d = new Date(Date.UTC(y, m, 31)); d.setUTCDate(31 - d.getUTCDay()); return d.toISOString().slice(0, 10); };
  const y = +date.slice(0, 4); if (date === f(y, 2)) return 23; if (date === f(y, 9)) return 25; return 24;
}
function renderHour() {
  const day = cur.day, v = $("hour").value, tb = $("hourTable"); if (!day) return;
  const row = (th, td) => `<tr><th>${esc(th)}</th><td>${td}</td></tr>`, mean = a => a.reduce((x, y) => x + y, 0) / a.length, n = day.f.length;
  const sgn = x => (x > 0 ? "+" : "");
  const when = i => t("row_time_val", {date: fmtDate($("date").value), hour: L(hourLabel(day, i)), utc: fmtDT(day.t[i])});
  if (cur.future) {
    if (v === "day") tb.innerHTML = row(t("day_title", {n: N(n)}), "") + row(t("row_mean_forecast"), MW(mean(day.f)).h) + row(t("row_mean_range80"), L(`${nf(mean(day.l80))} – ${nf(mean(day.u80))} MWh/h`).h) + row(t("row_mean_range95"), L(`${nf(mean(day.l95))} – ${nf(mean(day.u95))} MWh/h`).h);
    else { const i = +v; tb.innerHTML = row(t("row_time"), esc(when(i))) + row(t("row_forecast"), MW(day.f[i]).h) + row(t("row_range80"), L(`${nf(day.l80[i])} – ${nf(day.u80[i])} MWh/h`).h) + row(t("row_range95"), L(`${nf(day.l95[i])} – ${nf(day.u95[i])} MWh/h`).h) +
      row(t("row_horizon"), esc(t("row_horizon_val", {d: N(day.d[i]), k: N(day.k[i])}))); }
    drawChart(day); setHash(); return;
  }
  if (v === "day") {
    const inr = (lo, hi) => day.a.filter((x, i) => x >= lo[i] && x <= hi[i]).length, mae = day.a.reduce((s, x, i) => s + Math.abs(day.f[i] - x), 0) / n;
    tb.innerHTML = row(t("day_title", {n: N(n)}), "") + row(t("row_mean_actual"), MW(mean(day.a)).h) + row(t("row_mean_forecast"), MW(mean(day.f)).h) +
      row(t("row_mae_day"), esc(t("row_mae_day_val", {mae: MW(mae), pct: PCT(100 * mae / mean(day.a), 1)}))) +
      row(t("row_in80"), esc(t("row_hours_of", {a: N(inr(day.l80, day.u80)), n: N(n)}))) + row(t("row_in95"), esc(t("row_hours_of", {a: N(inr(day.l95, day.u95)), n: N(n)})));
  } else {
    const i = +v, a = day.a[i], f = day.f[i], err = f - a, in80 = a >= day.l80[i] && a <= day.u80[i], in95 = a >= day.l95[i] && a <= day.u95[i];
    const flag = ok => ` <span class="${ok ? "in" : "out"}">${esc(t(ok ? "inside" : "outside"))}</span>`;
    tb.innerHTML = row(t("row_time"), esc(when(i))) + row(t("row_actual"), MW(a).h) + row(t("row_forecast"), MW(f).h) +
      row(t("row_error"), esc(t("row_error_val", {err: L(`${sgn(err)}${nf(err)} MWh/h`), pct: L(`${sgn(err)}${nf(100 * err / a, 1)}%`)}))) +
      row(t("row_range80"), L(`${nf(day.l80[i])} – ${nf(day.u80[i])} MWh/h`).h + flag(in80)) + row(t("row_range95"), L(`${nf(day.l95[i])} – ${nf(day.u95[i])} MWh/h`).h + flag(in95));
  }
  drawChart(day); setHash();
}
function drawChart(day) {
  const svg = $("chart"); svg.innerHTML = ""; const W = 680, H_ = 300, Lm = 62, R = 12, T = 12, B = 34, n = day.h.length;
  svg.setAttribute("viewBox", `0 0 ${W} ${H_}`);
  const fut = cur.future, all = [...(fut ? [] : day.a), ...day.l95, ...day.u95, ...day.f]; let lo = Math.min(...all), hi = Math.max(...all); const pad = (hi - lo) * .06; lo -= pad; hi += pad;
  const x = i => Lm + (W - Lm - R) * (n === 1 ? .5 : i / (n - 1)), y = v => T + (H_ - T - B) * (1 - (v - lo) / (hi - lo));
  for (let k = 0; k <= 4; k++) { const v = lo + (hi - lo) * k / 4, yy = y(v); el("line", {x1: Lm, x2: W - R, y1: yy, y2: yy, stroke: "currentColor", opacity: .15}, svg); const tx = el("text", {x: Lm - 6, y: yy + 4, "text-anchor": "end", "font-size": 11, fill: "currentColor", opacity: .7}, svg); tx.textContent = nf(v); }
  const yt = el("text", {x: 12, y: (T + H_ - B) / 2, "font-size": 11, fill: "currentColor", opacity: .7, transform: `rotate(-90 12 ${(T + H_ - B) / 2})`, "text-anchor": "middle"}, svg); yt.textContent = t("axis_y");
  day.h.forEach((h, i) => { if (n <= 25 && (i % 3 === 0 || i === n - 1)) { const tx = el("text", {x: x(i), y: H_ - 14, "text-anchor": "middle", "font-size": 11, fill: "currentColor", opacity: .7}, svg); tx.textContent = String(h).padStart(2, "0"); } });
  const xt = el("text", {x: (Lm + W - R) / 2, y: H_ - 1, "text-anchor": "middle", "font-size": 11, fill: "currentColor", opacity: .7}, svg); xt.textContent = t("axis_x");
  const fc = getComputedStyle(document.documentElement).getPropertyValue("--fc").trim() || "#d55e00", act = getComputedStyle(document.documentElement).getPropertyValue("--act").trim() || "#222";
  const defs = el("defs", {}, svg); const hp = el("pattern", {id: "fcHatch", width: 8, height: 8, patternUnits: "userSpaceOnUse", patternTransform: "rotate(45)"}, defs); el("line", {x1: 0, y1: 0, x2: 0, y2: 8, stroke: "currentColor", "stroke-width": 1, opacity: .12}, hp);
  const line = (a, col, w) => el("polyline", {points: a.map((v, i) => `${x(i)},${y(v)}`).join(" "), fill: "none", stroke: col, "stroke-width": w, "stroke-linejoin": "round"}, svg);
  const band = (lo_, hi_, op) => { const top = lo_.map((_, i) => `${x(i)},${y(hi_[i])}`), bot = lo_.map((_, i) => `${x(i)},${y(lo_[i])}`).reverse(); el("polygon", {points: top.concat(bot).join(" "), fill: fc, opacity: op}, svg); };
  band(day.l95, day.u95, .2); band(day.l80, day.u80, .35);
  if (fut) el("rect", {x: Lm, y: T, width: W - Lm - R, height: H_ - T - B, fill: "url(#fcHatch)", opacity: .5}, svg);
  const ln = line(day.f, fc, 2.2); if (fut) ln.setAttribute("stroke-dasharray", "7 4"); if (!fut) line(day.a, act, 2);
  if (fut) { const wm = el("text", {x: Lm + 10, y: T + 20, "font-size": 13, "font-weight": 700, fill: "currentColor", opacity: .55}, svg); wm.textContent = t("chart_watermark"); }
  const v = $("hour").value;
  if (v !== "day") { const i = +v; el("line", {x1: x(i), x2: x(i), y1: T, y2: H_ - B, stroke: "currentColor", "stroke-dasharray": "4 3", opacity: .6}, svg); if (!fut) el("circle", {cx: x(i), cy: y(day.a[i]), r: 4.5, fill: act}, svg); el("circle", {cx: x(i), cy: y(day.f[i]), r: 4.5, fill: fc}, svg); }
  const hit = el("rect", {x: Lm, y: T, width: W - Lm - R, height: H_ - T - B, fill: "transparent", style: "cursor:pointer"}, svg);
  hit.addEventListener("click", e => { const b = svg.getBoundingClientRect(), px = (e.clientX - b.left) / b.width * W; const i = Math.max(0, Math.min(n - 1, Math.round((px - Lm) / (W - Lm - R) * (n - 1)))); $("hour").value = String(i); renderHour(); });
}
function renderSnapshot() {
  if (!fmeta) return; const e = $("snapshot"); e.hidden = false;
  e.innerHTML = tm("snapshot", {gen: fmtDT(fmeta.generated_utc), first: fmtDT(fmeta.covers_first_utc), last: fmtDT(fmeta.covers_last_utc), d1: fmtDate(fmeta.covers_first_local_date), d2: fmtDate(fmeta.covers_last_local_date), origin: fmtDT(fmeta.origin_utc)});
}

/* ---------- start ---------- */
async function init() {
  const sw = $("langs");
  for (const [code, info] of Object.entries(LANGS)) {   // buttons are labelled in their own language
    const b = document.createElement("button"); b.type = "button"; b.dataset.lang = code; b.lang = code; b.textContent = info.label; b.addEventListener("click", () => setLang(code)); sw.appendChild(b);
  }
  try { await setLang(pickLang(), false); } catch (e) { $("loaderr").hidden = false; $("loaderr").textContent = e.message + "  →  python3 -m http.server -d site 8000"; return; }
  try { [meta, states] = await Promise.all([getJSON("data/meta.json"), getJSON("data/states.geojson")]); }
  catch (e) { const m = $("loaderr"); m.hidden = false; m.textContent = t("load_error", {err: e.message, cmd: "python3 -m http.server -d site 8000", url: "http://localhost:8000"}); return; }
  try { fmeta = await getJSON("data/future_meta.json"); } catch (e) { fmeta = null; }   // the future snapshot is optional
  drawMap(); renderIntro(); renderSnapshot(); renderLicences();
  $("licBtn").addEventListener("click", () => $("licDialog").showModal());
  $("date").addEventListener("change", () => { renderDay(); setHash(); });
  $("hour").addEventListener("change", renderHour);
  $("jumpPast").addEventListener("click", () => { $("date").value = meta.last_full_local_day; renderDay(); });
  $("jumpFuture").addEventListener("click", () => { $("date").value = fmeta.covers_first_local_date; renderDay(); });
  $("popup").addEventListener("close", () => history.replaceState(null, "", location.pathname + location.search));
  const h = new URLSearchParams(location.hash.slice(1)); const st = states.features.find(f => f.properties.id === h.get("state"));
  if (st) openPopup(st.properties, h.get("date") || undefined, h.get("hour") || undefined);
}
init();
