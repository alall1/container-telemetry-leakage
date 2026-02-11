import os
import pandas as pd
import matplotlib.pyplot as plt

from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.metrics import accuracy_score, confusion_matrix, ConfusionMatrixDisplay
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier

DATASET = "data/dataset.csv"

FEATURES = [
    "runtime_ms",
    "avg_cpu_percent",
    "max_mem_mib",
    "blk_read_mib",
    "blk_write_mib",
]

def main():
    os.makedirs("results", exist_ok=True)
    df = pd.read_csv(DATASET)

    # Filter out failed runs if any
    df = df[df["exit_code"] == 0].copy()

    X = df[FEATURES]
    y = df["workload"]

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.25, random_state=42, stratify=y
    )

    # Simple, interpretable baseline: Logistic Regression (with scaling)
    clf = Pipeline([
        ("scaler", StandardScaler()),
        ("lr", LogisticRegression(max_iter=2000))
    ])
    clf.fit(X_train, y_train)
    pred = clf.predict(X_test)

    acc = accuracy_score(y_test, pred)
    cm = confusion_matrix(y_test, pred, labels=sorted(y.unique()))

    # Confusion matrix plot
    disp = ConfusionMatrixDisplay(confusion_matrix=cm, display_labels=sorted(y.unique()))
    disp.plot()
    plt.title(f"Confusion Matrix (LogReg) acc={acc:.3f}")
    plt.savefig("results/confusion_matrix.png", dpi=200, bbox_inches="tight")
    plt.close()

    # Plot 1: runtime distribution by workload (boxplot)
    plt.figure()
    df.boxplot(column="runtime_ms", by="workload")
    plt.suptitle("")
    plt.title("Runtime (ms) by Workload")
    plt.ylabel("runtime_ms")
    plt.savefig("results/plot_runtime.png", dpi=200, bbox_inches="tight")
    plt.close()

    # Plot 2: memory usage by workload (boxplot)
    plt.figure()
    df.boxplot(column="max_mem_mib", by="workload")
    plt.suptitle("")
    plt.title("Peak Memory (MiB) by Workload")
    plt.ylabel("max_mem_mib")
    plt.savefig("results/plot_mem.png", dpi=200, bbox_inches="tight")
    plt.close()

    # Results summary markdown
    chance = 1.0 / df["workload"].nunique()
    with open("results/summary.md", "w") as f:
        f.write(f"# MVP Results Summary\n\n")
        f.write(f"- Rows used (exit_code=0): {len(df)}\n")
        f.write(f"- Features: {FEATURES}\n")
        f.write(f"- Classifier: LogisticRegression (scaled)\n")
        f.write(f"- Test accuracy: {acc:.4f}\n")
        f.write(f"- Random chance baseline (~1/4): {chance:.4f}\n\n")
        f.write(f"Artifacts:\n")
        f.write(f"- results/confusion_matrix.png\n")
        f.write(f"- results/plot_runtime.png\n")
        f.write(f"- results/plot_mem.png\n")

    print(f"Accuracy: {acc:.4f} (chance ~{chance:.4f})")
    print("Wrote results/summary.md and plots.")

if __name__ == "__main__":
    main()

