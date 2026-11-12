"use strict";
// Plain JS + SVG. No libraries, no map tiles, no API keys, no network calls except this site's own files. Needs http (fetch), see README.
// All user-visible text lives in i18n/{en,de,ar}.json and is looked up with t()/tm(); this file contains no prose.
const ZONE_COLOR = {"50Hertz": "#0072B2", "Amprion": "#E69F00", "TenneT": "#009E73", "TransnetBW": "#CC79A7"};
const SVGNS = "http://www.w3.org/2000/svg";
const LANGS = {en: {label: "English", dir: "ltr", locale: "en-GB"}, ar: {label: "العربية", dir: "rtl", locale: "ar-u-nu-latn"}, de: {label: "Deutsch", dir: "ltr", locale: "de-DE"}};
const REPO = "https://github.com/n10man/German-Electrical-power-forecast", METHODS = REPO + "/blob/main/docs/METHODS.md";
const LINKS = {ccby: "https://creativecommons.org/licenses/by/4.0/", openmeteo: "https://open-meteo.com/", dlde: "https://www.govdata.de/dl-de/by-2-0",
  datenquellen: "https://sg.geodatenzentrum.de/web_public/gdz/datenquellen/datenquellen_vg_nuts.pdf", controlarea: "https://www.smard.de/page/en/wiki-article/5884/205642"};
const $ = id => document.getElementById(id);
const cache = {}, fcache = {}, msgs = {};
let M = null, lang = "en", loc = "en-GB", meta, fmeta = null, states, cur = null, lastFocus = null;  // cur = {state, zone, data, fdata, day, future}
const bandPref = {past: null, future: null};   // the "show usual range" choice, kept for this browser session only
try { for (const k of ["past", "future"]) { const v = sessionStorage.getItem("bands_" + k); if (v !== null) bandPref[k] = v === "1"; } } catch (e) { /* storage may be blocked */ }

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
function applyMeta() {   // page title / description / social tags follow the language; the image and url become absolute once SITE_CONFIG.baseUrl is set
  const base = ((window.SITE_CONFIG && window.SITE_CONFIG.baseUrl) || "").replace(/\/+$/, "");
  const set = (sel, attr, v) => { const e = document.querySelector(sel); if (e) e.setAttribute(attr, v); };
  set('meta[name="description"]', "content", t("meta_description")); set('meta[property="og:title"]', "content", t("page_title")); set('meta[name="twitter:title"]', "content", t("page_title"));
  set('meta[property="og:description"]', "content", t("meta_description")); set('meta[name="twitter:description"]', "content", t("meta_description"));
  set('meta[property="og:locale"]', "content", {en: "en_GB", de: "de_DE", ar: "ar_AR"}[lang]);
  if (base) { set('meta[property="og:image"]', "content", base + "/preview.jpg"); set('meta[name="twitter:image"]', "content", base + "/preview.jpg"); set('meta[property="og:url"]', "content", base + "/"); }
}
function applyStatic() {
  document.documentElement.lang = lang; document.documentElement.dir = LANGS[lang].dir; document.title = t("page_title"); applyMeta();
  document.querySelectorAll("[data-i18n]").forEach(e => { e.textContent = t(e.dataset.i18n); });
  document.querySelectorAll("[data-i18n-aria]").forEach(e => e.setAttribute("aria-label", t(e.dataset.i18nAria)));
  document.querySelectorAll("[data-i18n-title]").forEach(e => e.setAttribute("title", t(e.dataset.i18nTitle)));
  document.querySelectorAll("#langs button").forEach(b => b.setAttribute("aria-pressed", String(b.dataset.lang === lang)));
}
async function setLang(l, save = true) {
  try { M = await loadMessages(l); lang = l; } catch (e) { M = await loadMessages("en"); lang = "en"; }
  loc = LANGS[lang].locale; applyStatic();
  if (save) { try { localStorage.setItem("lang", lang); } catch (e) { /* ignore */ } const u = new URL(location.href); u.searchParams.set("lang", lang); history.replaceState(null, "", u); }
  if (states) { updateMapLabels(); renderIntro(); renderSnapshot(); renderLicences(); renderEnded(); }
  if (cur && $("popup").open) { const d = $("date").value, h = $("hour").value; await openPopup(cur.state, d, h); }
  else if (cur) updateTodayButton();
}
function renderIntro() { if (meta) $("intro").innerHTML = tm("intro", {pastStart: fmtDate(meta.first_full_local_day), pastEnd: fmtDate(meta.last_full_local_day)}); }
function renderLicences() {
  const a = (url, text) => H(`<a href="${url}">${esc(text)}</a>`, text);
  const p = {smard: H("<strong>Bundesnetzagentur | SMARD.de</strong>", "Bundesnetzagentur | SMARD.de"), ccby: a(LINKS.ccby, "CC BY 4.0"), openmeteo: a(LINKS.openmeteo, "Weather data by Open-Meteo.com"),
    lightgbm: "LightGBM", repo: a(REPO, t("link_repo")), methods: a(METHODS, t("link_methods")), dlde: a(LINKS.dlde, "dl-de/by-2-0"), datenquellen: a(LINKS.datenquellen, "Datenquellen"), controlarea: a(LINKS.controlarea, "SMARD Control area")};
  $("licBody").innerHTML = ["licences_load", "licences_weather", "licences_models", "licences_states", "licences_zones", "licences_notprod", "licences_intervals", "licences_code", "privacy_line"].map(k => `<p>${tm(k, p)}</p>`).join("");
  if (fmeta) $("licBody").insertAdjacentHTML("beforeend", `<h3>${esc(t("snapshot_heading"))}</h3><p>${tm("snapshot", snapParams())}</p>`);
}

