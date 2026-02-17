import os
import pandas as pd
import matplotlib.pyplot as plt

from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.metrics import accuracy_score
from sklearn.linear_model import LogisticRegression

DATASET = "data/mitigation_dataset.csv"

FEATURES = [
    "runtime_ms",
    "avg_cpu_percent",
    "max_mem_mib",
    "blk_read_mib",
    "blk_write_mib",
]

MITIGATION_ORDER = ["none", "low", "high"]

def eval_one(df: pd.DataFrame) -> float:
    X = df[FEATURES]
    y = df["secret_N"].astype(int)

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.25, random_state=42, stratify=y
    )

    clf = Pipeline([
        ("scaler", StandardScaler()),
        ("lr", LogisticRegression(max_iter=2000))
    ])
    clf.fit(X_train, y_train)
    pred = clf.predict(X_test)
    return float(accuracy_score(y_test, pred))

def main():
    os.makedirs("results", exist_ok=True)
    df = pd.read_csv(DATASET)
    df = df[df["exit_code"] == 0].copy()

    # Accuracy per mitigation level (separate classifiers)
    accs = {}
    for m in MITIGATION_ORDER:
        sub = df[df["mitigation"] == m].copy()
        accs[m] = eval_one(sub)

    # Overhead: compare median runtime to "none" baseline
    median_rt = {m: float(df[df["mitigation"] == m]["runtime_ms"].median()) for m in MITIGATION_ORDER}
    base = median_rt["none"]
    overhead = {m: (median_rt[m] / base - 1.0) if base > 0 else 0.0 for m in MITIGATION_ORDER}

    # Plot: Accuracy vs mitigation
    plt.figure()
    xs = list(range(len(MITIGATION_ORDER)))
    ys = [accs[m] for m in MITIGATION_ORDER]
    plt.xticks(xs, MITIGATION_ORDER)
    plt.ylim(0.0, 1.0)
    plt.ylabel("Test accuracy (predict secret_N)")
    plt.title("Accuracy vs Mitigation Strength")
    plt.plot(xs, ys, marker="o")
    plt.savefig("results/mitigation_accuracy_vs_strength.png", dpi=200, bbox_inches="tight")
    plt.close()

    # Plot: Overhead vs mitigation
    plt.figure()
    ys2 = [overhead[m] for m in MITIGATION_ORDER]
    plt.xticks(xs, MITIGATION_ORDER)
    plt.ylabel("Median runtime overhead (fraction)")
    plt.title("Runtime Overhead vs Mitigation Strength")
    plt.plot(xs, ys2, marker="o")
    plt.savefig("results/mitigation_overhead_vs_strength.png", dpi=200, bbox_inches="tight")
    plt.close()

    chance = 1.0 / df["secret_N"].nunique()
    with open("results/mitigation_summary.md", "w") as f:
        f.write("# Mitigation Evaluation Summary\n\n")
        f.write(f"- Rows used (exit_code=0): {len(df)}\n")
        f.write(f"- Features: {FEATURES}\n")
        f.write("- Classifier: LogisticRegression (scaled), evaluated separately per mitigation level\n")
        f.write(f"- Random chance baseline (~1/4): {chance:.4f}\n\n")
        f.write("## Accuracy vs mitigation\n")
        for m in MITIGATION_ORDER:
            f.write(f"- {m}: {accs[m]:.4f}\n")
        f.write("\n## Runtime overhead vs mitigation (median)\n")
        for m in MITIGATION_ORDER:
            f.write(f"- {m}: median_runtime_ms={median_rt[m]:.1f}, overhead={overhead[m]:.4f}\n")
        f.write("\nArtifacts:\n")
        f.write("- results/mitigation_accuracy_vs_strength.png\n")
        f.write("- results/mitigation_overhead_vs_strength.png\n")

    print("Wrote results/mitigation_summary.md and plots.")

if __name__ == "__main__":
    main()

