"""
analyse_results.py

Summary tables and report plots for every strategy, plus cross-strategy comparisons.
Reads the CSVs in each <Strategy>/Results folder and never modifies them.

    python analyse_results.py
"""

import glob
import os
from dataclasses import dataclass

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy import stats

ROOT = os.path.dirname(os.path.abspath(__file__))
COMPARISON_DIR = os.path.join(ROOT, "Comparison")
IS = "Implementation Shortfall"
IS_AXIS = "Implementation shortfall ($/share)\nown VWAP - market VWAP"

# Fixed colour per strategy so it is the same in every plot
COLOURS = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#4a3aa7"]
INK, MUTED, GRID = "#1f1f1e", "#6b6a66", "#e4e3df"

plt.rcParams.update({
    "figure.dpi": 110, "savefig.dpi": 200, "savefig.bbox": "tight",
    "font.size": 10, "axes.titlesize": 12, "axes.titleweight": "bold",
    "axes.edgecolor": MUTED, "axes.labelcolor": INK, "text.color": INK,
    "xtick.color": MUTED, "ytick.color": MUTED,
    "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8, "axes.axisbelow": True,
    "legend.frameon": False,
})


@dataclass
class Strategy:
    label: str
    results_dir: str
    session_csv: str
    timeseries_csv: str | None
    prefix: str           # start of every output file name for this strategy
    colour: str = ""
    df: pd.DataFrame | None = None

    @property
    def shortfall(self):
        return self.df[IS]

    def out(self, name):
        return os.path.join(self.results_dir, name)

    def plot_path(self, name):
        return os.path.join(self.results_dir, "Plots", f"{self.prefix}_{name}.png")


# --- Loading -----------------------------------------------------------------------

def find_strategies():
    found = [
        Strategy("Immediate buy", "ImmediateBuy/Results", "immediate_buy_session_results.csv", None, "Immediate_buy"),
        Strategy("VWAP (4-tick)", "VWAPStrategy/Results", "4_tick_session_results.csv", "4_tick_vwap_timeseries.csv", "VWAP_4-tick"),
        Strategy("TWAP (4-tick)", "TWAPStrategy/Results", "twap_4_tick_session_results.csv", "twap_4_tick_vwap_timeseries.csv", "TWAP_4-tick"),
    ]
    # One entry per limit-order offset that has been run
    for path in sorted(glob.glob(os.path.join(ROOT, "LimitOrders/Results/*_offset_*_session_results.csv"))):
        name = os.path.basename(path).replace("_session_results.csv", "")
        offset = name.split("_offset_")[1]
        found.append(Strategy(f"Limit (bid + {offset})", "LimitOrders/Results", os.path.basename(path),
                              f"{name}_vwap_timeseries.csv", f"Limit_offset_{offset}"))

    strategies = []
    for s in found:
        s.results_dir = os.path.join(ROOT, s.results_dir)
        s.df = pd.read_csv(s.out(s.session_csv))
        if s.df.empty:
            print(f"Skipping {s.label}: {s.session_csv} has no sessions yet")
            continue
        s.colour = COLOURS[len(strategies)]
        strategies.append(s)
    return strategies

# Per-tick shortfall, one column per session, ready to plot
def load_timeseries(s):
    df = pd.read_csv(s.out(s.timeseries_csv)).drop_duplicates(subset=["Session", "Tick"], keep="last")
    # Before the first fill RIT reports an own VWAP of 0, which is not a real shortfall
    df = df[df["Own VWAP"] > 0]
    # Sessions stopped before the end would bend the mean line
    last_tick = df.groupby("Session")["Tick"].max()
    complete = last_tick[last_tick == last_tick.max()].index
    if len(complete) < len(last_tick):
        print(f"  {s.label}: leaving out incomplete sessions {sorted(set(last_tick.index) - set(complete))}")
    return df[df["Session"].isin(complete)].pivot(index="Tick", columns="Session", values=IS)


# --- Statistics --------------------------------------------------------------------

def summarise(s):
    x = s.shortfall
    return {
        "Sessions": len(x),
        "Mean Own VWAP": round(s.df["Own VWAP"].mean(), 3),
        "Mean Market VWAP": round(s.df["Market VWAP"].mean(), 3),
        "Shortfall Mean": round(x.mean(), 3),
        "Shortfall Median": round(x.median(), 3),
        "Shortfall Std Dev": round(x.std(), 3),
        "Mean Abs Shortfall": round(x.abs().mean(), 3),
        "Shortfall Min": round(x.min(), 3),
        "Shortfall Max": round(x.max(), 3),
        "Sessions Above Market VWAP": int((x > 0).sum()),
    }

