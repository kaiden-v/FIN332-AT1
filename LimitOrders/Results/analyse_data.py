import argparse
import glob
import os

import pandas as pd
import matplotlib.pyplot as plt


def summarise(df, label):
    s = df["Slippage"]
    print(f"\n{label}: {len(df)} sessions")
    print(f"  Final position (all sessions): {[float(x) for x in sorted(df['Final Position'].unique())]}")
    print(f"  Slippage mean {s.mean():+.3f}, median {s.median():+.3f}, std dev {s.std():.3f}, "
          f"min/max {s.min():+.2f}/{s.max():+.2f}")
    if "Sweep Shares" in df.columns:
        print(f"  Sweep shares: mean {df['Sweep Shares'].mean():.0f}, max {df['Sweep Shares'].max():.0f}")

    row = {
        "Offset": float(df["Offset"].iloc[0]) if "Offset" in df.columns else None,
        "Sessions": len(df),
        "Mean Own VWAP": round(df["Own VWAP"].mean(), 3),
        "Mean Market VWAP": round(df["Market VWAP"].mean(), 3),
        "Slippage Mean": round(s.mean(), 3),
        "Slippage Median": round(s.median(), 3),
        "Slippage Std Dev": round(s.std(), 3),
        "Mean Abs Slippage": round(s.abs().mean(), 3),
        "Slippage Min": round(s.min(), 3),
        "Slippage Max": round(s.max(), 3),
        "Sessions Above Market VWAP": int((s > 0).sum()),
    }
    if "Sweep Shares" in df.columns:
        row["Mean Sweep Shares"] = round(df["Sweep Shares"].mean(), 1)
        row["Max Sweep Shares"] = int(df["Sweep Shares"].max())
    return row


def clean_timeseries(timeseries_csv):
    df = pd.read_csv(timeseries_csv)
    df = df.drop_duplicates(subset=["Session", "Tick"], keep="last")

    # Nothing filled yet: RIT reports an own VWAP of 0, which would plot as slippage of about -25
    no_fills = df["Own VWAP"] <= 0
    if no_fills.any():
        print(f"  Leaving out {int(no_fills.sum())} checkpoint(s) with no fills yet (own VWAP 0)")
        df = df[~no_fills]

    # Sessions stopped before the final tick would distort the mean line
    last_tick = df.groupby("Session")["Tick"].max()
    incomplete = last_tick[last_tick < last_tick.max()].index.tolist()
    if incomplete:
        print(f"  Leaving out incomplete session(s) from the plot: {incomplete}")
        df = df[~df["Session"].isin(incomplete)]

    return df.pivot(index="Tick", columns="Session", values="Slippage")


# One offset: a line per session plus the mean
def plot_timeseries(wide, label, out_path):
    fig, ax = plt.subplots(figsize=(11, 6))
    for session in wide.columns:
        ax.plot(wide.index, wide[session], linewidth=1, alpha=0.6,
                label=f"Session {session}" if len(wide.columns) <= 12 else None)
    ax.plot(wide.index, wide.mean(axis=1), color="black", linewidth=2.5, label="Mean across sessions")
    ax.axhline(0, color="grey", linewidth=1, linestyle="--")
    ax.set_xlabel("Tick")
    ax.set_ylabel("Slippage: own VWAP - market VWAP ($)\n(positive = paid more than market VWAP)")
    ax.set_title(f"{label}: slippage over the session")
    ax.grid(alpha=0.3)
    ax.legend(ncol=2, fontsize=8)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    print(f"  Saved plot to {out_path}")


# Individual sessions as dots with the mean marked, plus mean sweep shares, side by side
def plot_comparison(frames, out_path):
    labels = [label for label, _ in frames]
    fig, axes = plt.subplots(1, 2, figsize=(12, 5.5))

    ax = axes[0]
    for i, (label, df) in enumerate(frames, start=1):
        ax.scatter([i] * len(df), df["Slippage"], color="tab:blue", alpha=0.7, s=40, zorder=3)
        ax.hlines(df["Slippage"].mean(), i - 0.25, i + 0.25, color="tab:red", linewidth=3, zorder=4)
    ax.axhline(0, color="black", linewidth=1)
    ax.set_xticks(range(1, len(frames) + 1))
    ax.set_xticklabels(labels)
    ax.set_ylabel("Final slippage ($)\n(positive = paid more than market VWAP)")
    ax.set_title("Final slippage by offset (dots = sessions, red = mean)")
    ax.grid(axis="y", alpha=0.3)

    ax = axes[1]
    means = [df["Sweep Shares"].mean() if "Sweep Shares" in df.columns else 0 for _, df in frames]
    ax.bar(labels, means, color="tab:orange", alpha=0.85)
    ax.set_ylabel("Mean sweep shares")
    ax.set_title("Shares bought by the final market-order sweep")
    ax.grid(axis="y", alpha=0.3)

    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    print(f"\nSaved comparison plot to {out_path}")


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    parser = argparse.ArgumentParser(description="Analyse every limit-order offset in a Results folder.")
    parser.add_argument("--folder", default=here, help="folder with the results files (default: this script's folder)")
    args = parser.parse_args()

    files = sorted(glob.glob(os.path.join(args.folder, "*_offset_*_session_results.csv")))
    if not files:
        raise SystemExit(f"No *_offset_*_session_results.csv files found in {args.folder}")

    plots_dir = os.path.join(args.folder, "Plots")
    os.makedirs(plots_dir, exist_ok=True)

    rows, frames = [], []
    for path in files:
        df = pd.read_csv(path)
        offset = float(df["Offset"].iloc[0])
        label = f"Limit offset {offset:.2f}"

        rows.append(summarise(df, label))
        frames.append((label, df))

        ts_path = path.replace("_session_results.csv", "_vwap_timeseries.csv")
        if os.path.exists(ts_path):
            wide = clean_timeseries(ts_path)
            plot_timeseries(wide, label, os.path.join(plots_dir, f"Limit_offset_{offset:.2f}_timeseries.png"))
        else:
            print(f"  No timeseries file for {label}, skipping its timeseries plot")

    frames.sort(key=lambda item: item[1]["Offset"].iloc[0])
    comparison = pd.DataFrame(rows).sort_values("Offset")
    comparison_path = os.path.join(args.folder, "Limit_orders_comparison.csv")
    comparison.to_csv(comparison_path, index=False)
    print(f"\nSaved comparison table to {comparison_path}")

    plot_comparison(frames, os.path.join(plots_dir, "Limit_orders_comparison.png"))


if __name__ == "__main__":
    main()