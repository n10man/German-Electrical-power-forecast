"use strict";
// Plain JS + SVG. No libraries, no map tiles, no API keys. Needs to be served over http (fetch), see README.
const ZONE_COLOR = {"50Hertz": "#0072B2", "Amprion": "#E69F00", "TenneT": "#009E73", "TransnetBW": "#CC79A7"};
const SVGNS = "http://www.w3.org/2000/svg";
const $ = id => document.getElementById(id);
const fmt = (x, d = 0) => x.toLocaleString("en-GB", {minimumFractionDigits: d, maximumFractionDigits: d});
const cache = {};
let meta, fmeta = null, states, cur = null;  // cur = {state, zone, data, fdata, day, future}
const fcache = {};

function el(name, attrs = {}, parent) { const e = document.createElementNS(SVGNS, name); for (const k in attrs) e.setAttribute(k, attrs[k]); if (parent) parent.appendChild(e); return e; }

async function getJSON(url) { const r = await fetch(url); if (!r.ok) throw new Error(url + " -> HTTP " + r.status); return r.json(); }
async function zoneData(z) { return cache[z] || (cache[z] = await getJSON(`data/${z}.json`)); }
async function futureData(z) { if (!fmeta) return null; return fcache[z] || (fcache[z] = await getJSON(`data/future/${z}.json`)); }
const CONFIG_TXT = {A: "no weather inputs (calendar and recent load only)", B: "a forecast of temperature plus calendar and recent load", C: "forecasts of temperature, humidity, wind, solar radiation and cloud plus calendar and recent load"};

/* ---------- map ---------- */
function project(lon, lat) { const k = Math.cos(51 * Math.PI / 180); return [(lon - 5.8) * k * 100, (55.1 - lat) * 100]; }
function pathOf(geom) {
  const polys = geom.type === "Polygon" ? [geom.coordinates] : geom.coordinates;
  return polys.map(p => p.map(ring => "M" + ring.map(c => project(c[0], c[1]).map(v => v.toFixed(1)).join(",")).join("L") + "Z").join("")).join("");
}
function drawMap() {
  const svg = $("map"); const k = Math.cos(51 * Math.PI / 180);
  svg.setAttribute("viewBox", `-5 -5 ${(15.1 - 5.8) * k * 100 + 10} ${(55.1 - 47.2) * 100 + 10}`);
  const defs = el("defs", {}, svg);
  for (const f of states.features) {  // striped fill for split states
    const p = f.properties; if (!p.split) continue; const id = `p-${p.zone}-${p.also_served_by[0]}`;
    if (defs.querySelector("#" + CSS.escape(id))) continue;
    const pat = el("pattern", {id, width: 9, height: 9, patternUnits: "userSpaceOnUse", patternTransform: "rotate(45)"}, defs);
    el("rect", {width: 9, height: 9, fill: ZONE_COLOR[p.zone]}, pat); el("rect", {width: 1.8, height: 9, fill: ZONE_COLOR[p.also_served_by[0]]}, pat);
  }
  for (const f of states.features) {
    const p = f.properties;
    const path = el("path", {d: pathOf(f.geometry), fill: p.split ? `url(#p-${p.zone}-${p.also_served_by[0]})` : ZONE_COLOR[p.zone], tabindex: 0, role: "button",
      "aria-label": `${p.name}, ${p.zone} grid zone${p.split ? ", partly " + p.also_served_by.join(", ") : ""}. Open forecast.`, "data-id": p.id}, svg);
    path.addEventListener("mousemove", e => showTip(e, p)); path.addEventListener("mouseleave", hideTip);
    path.addEventListener("focus", () => { const r = path.getBoundingClientRect(); showTip({clientX: r.left + r.width / 2, clientY: r.top + r.height / 2}, p); });
    path.addEventListener("blur", hideTip);
    path.addEventListener("click", () => openPopup(p));
    path.addEventListener("keydown", e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); openPopup(p); } });
  }
  $("legend").innerHTML = Object.entries(ZONE_COLOR).map(([z, c]) => `<li><i style="background:${c}"></i>${z}</li>`).join("");
}
function showTip(e, p) {
  const t = $("tip"); t.hidden = false;
  t.textContent = `${p.name} · ${p.zone} grid zone` + (p.split ? ` (partly ${p.also_served_by.join(", ")})` : "");
  t.style.left = Math.min(e.clientX + 14, innerWidth - 270) + "px"; t.style.top = (e.clientY + 14) + "px";
}
function hideTip() { $("tip").hidden = true; }

