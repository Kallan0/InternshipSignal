# Your part: the work that creates learning and evidence

The repetitive work below is intentionally yours. It is where this project stops being an AI demo and becomes a defensible ML system. Do not share private emails or credentials in chat, issues, screenshots, or commits.

## Checkpoint 1 — Connect Gmail manually (30–60 minutes)

1. In Google Cloud Console, create or select a project.
2. Enable the Gmail API.
3. Configure an OAuth consent screen for an external test app.
4. Add your Google account as a test user.
5. Create a **Web application** OAuth client.
6. Add `http://localhost:8000/api/auth/google/callback` as an authorized redirect URI.
7. Download the client JSON and save it at the repository root as `credentials.json`.
8. Generate a key with `uv run python -m scripts.generate_key`; copy it into `.env` as `TOKEN_ENCRYPTION_KEY`.

Why this matters: OAuth separates authorization from passwords. The app asks only for `gmail.readonly`, and the encryption key stays outside source control. Learn to inspect scopes before approving any app.

Stop and verify: `GET /api/auth/google/start` returns a URL, authorization returns to the dashboard, and `GET /api/accounts` shows your address.

Before starting authorization, call `GET /api/auth/google/readiness`. It must report `ready: true` and `redirect_registered: true`; replacing the local JSON without registering the redirect URI in Google Cloud is not sufficient.

## Checkpoint 2 — Build the labeled dataset (3–6 focused hours)

The repository now includes a generated synthetic `data/labels.csv` so this checkpoint can run without your private mail. If you later add redacted real examples, keep a `group_id` shared by emails derived from the same company template or thread; the evaluation split keeps whole groups together to prevent leakage.

For every email, decide the status established by **this email**, not the final outcome you remember. Use:

- `APPLICATION_RECEIVED`: confirms submission was received.
- `UNDER_REVIEW`: explicitly says review is happening.
- `ASSESSMENT`: requests or reports a test/challenge.
- `INTERVIEW`: schedules or invites an interview.
- `NEXT_ROUND`: progression without a more specific interview/assessment label.
- `OFFER`: makes an employment/internship offer.
- `REJECTED`: explicitly ends the candidacy.
- `ACTION_REQUIRED`: requires a response/action but gives no clearer stage.
- `UNKNOWN`: related, but evidence is insufficient.

Labeling rules that make the difference:

1. Label explicit evidence, not hopeful interpretation.
2. If two labels appear, choose the newest action established by the message and note the ambiguity.
3. Keep near-duplicate templates in the same train/test group later; otherwise leakage inflates scores.
4. Include hard negatives such as job alerts, newsletters, and recruiter marketing.
5. Record uncertainty in `notes`; uncertain rows are valuable discussion material, not failures.

Why this matters: a sophisticated model trained on inconsistent labels learns inconsistency. Label definitions and disagreement handling often improve a classifier more than changing algorithms.

## Checkpoint 3 — Inspect errors, not just one score (60–90 minutes)

Run `uv run python -m scripts.train_baseline`, then open `artifacts/baseline_metrics.json`.

Answer these in `docs/EXPERIMENT_NOTES.md`:

1. Which class has the lowest recall? What wording does the model miss?
2. Which class has the lowest precision? What does it confuse with?
3. Are duplicates or company templates present across train and test?
4. Is macro F1 much lower than accuracy? If yes, which minority class is being ignored?
5. What confidence threshold gives acceptable errors for automatic updates?

Why this matters: accuracy can look good while rare `OFFER` or `REJECTED` messages fail. Macro F1 gives each class equal weight; the confusion matrix tells you what to fix.

## Checkpoint 4 — Benchmark Laya only after the baseline (1–3 hours plus download)

Run `uv sync`, then `uv run python -m scripts.warmup_laya`, and use the same held-out emails. After the baseline training script saves the split, run `uv run python -m scripts.benchmark_providers`. Record macro F1, per-class F1, latency, memory, review rate, and local-LLM escalation rate.

Do not copy benchmark numbers from Laya's website into this project. Its official documentation says zero-shot base models can be weak and confidence needs domain calibration. Your email dataset is the evidence that counts.

## Checkpoint 5 — Review real mistakes weekly (15 minutes/week)

Use the dashboard review queue. Correct ambiguous predictions rather than editing the database. Corrections create feedback rows that can become the next training set.

Track three questions:

- Did the model lack vocabulary/examples?
- Did normalization remove useful evidence or leave quoted history?
- Was the label definition itself ambiguous?

That diagnosis determines whether the right fix is more data, better parsing, clearer taxonomy, a rule, or a different model.
