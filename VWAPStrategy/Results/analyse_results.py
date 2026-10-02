import argparse
import os

import pandas as pd
import matplotlib.pyplot as plt


def summarise(final_csv, label):
    df = pd.read_csv(final_csv)
    s = df["Slippage"]
    print(f"\n{label}: {len(df)} sessions")
    print(f"  Final position (all sessions): {[float(x) for x in sorted(df['Final Position'].unique())]}")
    print(f"  Mean own VWAP:    {df['Own VWAP'].mean():.3f}")
    print(f"  Mean market VWAP: {df['Market VWAP'].mean():.3f}")
    print(f"  Slippage mean:    {s.mean():+.3f}")
    print(f"  Slippage median:  {s.median():+.3f}")
    print(f"  Slippage std dev: {s.std():.3f}")
    print(f"  Mean abs slippage:{s.abs().mean():.3f}")
    print(f"  Slippage min/max: {s.min():+.2f} / {s.max():+.2f}")
    print(f"  Sessions paying more than market VWAP: {(s > 0).sum()} of {len(s)}")

    return {
        "Strategy": label,
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


def plot_timeseries(timeseries_csv, label, out_path):
    df = pd.read_csv(timeseries_csv)
    df = df.drop_duplicates(subset=["Session", "Tick"], keep="last")

    # Sessions stopped before the final tick would distort the mean line
    last_tick = df.groupby("Session")["Tick"].max()
    incomplete = last_tick[last_tick < last_tick.max()].index.tolist()
    if incomplete:
        print(f"\nLeaving out incomplete session(s) from the plot: {incomplete}")
        df = df[~df["Session"].isin(incomplete)]

    wide = df.pivot(index="Tick", columns="Session", values="Slippage")

    fig, ax = plt.subplots(figsize=(11, 6))
    for session in wide.columns:
        ax.plot(wide.index, wide[session], linewidth=1, alpha=0.6,
                label=f"Session {session}" if len(wide.columns) <= 12 else None)
    ax.plot(wide.index, wide.mean(axis=1), color="black", linewidth=2.5, label="Mean across sessions")
    ax.axhline(0, color="grey", linewidth=1, linestyle="--")
    ax.set_ylim(-0.04, 0.08)
    ax.set_yticks([-0.04, -0.02, 0.00, 0.02, 0.04, 0.06, 0.08])

    ax.set_xlabel("Tick")
    ax.set_ylabel("Slippage: own VWAP - market VWAP ($)\n(positive = paid more than market VWAP)")
    ax.set_title(f"{label}: slippage over the session")
    ax.grid(alpha=0.3)
    ax.legend(ncol=2, fontsize=8)

    fig.tight_layout()
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    fig.savefig(out_path, dpi=150)
    print(f"\nSaved plot to {out_path}")


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    parser = argparse.ArgumentParser(description="Summary stats and timeseries plot for the VWAP strategy.")
    parser.add_argument("--final", default=os.path.join(here, "4_tick_session_results.csv"))
    parser.add_argument("--timeseries", default=os.path.join(here, "4_tick_vwap_timeseries.csv"))
    parser.add_argument("--label", default="VWAP (4-tick)")
    parser.add_argument("--out", default=None, help="plot path (default: a Plots folder inside the timeseries file's Results folder)")
    args = parser.parse_args()

    # Save the plot in a Plots folder inside the same Results folder as the data
    plot_name = args.label.replace(" ", "_").replace("(", "").replace(")", "") + "_timeseries.png"
    out_path = args.out or os.path.join(os.path.dirname(args.timeseries), "Plots", plot_name)

    summary = summarise(args.final, args.label)
    summary_path = os.path.join(os.path.dirname(args.final), plot_name.replace("_timeseries.png", "_summary.csv"))
    pd.DataFrame([summary]).to_csv(summary_path, index=False)
    print(f"\nSaved summary to {summary_path}")

    plot_timeseries(args.timeseries, args.label, out_path)


if __name__ == "__main__":
    main()