/* ---------- popup ---------- */
async function openPopup(p, date, hour) {
  hideTip(); const zone = p.zone;
  cur = {state: p, zone, data: await zoneData(zone), fdata: await futureData(zone), day: null, future: false};
  $("pTitle").textContent = p.name;
  $("zoneStmt").textContent = `Forecast is for the ${zone} grid zone, not the state.`;
  const sp = $("splitStmt");
  if (p.split) { sp.hidden = false; sp.textContent = `${p.name} is split between grid zones. The dominant zone used here is ${zone} (a judgement from qualitative sources, not a measured share); part of ${p.name} is also served by ${p.also_served_by.join(" and ")}. The numbers below are for the whole ${zone} grid zone (which spans several states), not for ${p.name} alone.`; }
  else sp.hidden = true;
  const d = $("date"); d.min = meta.first_full_local_day; d.max = fmeta ? fmeta.covers_last_local_date : meta.last_full_local_day;
  const want = date || d.value || "2026-01-14"; d.value = (want < d.min) ? d.min : (want > d.max ? d.max : want);
  $("jumpPast").hidden = $("jumpFuture").hidden = !fmeta;
  const pop = $("popup"); if (!pop.open) pop.showModal();
  renderDay(hour);
  history.replaceState(null, "", `#state=${p.id}&date=${$("date").value}&hour=${$("hour").value}`);
}
function hourLabel(day, i) {
  const h = day.h[i], dup = day.h.filter(x => x === h).length > 1, second = dup && day.h.indexOf(h) !== i;
  return String(h).padStart(2, "0") + ":00" + (dup ? (second ? " (2nd, after clocks go back)" : " (1st)") : "");
}
function renderDay(preferHour) {
  const date = $("date").value, past = cur.data.days[date], fut = cur.fdata ? cur.fdata.days[date] : null, day = past || fut || null; cur.day = day; cur.future = !past && !!fut;
  const sel = $("hour"); sel.innerHTML = "";
  const badge = $("badge"), info = $("dayInfo"), chart = $("chart"), table = $("hourTable");
  chart.innerHTML = ""; table.innerHTML = ""; $("fcNote").hidden = true; $("covStmt").hidden = true; $("backtestNote").hidden = !!fut && !past;
  document.querySelector("#popup").classList.toggle("is-future", cur.future); $("date").classList.toggle("unavailable", !day);
  document.querySelectorAll(".k-act-li").forEach(e => e.hidden = cur.future);
  if (!day) {
    badge.className = "badge"; badge.textContent = "No data for this date";
    const lastPast = meta.last_full_local_day, f0 = fmeta ? fmeta.covers_first_local_date : null;
    info.textContent = (date > lastPast && f0 && date < f0) ? `No data for this date: the past data end on ${lastPast} (the newest weeks were held back as unsettled) and the forecast snapshot starts on ${f0}.`
      : (fmeta && date > fmeta.covers_last_local_date) ? `No forecast for this date: the snapshot ends on ${fmeta.covers_last_local_date}.` : "This date is outside the covered range or all its hours are missing.";
    return;
  }
  const o = document.createElement("option"); o.value = "day"; o.textContent = "Full day (all hours)"; sel.appendChild(o);
  day.h.forEach((h, i) => { const op = document.createElement("option"); op.value = i; op.textContent = hourLabel(day, i); sel.appendChild(op); });
  sel.value = (preferHour !== undefined && [...sel.options].some(x => x.value === String(preferHour))) ? String(preferHour) : "day";
  if (cur.future) { renderFutureHeader(day, date); drawChart(day); renderHour(); return; }
  const nTest = day.s.reduce((a, b) => a + b, 0), n = day.s.length;
  if (nTest === n) { badge.className = "badge test"; badge.textContent = "Unseen test period"; }
  else if (nTest === 0) { badge.className = "badge val"; badge.textContent = "Validation period (used for tuning and calibration)"; }
  else { badge.className = "badge val mixed"; badge.textContent = `Mixed day: ${n - nTest} h in the validation period (used for tuning and calibration), ${nTest} h in the unseen test period`; }
  const miss = expectedHours(date) - n;
  info.textContent = miss > 0 ? `${miss} hour(s) of this date are left out: the actual load for the hour, or for the same hour one or two weeks earlier (a model input), is missing in the source data.` : "";
  const c = meta.test_coverage_cqr_by_zone[cur.zone], m = meta.test_coverage_cqr_mean; $("covStmt").hidden = false;
  $("covStmt").textContent = `Measured on the unseen test year: the 80% range contained ${m["80"]}% of actual values and the 95% range ${m["95"]}% (mean of the four zones; ${cur.zone}: ${c["80"]}% and ${c["95"]}%). The ranges are narrower than their labels suggest.`;
  drawChart(day); renderHour();
}
function renderFutureHeader(day, date) {
  const badge = $("badge"), info = $("dayInfo"), ds = day.d, k = [...new Set(day.k)], dmin = Math.min(...ds), dmax = Math.max(...ds), outlook = dmax >= fmeta.outlook_first_day;
  badge.className = "badge fcst"; badge.textContent = outlook && dmin >= fmeta.outlook_first_day ? "Low-confidence outlook – this has not happened yet" : "Forecast – this has not happened yet";
  const hz = dmin === dmax ? `${dmin} day${dmin > 1 ? "s" : ""}` : `${dmin}–${dmax} days`;
  info.innerHTML = `<strong>Forecast generated on ${fmeta.generated_utc} UTC</strong>, covers ${fmeta.covers_first_utc} to ${fmeta.covers_last_utc} UTC. Horizon for this date: <strong>${hz} ahead</strong> of the last known load hour (${fmeta.origin_utc} UTC). This is a static snapshot, not live; there is no actual line because these hours had not happened when it was made.` +
    (day.h.length < 24 ? " This date is only partly covered by the snapshot." : "");
  const fc = $("fcNote"); fc.hidden = false;
  const rows = k.map(kk => { const a = fmeta.accuracy[`${cur.zone}|${kk}`], first = day.k.indexOf(kk), dd = [...new Set(day.d.filter((_, i) => day.k[i] === kk))].join("–");
    return `<tr><td>${kk === 21 ? "low-confidence outlook (days 17–21)" : "model for day " + (kk === 1 ? "1" : kk)}</td><td>${CONFIG_TXT[a.config]}</td><td>${fmt(a.val_mae)} / ${fmt(a.val_baseline_mae)} (−${a.val_gain_pct}%)</td><td>${a.val_cov80_swapped_mean}% / ${a.val_cov95_swapped_mean}% (worst cell ${a.val_cov80_swapped_min}% / ${a.val_cov95_swapped_min}%)</td><td>${fmt(a.test_mae)} / ${fmt(a.test_baseline_mae)} (−${a.test_gain_pct}%)</td><td>${a.test_cov80}% / ${a.test_cov95}%</td></tr>`; }).join("");
  const a1 = fmeta.accuracy[`${cur.zone}|1`], aL = fmeta.accuracy[`${cur.zone}|${fmeta.outlook_included ? 21 : 16}`];
  fc.innerHTML = `<p><strong>How accurate is this horizon?</strong> Accuracy falls the further ahead you look. For ${cur.zone} the average error in the unseen test year was ${fmt(a1.test_mae)} MWh/h for the 1-day model and ${fmt(aL.test_mae)} MWh/h for the ${fmeta.outlook_included ? "21" : "16"}-day model (the simple same-hour-last-week baseline: ${fmt(a1.test_baseline_mae)} and ${fmt(aL.test_baseline_mae)}). The 17–21 day outlook is low-confidence.</p>` +
    `<div class="tscroll"><table class="acc"><thead><tr><th>Model used</th><th>Inputs</th><th>Validation MAE vs baseline (MWh/h)</th><th>Validation 80% / 95% range coverage</th><th>Test-year MAE vs baseline</th><th>Test-year 80% / 95% coverage</th></tr></thead><tbody>${rows}</tbody></table></div>` +
    `<p class="warnline"><strong>The ranges are too narrow.</strong> On the unseen test year the 80% ranges contained about 72% and the 95% ranges about 90% of actual values at every horizon, and some zones were worse (TenneT 66% and 86%). Treat the ranges as optimistic.</p>` +
    `<p class="small">Weather: archived weather forecasts were only available for leads up to 7 days, so only days 1–7 can use a weather forecast, and only where it helped on validation (see the Inputs column; in most cases it did not). Days 8–21 use calendar and recent load only. Validation = ${meta.val_start.slice(0, 10)} to ${meta.test_start.slice(0, 10)} (exclusive); the test year was used for the load-only 24-hour model before and is now a second time for these models. Weather forecasts for days 1–7 come from Open-Meteo; the models were trained on older archived forecasts of the same kind (which may differ from today's forecast model mix).</p>`;
}
function expectedHours(date) { // 24, or 23/25 on the Berlin DST change days
  const f = (y, m) => { const d = new Date(Date.UTC(y, m, 31)); d.setUTCDate(31 - d.getUTCDay()); return d.toISOString().slice(0, 10); };
  const y = +date.slice(0, 4); if (date === f(y, 2)) return 23; if (date === f(y, 9)) return 25; return 24;
}
function renderHour() {
  const day = cur.day, v = $("hour").value, t = $("hourTable"); if (!day) return;
  const R = (a, i) => fmt(a[i]);
  if (cur.future) {
    const n = day.f.length, mean = a => a.reduce((x, y) => x + y, 0) / n;
    if (v === "day") t.innerHTML = `<tr><th>Whole day (${n} hours)</th><td></td></tr><tr><th>Mean forecast</th><td>${fmt(mean(day.f))} MWh/h</td></tr><tr><th>Mean 80% range</th><td>${fmt(mean(day.l80))} – ${fmt(mean(day.u80))} MWh/h</td></tr><tr><th>Mean 95% range</th><td>${fmt(mean(day.l95))} – ${fmt(mean(day.u95))} MWh/h</td></tr>`;
    else { const i = +v; t.innerHTML = `<tr><th>Time</th><td>${$("date").value} ${hourLabel(day, i)} Berlin time (${day.t[i].replace("T", " ").replace("Z", " UTC")})</td></tr><tr><th>Forecast</th><td>${R(day.f, i)} MWh/h</td></tr><tr><th>80% range</th><td>${R(day.l80, i)} – ${R(day.u80, i)} MWh/h</td></tr><tr><th>95% range</th><td>${R(day.l95, i)} – ${R(day.u95, i)} MWh/h</td></tr><tr><th>Horizon</th><td>${day.d[i]} day${day.d[i] > 1 ? "s" : ""} after the last known load hour (model for day ${day.k[i]})</td></tr>`; }
    drawChart(day); history.replaceState(null, "", `#state=${cur.state.id}&date=${$("date").value}&hour=${v}`); return;
  }
  if (v === "day") {
    const n = day.a.length, mean = a => a.reduce((x, y) => x + y, 0) / n;
    const in80 = day.a.filter((x, i) => x >= day.l80[i] && x <= day.u80[i]).length, in95 = day.a.filter((x, i) => x >= day.l95[i] && x <= day.u95[i]).length;
    const mae = day.a.reduce((s, x, i) => s + Math.abs(day.f[i] - x), 0) / n;
    t.innerHTML = `<tr><th>Whole day (${n} hours)</th><td></td></tr><tr><th>Mean actual load</th><td>${fmt(mean(day.a))} MWh/h</td></tr><tr><th>Mean forecast</th><td>${fmt(mean(day.f))} MWh/h</td></tr>` +
      `<tr><th>Mean absolute error this day</th><td>${fmt(mae)} MWh/h (${fmt(100 * mae / mean(day.a), 1)}% of mean load)</td></tr>` +
      `<tr><th>Actual inside 80% range</th><td>${in80} of ${n} hours</td></tr><tr><th>Actual inside 95% range</th><td>${in95} of ${n} hours</td></tr>`;
  } else {
    const i = +v, a = day.a[i], f = day.f[i], err = f - a, in80 = a >= day.l80[i] && a <= day.u80[i], in95 = a >= day.l95[i] && a <= day.u95[i];
    t.innerHTML = `<tr><th>Time</th><td>${$("date").value} ${hourLabel(day, i)} Berlin time (${day.t[i].replace("T", " ").replace("Z", " UTC")})</td></tr>` +
      `<tr><th>Actual</th><td>${R(day.a, i)} MWh/h</td></tr><tr><th>Forecast</th><td>${R(day.f, i)} MWh/h</td></tr>` +
      `<tr><th>Error (forecast − actual)</th><td>${err > 0 ? "+" : ""}${fmt(err)} MWh/h (${err > 0 ? "+" : ""}${fmt(100 * err / a, 1)}%)</td></tr>` +
      `<tr><th>80% range</th><td>${R(day.l80, i)} – ${R(day.u80, i)} MWh/h <span class="${in80 ? "in" : "out"}">${in80 ? "✓ actual inside" : "✗ actual outside"}</span></td></tr>` +
      `<tr><th>95% range</th><td>${R(day.l95, i)} – ${R(day.u95, i)} MWh/h <span class="${in95 ? "in" : "out"}">${in95 ? "✓ actual inside" : "✗ actual outside"}</span></td></tr>`;
  }
  drawChart(day); history.replaceState(null, "", `#state=${cur.state.id}&date=${$("date").value}&hour=${v}`);
}
function drawChart(day) {
  const svg = $("chart"); svg.innerHTML = ""; const W = 680, H = 300, L = 62, R = 12, T = 12, B = 34, n = day.h.length;
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
  const fut = cur.future, all = [...(fut ? [] : day.a), ...day.l95, ...day.u95, ...day.f]; let lo = Math.min(...all), hi = Math.max(...all); const pad = (hi - lo) * .06; lo -= pad; hi += pad;
  const x = i => L + (W - L - R) * (n === 1 ? .5 : i / (n - 1)), y = v => T + (H - T - B) * (1 - (v - lo) / (hi - lo));
  for (let k = 0; k <= 4; k++) { const v = lo + (hi - lo) * k / 4, yy = y(v); el("line", {x1: L, x2: W - R, y1: yy, y2: yy, stroke: "currentColor", opacity: .15}, svg); const t = el("text", {x: L - 6, y: yy + 4, "text-anchor": "end", "font-size": 11, fill: "currentColor", opacity: .7}, svg); t.textContent = fmt(v); }
  const yt = el("text", {x: 12, y: (T + H - B) / 2, "font-size": 11, fill: "currentColor", opacity: .7, transform: `rotate(-90 12 ${(T + H - B) / 2})`, "text-anchor": "middle"}, svg); yt.textContent = "MWh per hour";
  day.h.forEach((h, i) => { if (n <= 25 && (i % 3 === 0 || i === n - 1)) { const t = el("text", {x: x(i), y: H - 14, "text-anchor": "middle", "font-size": 11, fill: "currentColor", opacity: .7}, svg); t.textContent = String(h).padStart(2, "0"); } });
  const xt = el("text", {x: (L + W - R) / 2, y: H - 1, "text-anchor": "middle", "font-size": 11, fill: "currentColor", opacity: .7}, svg); xt.textContent = "hour of day (Berlin time)";
  const fc = getComputedStyle(document.documentElement).getPropertyValue("--fc").trim() || "#d55e00", act = getComputedStyle(document.documentElement).getPropertyValue("--act").trim() || "#222";
  const band = (lo_, hi_, op) => { const top = lo_.map((_, i) => `${x(i)},${y(hi_[i])}`), bot = lo_.map((_, i) => `${x(i)},${y(lo_[i])}`).reverse(); el("polygon", {points: top.concat(bot).join(" "), fill: fc, opacity: op}, svg); };
  band(day.l95, day.u95, .2); band(day.l80, day.u80, .35);
  const defs = el("defs", {}, svg); const hp = el("pattern", {id: "fcHatch", width: 8, height: 8, patternUnits: "userSpaceOnUse", patternTransform: "rotate(45)"}, defs); el("line", {x1: 0, y1: 0, x2: 0, y2: 8, stroke: "currentColor", "stroke-width": 1, opacity: .12}, hp);
  const line = (a, col, w) => el("polyline", {points: a.map((v, i) => `${x(i)},${y(v)}`).join(" "), fill: "none", stroke: col, "stroke-width": w, "stroke-linejoin": "round"}, svg);
  if (fut) el("rect", {x: L, y: T, width: W - L - R, height: H - T - B, fill: "url(#fcHatch)", opacity: .5}, svg);
  const ln = line(day.f, fc, 2.2); if (fut) ln.setAttribute("stroke-dasharray", "7 4"); if (!fut) line(day.a, act, 2);
  if (fut) { const wm = el("text", {x: L + 10, y: T + 20, "font-size": 13, "font-weight": 700, fill: "currentColor", opacity: .55}, svg); wm.textContent = "FORECAST – has not happened yet"; }
  const v = $("hour").value;
  if (v !== "day") { const i = +v; el("line", {x1: x(i), x2: x(i), y1: T, y2: H - B, stroke: "currentColor", "stroke-dasharray": "4 3", opacity: .6}, svg); if (!fut) el("circle", {cx: x(i), cy: y(day.a[i]), r: 4.5, fill: act}, svg); el("circle", {cx: x(i), cy: y(day.f[i]), r: 4.5, fill: fc}, svg); }
  const hit = el("rect", {x: L, y: T, width: W - L - R, height: H - T - B, fill: "transparent", style: "cursor:pointer"}, svg);
  hit.addEventListener("click", e => { const b = svg.getBoundingClientRect(), px = (e.clientX - b.left) / b.width * W; const i = Math.max(0, Math.min(n - 1, Math.round((px - L) / (W - L - R) * (n - 1)))); $("hour").value = String(i); renderHour(); });
}

