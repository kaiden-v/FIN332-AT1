import argparse
import os
 
import pandas as pd
import matplotlib.pyplot as plt
 
 
def summarise(df, label):
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
    print(f"  Paid more than market VWAP: {(s > 0).sum()}, less: {(s < 0).sum()}, equal: {(s == 0).sum()}")
 
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
 
 
# Every session with its slippage, plus Mean and Std Dev rows, for the write-up
def build_table(df):
    table = df[["Session", "Own VWAP", "Market VWAP", "Slippage"]].copy()
    table["Session"] = table["Session"].astype(str)
    mean_row = {"Session": "Mean", "Own VWAP": df["Own VWAP"].mean(),
                "Market VWAP": df["Market VWAP"].mean(), "Slippage": df["Slippage"].mean()}
    std_row = {"Session": "Std Dev", "Own VWAP": df["Own VWAP"].std(),
               "Market VWAP": df["Market VWAP"].std(), "Slippage": df["Slippage"].std()}
    table = pd.concat([table, pd.DataFrame([mean_row, std_row])], ignore_index=True)
    return table.round(3)
 
 
def plot_by_session(df, label, out_path):
    fig, ax = plt.subplots(figsize=(10, 5.5))
    ax.bar(df["Session"], df["Slippage"], color="tab:blue", alpha=0.8)
    ax.axhline(0, color="black", linewidth=1)
    ax.axhline(df["Slippage"].mean(), color="tab:red", linestyle="--", linewidth=2,
               label=f"Mean {df['Slippage'].mean():+.3f}")
 
    ax.set_xlabel("Session")
    ax.set_xticks(df["Session"])
    ax.set_ylabel("Slippage: own VWAP - market VWAP ($)\n(positive = paid more than market VWAP)")
    ax.set_title(f"{label}: slippage by session")
    ax.grid(axis="y", alpha=0.3)
    ax.legend()
 
    fig.tight_layout()
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    fig.savefig(out_path, dpi=150)
    print(f"Saved plot to {out_path}")
 
 
def main():
    parser = argparse.ArgumentParser(description="Summary stats and plot for the immediate-buy runs.")
    parser.add_argument("--final", default="ImmediateBuy/Results/immediate_buy_session_results.csv")
    parser.add_argument("--label", default="Immediate buy")
    args = parser.parse_args()
 
    results_dir = os.path.dirname(args.final)
    name = args.label.replace(" ", "_")
    df = pd.read_csv(args.final)
 
    summary = summarise(df, args.label)
 
    summary_path = os.path.join(results_dir, f"{name}_summary.csv")
    pd.DataFrame([summary]).to_csv(summary_path, index=False)
    print(f"\nSaved summary to {summary_path}")
 
    table_path = os.path.join(results_dir, f"{name}_table.csv")
    build_table(df).to_csv(table_path, index=False)
    print(f"Saved session table to {table_path}")
 
    plot_by_session(df, args.label, os.path.join(results_dir, "Plots", f"{name}_slippage_by_session.png"))
 
 
if __name__ == "__main__":
    main()