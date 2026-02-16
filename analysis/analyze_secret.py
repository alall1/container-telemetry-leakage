import os
import pandas as pd
import matplotlib.pyplot as plt

from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.metrics import accuracy_score, confusion_matrix, ConfusionMatrixDisplay
from sklearn.linear_model import LogisticRegression

DATASET = "data/secret_dataset.csv"

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

    df = df[df["exit_code"] == 0].copy()

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

    acc = accuracy_score(y_test, pred)
    labels = sorted(y.unique())
    cm = confusion_matrix(y_test, pred, labels=labels)

    disp = ConfusionMatrixDisplay(confusion_matrix=cm, display_labels=[str(x) for x in labels])
    disp.plot()
    plt.title(f"Secret N Confusion Matrix (LogReg) acc={acc:.3f}")
    plt.savefig("results/secret_confusion_matrix.png", dpi=200, bbox_inches="tight")
    plt.close()

    plt.figure()
    df.boxplot(column="runtime_ms", by="secret_N")
    plt.suptitle("")
    plt.title("Runtime (ms) by Secret N")
    plt.ylabel("runtime_ms")
    plt.savefig("results/secret_plot_runtime.png", dpi=200, bbox_inches="tight")
    plt.close()

    plt.figure()
    df.boxplot(column="blk_write_mib", by="secret_N")
    plt.suptitle("")
    plt.title("Block Write (MiB) by Secret N")
    plt.ylabel("blk_write_mib")
    plt.savefig("results/secret_plot_blk_write.png", dpi=200, bbox_inches="tight")
    plt.close()

    chance = 1.0 / df["secret_N"].nunique()
    with open("results/secret_summary.md", "w") as f:
        f.write("# Secret Leakage Results Summary\n\n")
        f.write(f"- Rows used (exit_code=0): {len(df)}\n")
        f.write(f"- Secret levels: {sorted(df['secret_N'].unique().tolist())}\n")
        f.write(f"- Features: {FEATURES}\n")
        f.write("- Classifier: LogisticRegression (scaled)\n")
        f.write(f"- Test accuracy: {acc:.4f}\n")
        f.write(f"- Random chance baseline (~1/4): {chance:.4f}\n\n")
        f.write("Artifacts:\n")
        f.write("- results/secret_confusion_matrix.png\n")
        f.write("- results/secret_plot_runtime.png\n")
        f.write("- results/secret_plot_blk_write.png\n")

    print(f"Secret N accuracy: {acc:.4f} (chance ~{chance:.4f})")
    print("Wrote results/secret_summary.md and plots.")

if __name__ == "__main__":
    main()

