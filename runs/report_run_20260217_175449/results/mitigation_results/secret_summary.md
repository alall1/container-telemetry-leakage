# Secret Leakage Results Summary

- Rows used (exit_code=0): 200
- Secret levels: [0, 1, 2, 3]
- Features: ['runtime_ms', 'avg_cpu_percent', 'max_mem_mib', 'blk_read_mib', 'blk_write_mib']
- Classifier: LogisticRegression (scaled)
- Test accuracy: 0.7600
- Random chance baseline (~1/4): 0.2500

Artifacts:
- results/secret_confusion_matrix.png
- results/secret_plot_runtime.png
- results/secret_plot_blk_write.png