function el(name, attrs = {}, parent) { const e = document.createElementNS(SVGNS, name); for (const k in attrs) e.setAttribute(k, attrs[k]); if (parent) parent.appendChild(e); return e; }
async function zoneData(z) { return cache[z] || (cache[z] = await getJSON(`data/${z}.json`)); }
async function futureData(z) { if (!fmeta) return null; return fcache[z] || (fcache[z] = await getJSON(`data/future/${z}.json`)); }

function showLoadError(key, e) {   // friendly, translated; the technical detail stays in the console
  console.error(e); const m = $("loaderr"); m.hidden = false;
  m.textContent = t(key, {err: String(e && e.message || e), cmd: "python3 -m http.server -d site 8000", url: "http://localhost:8000"}); m.scrollIntoView({block: "nearest"});
}
/* ---------- map ---------- */
function project(lon, lat) { const k = Math.cos(51 * Math.PI / 180); return [(lon - 5.8) * k * 100, (55.1 - lat) * 100]; }
function pathOf(geom) {
  const polys = geom.type === "Polygon" ? [geom.coordinates] : geom.coordinates;
  return polys.map(p => p.map(ring => "M" + ring.map(c => project(c[0], c[1]).map(v => v.toFixed(1)).join(",")).join("L") + "Z").join("")).join("");
}
function highlightZone(zone) { $("map").classList.toggle("hovering", !!zone); document.querySelectorAll("#map path").forEach(p => p.classList.toggle("hl", !!zone && p.dataset.zone === zone)); }
/* ---------- input method: "keyboard" only after Tab / arrows / Enter / Space, back to "pointer" on any pointer use. A focused state shows its highlight only in keyboard mode. ---------- */
const root = document.documentElement; root.dataset.input = "pointer";
const KEYS = ["Tab", "ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight", "Enter", " "];
function setInput(mode) {
  if (root.dataset.input === mode) return; root.dataset.input = mode;
  if (mode === "pointer") { const a = document.activeElement; if (a && a.matches && a.matches("#map>path")) { clearHover(); highlightZone(null); hideTip(); } }   // a focused state shows nothing in pointer mode
}
addEventListener("keydown", e => { if (KEYS.includes(e.key) && !e.metaKey && !e.ctrlKey && !e.altKey) setInput("keyboard"); }, true);
for (const ev of ["pointerdown", "pointermove"]) addEventListener(ev, () => setInput("pointer"), true);
const keyboardMode = () => root.dataset.input === "keyboard";
/* ---------- hovered-state layer: a lighter, outlined, slightly enlarged copy of the hovered state, drawn above all states and ignored by the pointer ---------- */
const canHover = () => matchMedia("(hover: hover)").matches, reducedMotion = () => matchMedia("(prefers-reduced-motion: reduce)").matches;
const mixWhite = (hex, w) => "#" + [1, 3, 5].map(i => Math.round(parseInt(hex.slice(i, i + 2), 16) * (1 - w) + 255 * w).toString(16).padStart(2, "0")).join("");
function hoverScale(bb) {   // about 1.25 for large states, up to 1.45 for very small ones (Berlin, Hamburg, Bremen), from the size of the bounding box (map units)
  const size = Math.max(bb.width, bb.height), t = Math.min(1, Math.max(0, (size - 35) / (90 - 35))); return 1.45 - (1.45 - 1.25) * t;
}
function hoverFit(svg, bb, s) {   // keep the enlarged copy (plus outline and shadow) fully inside the viewBox: shrink if it cannot fit, otherwise slide it inwards
  const vb = svg.viewBox.baseVal, m = 9 * vb.width / (svg.getBoundingClientRect().width || vb.width);   // about 9 screen pixels for outline and shadow, in map units
  s = Math.min(s, (vb.width - 2 * m) / bb.width, (vb.height - 2 * m) / bb.height);
  const cx = bb.x + bb.width / 2, cy = bb.y + bb.height / 2, hw = bb.width * s / 2 + m, hh = bb.height * s / 2 + m;
  const dx = Math.max(0, vb.x - (cx - hw)) - Math.max(0, (cx + hw) - (vb.x + vb.width)), dy = Math.max(0, vb.y - (cy - hh)) - Math.max(0, (cy + hh) - (vb.y + vb.height));
  return {s, dx, dy};
}
function setupHoverLayer(svg) {
  const defs = el("defs", {}, svg), f = el("filter", {id: "hvShadow", x: "-30%", y: "-30%", width: "160%", height: "160%"}, defs);
  el("feGaussianBlur", {in: "SourceAlpha", stdDeviation: "2.2", result: "b"}, f); el("feOffset", {in: "b", dx: "0", dy: "2", result: "o"}, f);
  el("feComponentTransfer", {in: "o", result: "s"}, f).appendChild(el("feFuncA", {type: "linear", slope: "0.45"}));
  const m = el("feMerge", {}, f); el("feMergeNode", {in: "s"}, m); el("feMergeNode", {in: "SourceGraphic"}, m);
  el("g", {id: "hoverLayer", "pointer-events": "none", "aria-hidden": "true"}, svg);
}
function clearHover() { const g = $("hoverLayer"); if (g) while (g.firstChild) g.removeChild(g.firstChild); }   // no replaceChildren: older Safari lacks it
function showHover(path, zone, scaleOn = true) {
  const layer = $("hoverLayer"); if (!layer) return; clearHover();
  const g = el("g", {class: "hv", filter: "url(#hvShadow)"}, layer), d = path.getAttribute("d"), cp = el("clipPath", {id: "hvClip"}, g); el("path", {d}, cp);
  el("path", {d, fill: mixWhite(ZONE_COLOR[zone], 0.35), stroke: "#111", "stroke-width": 2.5, "stroke-linejoin": "round", "vector-effect": "non-scaling-stroke"}, g);   // dark outline
  el("path", {d, fill: "none", stroke: "#fff", "stroke-width": 2, "vector-effect": "non-scaling-stroke", "clip-path": "url(#hvClip)"}, g);                                  // thin white inner edge
  g.style.transform = "scale(1)";
  if (scaleOn && canHover() && !reducedMotion()) { const bb = path.getBBox(), f = hoverFit($("map"), bb, hoverScale(bb)); g.getBoundingClientRect(); g.style.transform = `translate(${f.dx.toFixed(2)}px, ${f.dy.toFixed(2)}px) scale(${f.s.toFixed(3)})`; }   // the transition (style.css) animates the zoom about the centre of the bounding box
}
function drawMap() {
  const svg = $("map"); const k = Math.cos(51 * Math.PI / 180);
  svg.setAttribute("viewBox", `-5 -5 ${(15.1 - 5.8) * k * 100 + 10} ${(55.1 - 47.2) * 100 + 10}`);
  for (const f of states.features) {   // one solid colour per state: its dominant zone
    const p = f.properties;
    const path = el("path", {d: pathOf(f.geometry), fill: ZONE_COLOR[p.zone], tabindex: 0, role: "button", "data-id": p.id, "data-zone": p.zone}, svg);
    // Pointer events, not mouse events: on phones there is no hover, so a single tap must open the popup (iOS Safari swallows the first tap when a hover handler changes the page).
    const lit = e => { highlightZone(p.zone); if (canHover()) { try { showHover(path, p.zone); } catch (err) { console.error(err); } } };   // cosmetic: an error here must never stop the tooltip
    path.addEventListener("pointerenter", e => { if (e.pointerType === "mouse") { lit(e); showTip(e, p); } });
    path.addEventListener("pointermove", e => { if (e.pointerType === "mouse") { if (!$("hoverLayer").firstChild) lit(e); showTip(e, p); } });   // self-healing: re-light if the first enter was missed
    path.addEventListener("pointerleave", e => { if (e.pointerType === "mouse") { hideTip(); highlightZone(null); clearHover(); } });
    path.addEventListener("pointerdown", e => { if (e.pointerType !== "mouse") highlightZone(p.zone); });   // touch / pen: show the zone while pressed
    for (const ev of ["pointerup", "pointercancel"]) path.addEventListener(ev, e => { if (e.pointerType !== "mouse") highlightZone(null); });
    path.addEventListener("focus", () => {   // only keyboard focus shows anything: same shape-following highlight as hover, plus the label
      if (!keyboardMode()) return; highlightZone(p.zone); try { showHover(path, p.zone); } catch (err) { console.error(err); }
      const r = path.getBoundingClientRect(); showTip({clientX: r.left + r.width / 2, clientY: r.top + r.height / 2}, p);
    });
    path.addEventListener("blur", () => { if (keyboardMode()) { hideTip(); highlightZone(null); clearHover(); } });
    path.addEventListener("click", () => openPopup(p));
    path.addEventListener("keydown", e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); openPopup(p); } });
  }
  setupHoverLayer(svg); updateMapLabels();
}
function updateMapLabels() {
  for (const f of states.features) {
    const p = f.properties, path = document.querySelector(`#map path[data-id="${p.id}"]`);
    path.setAttribute("aria-label", p.split ? t("state_aria_split", {state: stateName(p), zone: p.zone, others: names(p.also_served_by)}) : t("state_aria", {state: stateName(p), zone: p.zone}));
  }
  $("legend").innerHTML = Object.entries(ZONE_COLOR).map(([z, c]) => `<li><i style="background:${c}"></i>${esc(z)}</li>`).join("");
}
function showTip(e, p) {   // two pieces: the state name (large, bold) and the rest on a second, smaller line
  const tip = $("tip"); tip.hidden = false; tip.textContent = "";
  const a = document.createElement("span"), b = document.createElement("span"); a.className = "tipname"; b.className = "tiprest"; a.textContent = stateName(p); b.innerHTML = tm("tip_rest", {zone: L(p.zone)}); tip.appendChild(a); tip.appendChild(b);   // the zone name inside the second line is isolated left-to-right, so Arabic and German sentences keep their order
  const w = tip.offsetWidth || 240, h = tip.offsetHeight || 60, rtl = LANGS[lang].dir === "rtl", x = rtl ? e.clientX - 14 - w : e.clientX + 14;
  let y = e.clientY + 18; if (y + h > innerHeight - 4) y = e.clientY - 14 - h;                         // flip above the pointer near the bottom edge
  tip.style.left = Math.max(4, Math.min(x, innerWidth - w - 4)) + "px"; tip.style.top = Math.max(4, Math.min(y, innerHeight - h - 4)) + "px";
}
function hideTip() { $("tip").hidden = true; }

