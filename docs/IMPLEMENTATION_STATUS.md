# Implementation status

This file maps the implementation plan to the repository's current state.

| Phase | Status | Evidence / remaining work |
|---|---|---|
| Gmail OAuth and ingestion | Implemented, connection pending | Read-only OAuth, encrypted credentials, bounded sync, and message-ID deduplication exist. A real Google OAuth client still needs to be connected. |
| Email normalization | Implemented | HTML cleanup, tracking-image removal, whitespace cleanup, and quoted-history truncation are tested. |
| Labeling dataset | Implemented with synthetic data | 384 rows, 64 template groups, group-held-out evaluation. Real-email accuracy remains unproven. |
| TF-IDF baseline | Implemented | Separate relevance and status heads with a frozen evaluation split. |
| Laya integration | Implemented | Laya 0.3.12 typed-decisions checkpoint downloaded; single and batch inference verified. |
| Laya evaluation | Implemented on synthetic data | Provider benchmark records macro F1, per-class results, confusion matrices, latency, review rate, and escalation rate. |
| Rule validation | Implemented | Rules support predictions, recover relevance misses, and expose conflicts for review. |
| Local LLM | Implemented and runtime-verified | Schema-constrained Ollama adapter, health endpoint, prompt-injection boundary, mocked contract tests, and real `llama3:latest` inference pass. |
| Confidence router | Implemented | High/medium/low routing and conflict behavior are tested. Threshold calibration still needs non-test data. |
| Application matching | Implemented | Gmail-thread matching followed by conservative normalized company/role similarity. |
| Status resolver | Implemented | Chronological events, regression guards, terminal-state handling, and human overrides are tested. |
| Persistence | MVP implemented | SQLAlchemy and SQLite work locally. PostgreSQL and Alembic migrations remain. |
| Dashboard | Implemented | Application list, metrics, search, and human review queue build successfully. |
| Feedback loop | MVP implemented | Corrections are recorded as feedback and update application events. Dataset export/retraining automation remains. |

## Recommended next engineering phase

1. Connect and validate a real Gmail OAuth test account.
2. Add deadline/action extraction and dedicated action-item persistence.
3. Add Alembic migrations and a PostgreSQL development profile.
4. Add scheduled incremental sync and operational logging.
