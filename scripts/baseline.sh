#!/usr/bin/env bash
set -euo pipefail

BASELINE_NAME="${1:-mvp_v0.1}"
SNAP_DIR="baselines/${BASELINE_NAME}"

echo "[*] Freezing baseline -> ${SNAP_DIR}"

# Clean workspace outputs
rm -f data/dataset.csv
rm -rf results/env
mkdir -p data results

# Build + run + analyze
make build
make run
make analyze

# Capture env
./scripts/collect_env.sh results/env

# Write config.json (keep it simple and explicit)
cat > results/config.json <<'JSON'
{
  "workloads": ["cpu", "mem", "disk", "mix"],
  "intensity_levels": ["low", "med", "high"],
  "repetitions_per_config": 30,
  "resource_limits": { "cpus": 1, "memory": "512m", "network": "none" },
  "features": ["runtime_ms", "avg_cpu_percent", "max_mem_mib", "blk_read_mib", "blk_write_mib"],
  "classifier": "logistic_regression_scaled",
  "notes": "Telemetry collected from host via cgroup v2; single VM; Docker only."
}
JSON

# Create snapshot dir and copy immutable artifacts
mkdir -p "${SNAP_DIR}/data" "${SNAP_DIR}/results" "${SNAP_DIR}/env"

cp data/dataset.csv "${SNAP_DIR}/data/dataset.csv"
cp data/dataset.schema.json "${SNAP_DIR}/data/dataset.schema.json" 2>/dev/null || true

cp results/summary.md "${SNAP_DIR}/results/summary.md"
cp results/confusion_matrix.png "${SNAP_DIR}/results/confusion_matrix.png"
cp results/plot_runtime.png "${SNAP_DIR}/results/plot_runtime.png"
cp results/plot_mem.png "${SNAP_DIR}/results/plot_mem.png"

cp results/env/* "${SNAP_DIR}/env/"
cp results/config.json "${SNAP_DIR}/config.json"

echo "[*] Baseline frozen."

