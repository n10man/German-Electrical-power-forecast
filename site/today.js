"use strict";
// Pure date logic for the "Today" button (no DOM). All dates are Europe/Berlin calendar dates written YYYY-MM-DD.
const TodayLogic = (() => {
  const fmt = new Intl.DateTimeFormat("en-CA", {timeZone: "Europe/Berlin", year: "numeric", month: "2-digit", day: "2-digit"});
  const berlinDate = ms => fmt.format(new Date(ms));                                   // the clock is passed in, so tests can fake it
  const dayNo = iso => Math.round(Date.parse(iso + "T00:00:00Z") / 864e5);
  // r0/r1 = first/last date with real data; f0/f1 = first/last forecast date (null when there is no forecast snapshot).
  function action(today, r0, r1, f0, f1) {
    if (f1 && today > f1) return {kind: "ended", date: f1};                            // snapshot is over: no jump, show the notice
    if ((today >= r0 && today <= r1) || (f0 && today >= f0 && today <= f1)) return {kind: "set", date: today};
    const cands = [r0, r1].concat(f0 ? [f0, f1] : []);
    const best = cands.reduce((a, b) => Math.abs(dayNo(b) - dayNo(today)) < Math.abs(dayNo(a) - dayNo(today)) ? b : a);
    return {kind: "nearest", date: best};                                              // in the gap, or before the first real day
  }
  return {berlinDate, action};
})();
if (typeof module !== "undefined") module.exports = TodayLogic;