/* ---------- popup ---------- */
async function openPopup(p, date, hour) {
  hideTip(); clearHover(); highlightZone(null); const zone = p.zone;
  try { cur = {state: p, zone, data: await zoneData(zone), fdata: await futureData(zone), day: null, future: false}; }
  catch (e) { showLoadError("load_error_zone", e); return; }   // the zone file could not be fetched: say so instead of failing silently
  $("pTitle").textContent = stateName(p);
  $("zoneStmt").textContent = t("zone_stmt", {zone});
  const sp = $("splitStmt");
  if (p.split) { sp.hidden = false; sp.textContent = t("split_stmt", {state: stateName(p), zone, others: names(p.also_served_by)}); }
  else sp.hidden = true;
  const d = $("date"); d.min = meta.first_full_local_day; d.max = fmeta ? fmeta.covers_last_local_date : meta.last_full_local_day;
  const want = date || d.value || "2026-01-14"; d.value = (want < d.min) ? d.min : (want > d.max ? d.max : want);
  $("jumpToday").hidden = !fmeta; updateTodayButton();
  openModal($("popup"));
  renderDay(hour);
  setHash();
}
function openModal(dlg) {   // centred modal; the page behind is locked and inert, focus goes to the dialog and comes back on close
  if (dlg.open) return;
  lastFocus = document.activeElement; document.documentElement.classList.add("modal-open"); dlg.showModal(); dlg.focus({preventScroll: true});
}
function onModalClose() {
  if (document.querySelector("dialog[open]")) return;
  document.documentElement.classList.remove("modal-open");
  if (lastFocus && document.contains(lastFocus)) lastFocus.focus({preventScroll: true});   // give focus back; in pointer mode the focus handler shows nothing
}
function backdropClose(dlg) {   // a click that lands on the dialog element itself but outside its box is a click on the backdrop
  dlg.addEventListener("click", e => { if (e.target !== dlg) return; const r = dlg.getBoundingClientRect(); if (e.clientX < r.left || e.clientX > r.right || e.clientY < r.top || e.clientY > r.bottom) { dlg.close(); onModalClose(); } });
  dlg.addEventListener("close", onModalClose);
}
/* ---------- "Today" and "Latest real data" ---------- */
const todayIso = () => TodayLogic.berlinDate(Date.now());
function todayAction() { return TodayLogic.action(todayIso(), meta.first_full_local_day, meta.last_full_local_day, fmeta && fmeta.covers_first_local_date, fmeta && fmeta.covers_last_local_date); }
function updateTodayButton() {
  if (!fmeta || !meta) return; const a = todayAction(), btn = $("jumpToday"), msg = $("todayMsg");
  btn.disabled = a.kind === "ended";
  if (a.kind === "ended") { msg.hidden = false; msg.textContent = t("snapshot_ended", {date: fmtDate(a.date)}); } else msg.hidden = true;
  msg.dataset.kind = a.kind === "ended" ? "ended" : "";
}
function goToday() {
  const a = todayAction(), msg = $("todayMsg"); if (a.kind === "ended") return;
  $("date").value = a.date; msg.dataset.kind = "";
  if (a.kind === "nearest") { msg.hidden = false; msg.textContent = t("today_nearest", {date: fmtDate(a.date)}); } else msg.hidden = true;
  renderDay(); setHash();
}
function goLatest() { $("date").value = meta.last_full_local_day; $("todayMsg").hidden = true; updateTodayButton(); renderDay(); setHash(); }
function renderEnded() {
  const e = $("ended"); if (!fmeta || !meta) { e.hidden = true; return; }
  const a = todayAction(); e.hidden = a.kind !== "ended"; if (!e.hidden) e.textContent = t("snapshot_ended", {date: fmtDate(a.date)});
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
  chart.innerHTML = ""; table.innerHTML = ""; $("fcNote").hidden = true; $("covStmt").hidden = true; $("backtestNote").hidden = !!fut && !past; $("periodNote").textContent = ""; $("headline").innerHTML = "";
  $("popup").classList.toggle("is-future", cur.future); $("date").classList.toggle("unavailable", !day);
  document.querySelectorAll(".k-act-li").forEach(e => e.hidden = cur.future);
  $("bands").checked = bandsOn(); updateLegend();
  if (!day) {
    badge.className = "badge"; badge.textContent = t("badge_none"); badge.removeAttribute("title");
    const lastPast = meta.last_full_local_day, f0 = fmeta ? fmeta.covers_first_local_date : null;
    info.textContent = (date > lastPast && f0 && date < f0) ? t("nodata_gap", {lastPast: fmtDate(lastPast), firstFuture: fmtDate(f0)})
      : (fmeta && date > fmeta.covers_last_local_date) ? t("nodata_after", {lastFuture: fmtDate(fmeta.covers_last_local_date)}) : t("nodata_other");
    $("more").open = true; return;
  }
  const o = document.createElement("option"); o.value = "day"; o.textContent = t("full_day"); sel.appendChild(o);
  day.h.forEach((h, i) => { const op = document.createElement("option"); op.value = i; op.textContent = hourLabel(day, i); sel.appendChild(op); });
  sel.value = (preferHour !== undefined && [...sel.options].some(x => x.value === String(preferHour))) ? String(preferHour) : "day";
  if (cur.future) { renderFutureHeader(day, date); drawChart(day); renderHour(); return; }
  const nTest = day.s.reduce((a, b) => a + b, 0), n = day.s.length;
  const period = nTest === n ? t("badge_test") : nTest === 0 ? t("badge_val") : t("badge_mixed", {nVal: N(n - nTest), nTest: N(nTest)});
  badge.className = "badge"; badge.classList.add(...(nTest === n ? ["test"] : nTest === 0 ? ["val"] : ["val", "mixed"])); badge.textContent = t("badge_past"); badge.title = period;   // the tuning / unseen-test distinction: tooltip and More details
  $("periodNote").textContent = period;
  const miss = expectedHours(date) - n;
  info.textContent = miss > 0 ? t("missing_hours", {n: N(miss)}) : "";
  const c = meta.test_coverage_cqr_by_zone[cur.zone], m = meta.test_coverage_cqr_mean; $("covStmt").hidden = false;
  $("covStmt").textContent = t("cov_stmt", {m80: PCT(m["80"], 1), m95: PCT(m["95"], 1), zone: cur.zone, z80: PCT(c["80"], 1), z95: PCT(c["95"], 1)});
  drawChart(day); renderHour();
}
function renderFutureHeader(day, date) {
  const badge = $("badge"), info = $("dayInfo"), ds = day.d, k = [...new Set(day.k)], dmin = Math.min(...ds), dmax = Math.max(...ds), outlook = dmax >= fmeta.outlook_first_day;
  badge.className = "badge fcst"; badge.textContent = t(outlook && dmin >= fmeta.outlook_first_day ? "badge_outlook" : "badge_future"); badge.removeAttribute("title");
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
    `<table class="acc"><thead><tr>${th("acc_h_model")}${th("acc_h_inputs")}${th("acc_h_val")}${th("acc_h_valcov")}${th("acc_h_test")}${th("acc_h_testcov")}</tr></thead><tbody>${rows}</tbody></table>` +
    `<p class="warnline">${tm("acc_warn")}</p>` +
    (fmeta.interval_method ? `<p class="small">${tm("intervals_future", {weeks: N(fmeta.interval_method.window_weeks), days: N(fmeta.interval_method.calibration_days), v80: PCT(fmeta.interval_method.validation_cov80, 1), v95: PCT(fmeta.interval_method.validation_cov95, 1)})}</p>` : "") +
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
    renderHeadline(day, v); drawChart(day); setHash(); return;
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
  renderHeadline(day, v); drawChart(day); setHash();
}
function renderHeadline(day, v) {
  const mean = a => a.reduce((x, y) => x + y, 0) / a.length, date = fmtDate($("date").value), hr = v === "day" ? null : L(hourLabel(day, +v));
  const at = a => v === "day" ? mean(a) : a[+v];
  const f = at(day.f); let html;
  if (cur.future) html = tm(hr ? "head_future_hour" : "head_future_day", {date, hour: hr, fc: MW(f), lo: N(at(day.l80)), hi: MW(at(day.u80))});
  else { const a = at(day.a); html = tm(hr ? "head_past_hour" : "head_past_day", {date, hour: hr, actual: MW(a), fc: MW(f), pct: PCT(100 * Math.abs(f - a) / a, 1)}); }
  $("headline").innerHTML = html;
}
const bandsOn = () => { const v = bandPref[cur.future ? "future" : "past"]; return v === null ? cur.future : v; };
function updateLegend() { document.querySelectorAll(".k-band-li").forEach(e => e.hidden = !bandsOn()); }
function drawChart(day) {
  const svg = $("chart"); svg.innerHTML = ""; const W = Math.max(300, Math.min(640, Math.round(svg.clientWidth || 640))), H_ = W < 450 ? 240 : 220, Lm = 64, R = 10, T = 10, B = 40, n = day.h.length, FS = 12;   // viewBox follows the real width, so text keeps its size on phones
  svg.setAttribute("viewBox", `0 0 ${W} ${H_}`);
  const fut = cur.future, bands = bandsOn(), all = [...(fut ? [] : day.a), ...day.f, ...(bands ? [...day.l95, ...day.u95] : [])]; let lo = Math.min(...all), hi = Math.max(...all); const pad = (hi - lo) * .08; lo -= pad; hi += pad;
  const x = i => Lm + (W - Lm - R) * (n === 1 ? .5 : i / (n - 1)), y = v => T + (H_ - T - B) * (1 - (v - lo) / (hi - lo));
  for (let k = 0; k <= 3; k++) { const v = lo + (hi - lo) * k / 3, yy = y(v); el("line", {x1: Lm, x2: W - R, y1: yy, y2: yy, stroke: "currentColor", opacity: .15}, svg); const tx = el("text", {x: Lm - 6, y: yy + 4, "text-anchor": "end", "font-size": FS, fill: "currentColor", opacity: .75}, svg); tx.textContent = nf(v); }
  const yt = el("text", {x: 11, y: (T + H_ - B) / 2, "font-size": FS, fill: "currentColor", opacity: .75, transform: `rotate(-90 11 ${(T + H_ - B) / 2})`, "text-anchor": "middle"}, svg); yt.textContent = t("axis_y");
  day.h.forEach((h, i) => { if (n <= 25 && (i % 3 === 0 || i === n - 1)) { const tx = el("text", {x: x(i), y: H_ - 22, "text-anchor": "middle", "font-size": FS, fill: "currentColor", opacity: .75}, svg); tx.textContent = String(h).padStart(2, "0"); } });
  const xt = el("text", {x: (Lm + W - R) / 2, y: H_ - 5, "text-anchor": "middle", "font-size": FS, fill: "currentColor", opacity: .75}, svg); xt.textContent = t("axis_x");
  const fc = getComputedStyle(document.documentElement).getPropertyValue("--fc").trim() || "#d55e00", act = getComputedStyle(document.documentElement).getPropertyValue("--act").trim() || "#222";
  const defs = el("defs", {}, svg); const hp = el("pattern", {id: "fcHatch", width: 8, height: 8, patternUnits: "userSpaceOnUse", patternTransform: "rotate(45)"}, defs); el("line", {x1: 0, y1: 0, x2: 0, y2: 8, stroke: "currentColor", "stroke-width": 1, opacity: .12}, hp);
  const line = (a, col, w) => el("polyline", {points: a.map((v, i) => `${x(i)},${y(v)}`).join(" "), fill: "none", stroke: col, "stroke-width": w, "stroke-linejoin": "round"}, svg);
  const band = (lo_, hi_, op) => { const top = lo_.map((_, i) => `${x(i)},${y(hi_[i])}`), bot = lo_.map((_, i) => `${x(i)},${y(lo_[i])}`).reverse(); el("polygon", {points: top.concat(bot).join(" "), fill: fc, opacity: op}, svg); };
  if (bands) { band(day.l95, day.u95, .2); band(day.l80, day.u80, .35); }
  if (fut) el("rect", {x: Lm, y: T, width: W - Lm - R, height: H_ - T - B, fill: "url(#fcHatch)", opacity: .5}, svg);
  const ln = line(day.f, fc, 2.4); if (fut) ln.setAttribute("stroke-dasharray", "7 4"); if (!fut) line(day.a, act, 2.2);
  const label = (txt, i, dy, col) => { const tx = el("text", {x: Math.max(Lm + 30, Math.min(W - R - 30, x(i))), y: y(txt.v) + dy, "text-anchor": "middle", "font-size": FS + 1, "font-weight": 700, fill: col, stroke: "var(--card)", "stroke-width": 3, "paint-order": "stroke"}, svg); tx.textContent = txt.s; };
  const argmax = a => a.indexOf(Math.max(...a)), argmin = a => a.indexOf(Math.min(...a));
  label({s: t("key_forecast"), v: day.f[argmax(day.f)]}, argmax(day.f), -8, fc);
  if (!fut) label({s: t("key_actual"), v: day.a[argmin(day.a)]}, argmin(day.a), 18, act);
  const v = $("hour").value;
  if (v !== "day") { const i = +v; el("line", {x1: x(i), x2: x(i), y1: T, y2: H_ - B, stroke: "currentColor", "stroke-dasharray": "4 3", opacity: .6}, svg); if (!fut) el("circle", {cx: x(i), cy: y(day.a[i]), r: 4.5, fill: act}, svg); el("circle", {cx: x(i), cy: y(day.f[i]), r: 4.5, fill: fc}, svg); }
  const hit = el("rect", {x: Lm, y: T, width: W - Lm - R, height: H_ - T - B, fill: "transparent", style: "cursor:pointer"}, svg);
  hit.addEventListener("click", e => { const b = svg.getBoundingClientRect(), px = (e.clientX - b.left) / b.width * W; const i = Math.max(0, Math.min(n - 1, Math.round((px - Lm) / (W - Lm - R) * (n - 1)))); $("hour").value = String(i); renderHour(); });
}
function snapParams() { return {gen: fmtDT(fmeta.generated_utc), first: fmtDT(fmeta.covers_first_utc), last: fmtDT(fmeta.covers_last_utc), d1: fmtDate(fmeta.covers_first_local_date), d2: fmtDate(fmeta.covers_last_local_date), origin: fmtDT(fmeta.origin_utc)}; }
function renderSnapshot() {   // one permanent line; the long explanation is in the "Data and licences" dialog
  if (!fmeta) return; const e = $("snapshot"); e.hidden = false; e.innerHTML = tm("snapshot_short", snapParams());
}

