# Experiment notes

Record measured results only. Keep the held-out set unchanged while comparing providers.

| Date | Dataset version | Provider | Macro F1 | Review rate | Avg latency | Notes |
|---|---|---|---:|---:|---:|---|
| 2026-09-24 | synthetic-v1, group-held-out | TF-IDF baseline | 0.407 | 0.0% raw | 1.06 ms | Relevance macro F1 0.448; all relevant predictions below escalation threshold |
| 2026-09-24 | synthetic-v1, group-held-out | TF-IDF + rules | 0.496 | 100.0% | 1.06 ms | Conflicts/support routed conservatively |
| 2026-09-24 | synthetic-v1, group-held-out | Laya typed-decisions | 0.637 | 0.0% raw | 1267.25 ms | Relevance macro F1 1.0; raw provider before routing |
| 2026-09-24 | synthetic-v1, group-held-out | Laya + rules | 0.696 | 81.25% | 1267.25 ms | Current production path; LLM escalation rate 100% at threshold 0.70 |
| 2026-09-24 | synthetic-v1, group-held-out | Rules only | 0.265 | 56.25% | 0.05 ms | Useful evidence layer, weak standalone classifier |

## Error analysis

- Lowest-performing Laya classes: `ACTION_REQUIRED` and relevant `UNKNOWN` (both F1 0.0).
- Strongest Laya classes: `INTERVIEW` and `NEXT_ROUND` (both F1 1.0 on this split).
- Common issue: Laya assigns a concrete stage when the correct label is ambiguous or only asks for a generic action.
- Suspected leakage: exact template leakage is prevented by `group_id`; generator-wide style leakage remains.
- Threshold change to test next: none on this test set. Create a separate calibration split before choosing thresholds.
- Examples to collect next: ambiguous portal notifications, document requests, consent/profile actions, and job alerts that resemble application updates.

These results are synthetic engineering diagnostics, not claims about real-email accuracy.
