# Internship Signal

A privacy-first internship application tracker. It turns email updates into an auditable application timeline using deterministic rules, a replaceable classification provider, confidence routing, and human corrections.

See [implementation status](docs/IMPLEMENTATION_STATUS.md) for the phase-by-phase project state.

This repository is an implemented MVP foundation, not a claim of model accuracy. Gmail credentials, a genuinely labeled dataset, and benchmark results must come from the project owner; see [Your part](docs/YOUR_PART.md).

## Architecture

```text
Gmail/manual email
      ↓
normalize + remove quoted history
      ↓
rules + provider (primary Laya / TF-IDF benchmark)
      ↓ low confidence
optional local Ollama or human review
      ↓
email → classification → application event
      ↓
chronological status resolver → FastAPI → React dashboard
```

The provider boundary is intentional: Laya is now the primary typed-decision provider, while rules validate explicit evidence and disagreements enter review. The app records which provider made every decision.

## Run locally

Requirements: `uv`, Node.js 20+, and npm.

To start/reuse Ollama, the backend, and the frontend together and then import up
to 50 previously unseen matching Gmail messages, run this from the repository root:

```powershell
npm run dev
```

The command avoids starting a second Ollama instance when port 11434 is already
available. Override the new-message batch size when needed with
`$env:SYNC_LIMIT=100; npm run dev` (maximum 500).

For separate terminals instead:

```powershell
Copy-Item .env.example .env
uv sync
uv run fastapi dev app/main.py
```

In a second terminal:

```powershell
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`. API docs are at `http://localhost:8000/docs`.

To see the flow without Gmail, keep the backend running and execute:

```powershell
uv run python -m scripts.seed_demo
```

## Gmail connection

Complete Checkpoint 1 in [docs/YOUR_PART.md](docs/YOUR_PART.md), then:

1. Visit `GET /api/auth/google/start` in the API docs.
2. Open the returned authorization URL and approve read-only Gmail access.
3. The callback stores the token encrypted; raw credentials are gitignored.
4. List `GET /api/accounts`, then call `POST /api/accounts/{id}/sync`.

The current sync query limits collection to likely application mail from the last two years. Deduplication uses Gmail's immutable message ID.

## Classifier modes

Set `CLASSIFIER_PROVIDER` in `.env`:

- `rules` — deterministic fallback/testing mode; no training data needed.
- `baseline` — TF-IDF + logistic regression trained from your labels.
- `laya` — primary typed-decision path. It is installed by `uv sync`; the first inference downloads model weights.

Warm the configured checkpoint with:

```powershell
uv run python -m scripts.warmup_laya
```

After training the baseline, compare identical held-out rows across providers:

```powershell
uv run python -m scripts.benchmark_providers
```

The benchmark writes status/relevance macro F1, per-class metrics, confusion matrices, latency, manual-review rate, and LLM-escalation rate to `artifacts/provider_benchmark.json`.

Enable `OLLAMA_ENABLED=true` only after installing Ollama and pulling the configured model. Low-confidence results then use schema-constrained local analysis; otherwise they enter the human review queue.

Check the local runtime or exercise the full hybrid route with:

```powershell
uv run python -m scripts.warmup_ollama --model llama3:latest
uv run python -m scripts.smoke_hybrid
```

### Train the honest baseline

Generate the synthetic bootstrap dataset and train:

```powershell
uv run python -m scripts.generate_synthetic_dataset
uv run python -m scripts.train_baseline
```

The current dataset contains 384 synthetic messages across 64 template groups. The training script keeps whole template families out of training and writes the model plus held-out metrics under `artifacts/`. See [the dataset card](docs/DATASET_CARD.md) for composition and limitations.

### Improve accuracy with your reviewed emails

The best improvement is training on labels you verified in Review Desk—not blindly trusting model predictions. `Accept` and corrected statuses are stored as human-reviewed feedback and remain visible in **Accepted activity**.

After collecting enough varied decisions (at least four independent threads per status, plus unrelated hard negatives), export them locally and retrain:

```powershell
uv run python -m scripts.export_feedback_labels
uv run python -m scripts.train_baseline --data data/feedback_labels.csv
```

The export is Git-ignored because it contains your email text. The trainer evaluates on whole held-out threads and uses both word and character n-grams to better generalize across email wording. Once its held-out metrics improve on the existing provider, set `CLASSIFIER_PROVIDER=baseline` in `.env` and restart the app. Dashboard agreement is not real-world accuracy; it only measures agreement with decisions you reviewed.

## Test

```powershell
uv run pytest
cd frontend
npm run build
```

## Implemented scope

- Gmail OAuth with read-only scope and encrypted token-at-rest storage
- bounded Gmail sync and message-ID deduplication
- HTML/text normalization and quoted-history removal
- rules, TF-IDF, Laya, and Ollama provider boundaries
- confidence routing and review queue
- SQLAlchemy persistence for accounts, emails, classifications, applications, events, and feedback
- chronological status resolution
- thread-first application matching with normalized company/role fallback
- correction endpoint that saves training feedback
- searchable dashboard, status metrics, and human review UI
- unit and API integration tests

## Deliberately deferred

- production migrations and PostgreSQL deployment
- robust cross-email entity resolution for multiple roles at one company
- background scheduling/queues
- trained Laya specialization and calibration
- deadline/entity extraction beyond the minimal contract
- attachment parsing, multilingual evaluation, notifications, and calendar integration

Those belong after real data exposes which errors actually matter.
