# Mitigation Evaluation Summary

- Rows used (exit_code=0): 360
- Features: ['runtime_ms', 'avg_cpu_percent', 'max_mem_mib', 'blk_read_mib', 'blk_write_mib']
- Classifier: LogisticRegression (scaled), evaluated separately per mitigation level
- Random chance baseline (~1/4): 0.2500

## Accuracy vs mitigation
- none: 0.7667
- low: 0.8000
- high: 0.7000

## Runtime overhead vs mitigation (median)
- none: median_runtime_ms=4586.2, overhead=0.0000
- low: median_runtime_ms=4804.1, overhead=0.0475
- high: median_runtime_ms=4627.8, overhead=0.0091

Artifacts:
- results/mitigation_accuracy_vs_strength.png
- results/mitigation_overhead_vs_strength.png