# Mean shortfall with a 95% confidence interval
def mean_ci(s):
    x = s.shortfall
    n, mean, sd = len(x), x.mean(), x.std()
    half_width = stats.t.ppf(0.975, n - 1) * sd / np.sqrt(n)
    return {
        "Strategy": s.label, "Sessions": n,
        "Mean": round(mean, 4), "Std Dev": round(sd, 4),
        "CI 95% Low": round(mean - half_width, 4), "CI 95% High": round(mean + half_width, 4),
    }


# --- Per-strategy plots ------------------------------------------------------------

def save(fig, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fig.savefig(path)
    plt.close(fig)
    print(f"  saved {os.path.relpath(path, ROOT)}")

# Histogram of final shortfall, one bin per cent
def plot_distribution(s):
    x = s.shortfall
    fig, ax = plt.subplots(figsize=(9, 4.5))
    edges = np.arange(np.floor(x.min() * 100) - 0.5, np.ceil(x.max() * 100) + 1.5) / 100
    ax.hist(x, bins=edges, color=s.colour, edgecolor="white", linewidth=2)
    ax.axvline(0, color=MUTED, linewidth=1, linestyle="--")
    ax.axvline(x.mean(), color=INK, linewidth=1.5, label=f"Mean {x.mean():+.3f}")
    ax.set_xlabel(IS_AXIS)
    ax.set_ylabel("Number of sessions")
    ax.set_title(f"{s.label}: distribution of final shortfall (n = {len(x)})")
    ax.legend(loc="upper right")
    save(fig, s.plot_path("shortfall_distribution"))

# Final shortfall for each session in run order, with the mean
def plot_by_session(s):
    fig, ax = plt.subplots(figsize=(11, 4.5))
    ax.bar(s.df["Session"], s.shortfall, color=s.colour, width=0.7, edgecolor="white", linewidth=1)
    ax.axhline(0, color=INK, linewidth=1)
    ax.axhline(s.shortfall.mean(), color=INK, linestyle="--", linewidth=1.5, label=f"Mean {s.shortfall.mean():+.3f}")
    ax.set_xlabel("Session")
    ax.set_ylabel(IS_AXIS)
    ax.set_title(f"{s.label}: final shortfall by session")
    ax.legend(loc="upper right")
    save(fig, s.plot_path("shortfall_by_session"))

# Own VWAP against market VWAP: points above the 45-degree line paid more than the market
def plot_vwap_scatter(s):
    fig, ax = plt.subplots(figsize=(6, 6))
    lo = min(s.df["Own VWAP"].min(), s.df["Market VWAP"].min()) - 0.02
    hi = max(s.df["Own VWAP"].max(), s.df["Market VWAP"].max()) + 0.02
    ax.plot([lo, hi], [lo, hi], color=MUTED, linewidth=1.5, linestyle="--", label="Own VWAP = market VWAP")
    ax.scatter(s.df["Market VWAP"], s.df["Own VWAP"], color=s.colour, s=50, edgecolor="white", linewidth=1,
               zorder=3, label="Sessions")
    ax.set_xlim(lo, hi)
    ax.set_ylim(lo, hi)
    ax.set_aspect("equal")
    ax.set_xlabel("Market VWAP ($)")
    ax.set_ylabel("Own VWAP ($)")
    ax.set_title(f"{s.label}: own vs market VWAP")
    ax.legend(loc="upper left")
    save(fig, s.plot_path("vwap_scatter"))

# Shortfall through the session: each session faintly, the mean and a +/-1 sd band on top
def plot_timeseries(s, wide):
    mean, sd = wide.mean(axis=1), wide.std(axis=1)
    fig, ax = plt.subplots(figsize=(11, 5.5))
    ax.plot(wide.index, wide.values, color="#b9b8b2", linewidth=0.8, alpha=0.6)
    ax.plot([], [], color="#b9b8b2", linewidth=0.8, label=f"Individual sessions (n = {wide.shape[1]})")
    ax.fill_between(wide.index, mean - sd, mean + sd, color=s.colour, alpha=0.18, linewidth=0, label="Mean +/- 1 sd")
    ax.plot(wide.index, mean, color=s.colour, linewidth=2.5, label="Mean across sessions")
    ax.axhline(0, color=INK, linewidth=1)
    ax.set_xlim(wide.index.min(), wide.index.max())
    ax.set_xlabel("Tick")
    ax.set_ylabel(IS_AXIS)
    ax.set_title(f"{s.label}: running shortfall over the session")
    ax.legend(loc="upper right")
    save(fig, s.plot_path("timeseries"))

# Limit orders only: shares the limit orders failed to fill, bought at market in the final sweep
def plot_sweep_shares(s):
    df = s.df
    swept = (df["Sweep Shares"] > 0).sum()
    fig, ax = plt.subplots(figsize=(11, 4.5))
    ax.bar(df["Session"], df["Sweep Shares"], color=s.colour, width=0.7)
    for session, shares, shortfall in zip(df["Session"], df["Sweep Shares"], df[IS]):
        if shares > 0:
            ax.annotate(f"{shares:,} sh\nIS {shortfall:+.2f}", (session, shares), xytext=(0, 4),
                        textcoords="offset points", ha="center", va="bottom", fontsize=9, color=INK)
    ax.set_xticks(df["Session"])
    ax.set_ylim(0, max(df["Sweep Shares"].max() * 1.25, 1))
    ax.set_xlabel("Session")
    ax.set_ylabel("Shares bought by the final sweep")
    ax.set_title(f"{s.label}: unfilled shares swept at market ({swept} of {len(df)} sessions)")
    save(fig, s.plot_path("sweep_shares"))


# --- Cross-strategy comparison -----------------------------------------------------

# Box plot of final shortfall per strategy with every session overlaid as a dot
def plot_shortfall_by_strategy(strategies):
    fig, ax = plt.subplots(figsize=(10, 5.5))
    rng = np.random.default_rng(0)
    for i, s in enumerate(strategies, start=1):
        ax.boxplot(s.shortfall, positions=[i], widths=0.5, showfliers=False,
                   medianprops={"color": INK, "linewidth": 2},
                   boxprops={"color": MUTED}, whiskerprops={"color": MUTED}, capprops={"color": MUTED})
        jitter = rng.uniform(-0.15, 0.15, len(s.shortfall))
        ax.scatter(i + jitter, s.shortfall, color=s.colour, s=30, alpha=0.8, edgecolor="white", linewidth=0.8, zorder=3)
    ax.axhline(0, color=INK, linewidth=1, linestyle="--")
    ax.set_xticks(range(1, len(strategies) + 1), [f"{s.label}\n(n = {len(s.shortfall)})" for s in strategies])
    ax.set_ylabel(IS_AXIS)
    ax.set_title("Final implementation shortfall by strategy")
    save(fig, os.path.join(COMPARISON_DIR, "shortfall_by_strategy.png"))

# Mean shortfall with 95% confidence intervals: an interval clear of zero is a significant cost (or saving)
def plot_mean_ci(strategies, table):
    fig, ax = plt.subplots(figsize=(9, 0.9 * len(strategies) + 1.5))
    for i, (s, (_, row)) in enumerate(zip(strategies, table.iterrows())):
        y = len(strategies) - i
        mean, low, high = row["Mean"], row["CI 95% Low"], row["CI 95% High"]
        ax.errorbar(mean, y, xerr=[[mean - low], [high - mean]], fmt="o", color=s.colour,
                    markersize=9, elinewidth=2.5, capsize=5)
        ax.annotate(f"{mean:+.4f}  [{low:+.4f}, {high:+.4f}]", (high, y),
                    xytext=(8, 0), textcoords="offset points", va="center", fontsize=9, color=INK)
    ax.axvline(0, color=INK, linewidth=1, linestyle="--")
    ax.set_yticks(range(len(strategies), 0, -1), [s.label for s in strategies])
    ax.set_ylim(0.4, len(strategies) + 0.6)
    ax.margins(x=0.35)
    ax.grid(axis="y", visible=False)
    ax.set_xlabel("Mean implementation shortfall ($/share) with 95% confidence interval")
    ax.set_title("Mean shortfall by strategy")
    save(fig, os.path.join(COMPARISON_DIR, "mean_shortfall_ci.png"))

# Expected cost against risk (sd of cost), as in the efficient trading frontier (Hasbrouck 17.2)
def plot_cost_vs_risk(strategies):
    fig, ax = plt.subplots(figsize=(8, 5.5))
    for s in strategies:
        ax.scatter(s.shortfall.std(), s.shortfall.mean(), color=s.colour, s=120, edgecolor="white", linewidth=2, zorder=3)
        ax.annotate(s.label, (s.shortfall.std(), s.shortfall.mean()), xytext=(10, 4),
                    textcoords="offset points", fontsize=10, color=INK)
    ax.axhline(0, color=MUTED, linewidth=1, linestyle="--")
    ax.margins(x=0.3, y=0.25)
    ax.set_xlabel("Risk: standard deviation of shortfall across sessions ($/share)")
    ax.set_ylabel("Expected cost: mean shortfall ($/share)")
    ax.set_title("Cost vs risk by strategy (lower-left is better)")
    save(fig, os.path.join(COMPARISON_DIR, "cost_vs_risk.png"))

# Mean running shortfall for every strategy that logged checkpoints, on one axis
def plot_timeseries_comparison(series):
    fig, ax = plt.subplots(figsize=(11, 5.5))
    for s, mean in series:
        ax.plot(mean.index, mean.values, color=s.colour, linewidth=2.2, label=s.label)
    ax.axhline(0, color=INK, linewidth=1)
    ax.set_xlim(0, max(mean.index.max() for _, mean in series))
    ax.set_xlabel("Tick")
    ax.set_ylabel(IS_AXIS)
    ax.set_title("Mean running shortfall over the session")
    ax.legend(loc="center right")
    save(fig, os.path.join(COMPARISON_DIR, "shortfall_over_session.png"))


# --- Main --------------------------------------------------------------------------

def main():
    strategies = find_strategies()
    limits = [s for s in strategies if s.prefix.startswith("Limit")]
    mean_series = []

    for s in strategies:
        print(f"\n{s.label}: {len(s.df)} sessions, mean shortfall {s.shortfall.mean():+.3f}, sd {s.shortfall.std():.3f}")
        plot_distribution(s)
        plot_by_session(s)
        plot_vwap_scatter(s)
        if s in limits:
            plot_sweep_shares(s)
        else:
            pd.DataFrame([{"Strategy": s.label, **summarise(s)}]).to_csv(s.out(f"{s.prefix}_summary.csv"), index=False)
        if s.timeseries_csv:
            wide = load_timeseries(s)
            plot_timeseries(s, wide)
            mean_series.append((s, wide.mean(axis=1)))

    # Immediate buy: per-session table with Mean and Std Dev rows for the write-up
    immediate = next((s for s in strategies if s.prefix == "Immediate_buy"), None)
    if immediate:
        cols = ["Session", "Own VWAP", "Market VWAP", IS]
        table = immediate.df[cols].astype({"Session": str})
        stat_rows = pd.DataFrame([{"Session": name, **getattr(immediate.df[cols[1:]], fn)()} for name, fn in
                                  [("Mean", "mean"), ("Std Dev", "std")]])
        pd.concat([table, stat_rows], ignore_index=True).round(3).to_csv(immediate.out("Immediate_buy_table.csv"), index=False)

    # Limit orders: one row per offset
    if limits:
        rows = []
        for s in limits:
            row = {"Offset": float(s.df["Offset"].iloc[0]), **summarise(s),
                   "Mean Sweep Shares": round(s.df["Sweep Shares"].mean(), 1),
                   "Max Sweep Shares": int(s.df["Sweep Shares"].max())}
            rows.append(row)
        pd.DataFrame(rows).sort_values("Offset").to_csv(os.path.join(limits[0].results_dir, "Limit_orders_comparison.csv"), index=False)

    print("\nComparison across strategies")
    table = pd.DataFrame([mean_ci(s) for s in strategies])
    os.makedirs(COMPARISON_DIR, exist_ok=True)
    table.to_csv(os.path.join(COMPARISON_DIR, "strategy_comparison.csv"), index=False)
    print(table.to_string(index=False))
    plot_shortfall_by_strategy(strategies)
    plot_mean_ci(strategies, table)
    plot_cost_vs_risk(strategies)
    if mean_series:
        plot_timeseries_comparison(mean_series)


if __name__ == "__main__":
    main()
