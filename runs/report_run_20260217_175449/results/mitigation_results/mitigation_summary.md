# Mitigation Evaluation Summary

- Rows used (exit_code=0): 360
- Features: ['runtime_ms', 'avg_cpu_percent', 'max_mem_mib', 'blk_read_mib']
- Classifier: LogisticRegression (scaled), evaluated separately per mitigation level
- Random chance baseline (~1/4): 0.2500

## Accuracy vs mitigation
- none: 0.7333
- low: 0.7667
- high: 0.6000

## Runtime overhead vs mitigation (median)
- none: median_runtime_ms=3573.9, overhead=0.0000
- low: median_runtime_ms=10229.8, overhead=1.8624
- high: median_runtime_ms=20218.8, overhead=4.6574

Artifacts:
- results/mitigation_accuracy_vs_strength.png
- results/mitigation_overhead_vs_strength.png