function renderSnapshot() {
  if (!fmeta) return; const e = $("snapshot"); e.hidden = false;
  e.innerHTML = `<strong>Future forecast snapshot:</strong> Forecast generated on ${fmeta.generated_utc} UTC, covers ${fmeta.covers_first_utc} to ${fmeta.covers_last_utc} UTC (${fmeta.covers_first_local_date} to ${fmeta.covers_last_local_date} Berlin dates). It is a one-off file made from real weather forecasts and the latest load known at ${fmeta.origin_utc} UTC; this page does not update itself and your browser makes no weather requests. Days 1–16 are forecasts; days 17–21 are a low-confidence outlook without weather. Accuracy falls the further ahead you look.`;
}

/* ---------- start ---------- */
async function init() {
  try { [meta, states] = await Promise.all([getJSON("data/meta.json"), getJSON("data/states.geojson")]); }
  catch (e) { const m = $("loaderr"); m.hidden = false; m.textContent = "Could not load the data files (" + e.message + "). Serve this folder over http, e.g. `python3 -m http.server -d site 8000`, and open http://localhost:8000 (opening index.html directly via file:// is blocked by the browser)."; return; }
  try { fmeta = await getJSON("data/future_meta.json"); } catch (e) { fmeta = null; }   // the future snapshot is optional
  drawMap(); renderSnapshot();
  $("date").addEventListener("change", () => { renderDay(); history.replaceState(null, "", `#state=${cur.state.id}&date=${$("date").value}&hour=${$("hour").value}`); });
  $("hour").addEventListener("change", renderHour);
  $("jumpPast").addEventListener("click", () => { $("date").value = meta.last_full_local_day; renderDay(); });
  $("jumpFuture").addEventListener("click", () => { $("date").value = fmeta.covers_first_local_date; renderDay(); });
  $("popup").addEventListener("close", () => history.replaceState(null, "", location.pathname));
  const h = new URLSearchParams(location.hash.slice(1)); const st = states.features.find(f => f.properties.id === h.get("state"));
  if (st) openPopup(st.properties, h.get("date") || undefined, h.get("hour") || undefined);
}
init();
