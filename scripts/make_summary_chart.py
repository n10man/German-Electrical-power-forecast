"""README results chart: test-year MAE per zone for last-week baseline, SMARD official day-ahead forecast and my model.
Reads results/official_forecast_comparison.csv (logged numbers only). Writes docs/results_chart_light.png and docs/results_chart_dark.png.
Palette = the validated reference palette slots 1-3 (validate_palette: all checks pass in both modes; the light-mode aqua contrast warning is
covered by the value labels on every bar and by the table in the README)."""
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Rectangle, Patch
import pandas as pd
ZONES = ["50Hertz", "Amprion", "TenneT", "TransnetBW"]
SERIES = [("B1 last week (logged, F1)", "Same hour last week (baseline)", 3), ("SMARD official day-ahead forecast (filter 411)", "SMARD official day-ahead forecast", 2), ("our model (logged, F1)", "My model (rolling 24-hour-ahead)", 1)]
THEME = {"light": dict(surface="#fcfcfb", ink="#0b0b0b", ink2="#52514e", grid="#e6e5e1", cols={1: "#2a78d6", 2: "#eb6834", 3: "#1baf7a"}),
         "dark": dict(surface="#1a1a19", ink="#f0efec", ink2="#c3c2b7", grid="#34332f", cols={1: "#3987e5", 2: "#d95926", 3: "#199e70"})}
R = pd.read_csv("results/official_forecast_comparison.csv"); R = R[R.period == "test"]
for mode, t in THEME.items():
    fig, ax = plt.subplots(figsize=(9, 4.9), dpi=130); fig.patch.set_facecolor(t["surface"]); ax.set_facecolor(t["surface"])
    ymax = 1350; ax.set_ylim(0, ymax); ax.set_xlim(-0.6, len(ZONES) - 0.4)
    bw, gap = 0.2, 0.026                                   # <= 24 px thick bars, ~2 px surface gap between neighbours
    for si, (key, label, slot) in enumerate(SERIES):
        for zi, z in enumerate(ZONES):
            v = float(R[(R.zone == z) & (R.model == key)].MAE.iloc[0]); x0 = zi + (si - 1) * (bw + gap) - bw / 2
            r = bw / 2.6
            p = FancyBboxPatch((x0, -r * 120), bw, v + r * 120, boxstyle=f"round,pad=0,rounding_size={r}", mutation_aspect=ymax / (len(ZONES) + 0.2) / 1.0 * 0 + 120, fc=t["cols"][slot], ec="none", zorder=3)
            ax.add_patch(p); p.set_clip_path(Rectangle((x0 - 0.01, 0), bw + 0.02, v + 5, transform=ax.transData))
            ax.text(x0 + bw / 2, v + 18, f"{v:,.0f}", ha="center", va="bottom", fontsize=8.5, color=t["ink"], zorder=4)
    ax.set_xticks(range(len(ZONES))); ax.set_xticklabels(ZONES, color=t["ink"], fontsize=10)
    ax.tick_params(axis="x", length=0, pad=8); ax.tick_params(axis="y", length=0, colors=t["ink2"], labelsize=9)
    ax.yaxis.grid(True, color=t["grid"], linewidth=1, zorder=0); ax.set_axisbelow(True)
    for s in ("top", "right", "left"): ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color(t["grid"]); ax.set_ylabel("Mean absolute error, MWh per hour (lower is better)", color=t["ink2"], fontsize=9)
    ax.set_title("Sealed test year (2025-10-25 to 2026-10-24): error by grid zone", loc="left", color=t["ink"], fontsize=12, fontweight="bold", pad=34)
    leg = ax.legend(handles=[Patch(facecolor=t["cols"][slot], label=label) for _, label, slot in SERIES], loc="lower left", bbox_to_anchor=(0, 1.0), ncol=3, frameon=False, fontsize=8.8, handlelength=1.1, handleheight=0.9, columnspacing=1.6, borderaxespad=0.2)
    for tx in leg.get_texts(): tx.set_color(t["ink"])
    fig.text(0.012, 0.012, "Not like-for-like: the official forecast is a true day-ahead forecast; mine is rolling 24-hour-ahead, uses lag_24h and observed weather.", color=t["ink2"], fontsize=7.8)
    fig.subplots_adjust(left=0.085, right=0.985, top=0.80, bottom=0.14); fig.savefig(f"docs/results_chart_{mode}.png", facecolor=t["surface"]); plt.close(fig)
print("wrote docs/results_chart_light.png and docs/results_chart_dark.png")
