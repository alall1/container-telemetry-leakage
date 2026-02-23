# Mitigation Evaluation Summary

- Rows used (exit_code=0): 360
- Features: ['runtime_ms', 'avg_cpu_percent', 'max_mem_mib', 'blk_read_mib']
- Classifier: LogisticRegression (scaled), evaluated separately per mitigation level
- Random chance baseline (~1/4): 0.2500

## Accuracy vs mitigation
- none: 0.7333
- low: 0.8333
- high: 0.5667

## Runtime overhead vs mitigation (median)
- none: median_runtime_ms=3646.8, overhead=0.0000
- low: median_runtime_ms=10228.0, overhead=1.8046
- high: median_runtime_ms=20220.8, overhead=4.5447

Artifacts:
- results/mitigation_accuracy_vs_strength.png
- results/mitigation_overhead_vs_strength.png