/* ---------- start ---------- */
async function init() {
  const sw = $("langs");
  for (const [code, info] of Object.entries(LANGS)) {   // buttons are labelled in their own language
    const b = document.createElement("button"); b.type = "button"; b.dataset.lang = code; b.lang = code; b.textContent = info.label; b.addEventListener("click", () => setLang(code)); sw.appendChild(b);
  }
  try { await setLang(pickLang(), false); } catch (e) { $("loaderr").hidden = false; $("loaderr").textContent = e.message + "  →  python3 -m http.server -d site 8000"; return; }
  try { [meta, states] = await Promise.all([getJSON("data/meta.json"), getJSON("data/states.geojson")]); }
  catch (e) { showLoadError("load_error", e); return; }
  try { fmeta = await getJSON("data/future_meta.json"); } catch (e) { fmeta = null; }   // the future snapshot is optional
  drawMap(); renderIntro(); renderSnapshot(); renderLicences(); renderEnded();
  backdropClose($("popup")); backdropClose($("licDialog"));
  $("licBtn").addEventListener("click", () => openModal($("licDialog")));
  $("bands").addEventListener("change", () => { const k = cur.future ? "future" : "past"; bandPref[k] = $("bands").checked; try { sessionStorage.setItem("bands_" + k, bandPref[k] ? "1" : "0"); } catch (e) { /* ignore */ } updateLegend(); if (cur.day) drawChart(cur.day); });
  $("date").addEventListener("change", () => { renderDay(); setHash(); });
  $("hour").addEventListener("change", renderHour);
  $("jumpLatest").addEventListener("click", goLatest); $("jumpToday").addEventListener("click", goToday);
  addEventListener("resize", () => { if (cur && cur.day && $("popup").open) drawChart(cur.day); });
  $("popup").addEventListener("close", () => history.replaceState(null, "", location.pathname + location.search));
  const h = new URLSearchParams(location.hash.slice(1)); const st = states.features.find(f => f.properties.id === h.get("state"));
  if (st) openPopup(st.properties, h.get("date") || undefined, h.get("hour") || undefined).then(() => { if (h.get("more") === "1") $("more").open = true; });   // &more=1 opens "More details" (used for screenshots)
}
init();
