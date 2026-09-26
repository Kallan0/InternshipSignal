# Synthetic email dataset card

## Purpose

This dataset bootstraps development and tests whether the pipeline, labels, splits, metrics, and provider adapters work end to end. It is not evidence of performance on real inbox mail.

## Provenance

- Generated locally by `scripts/generate_synthetic_dataset.py`.
- Contains no real people, email addresses, application IDs, links, or private email text.
- Company, recruiter, date, and role values are fictional substitutions.
- Output path: `data/labels.csv` (gitignored, reproducible from the generator).

## Composition

- 384 total messages.
- 324 application-related messages.
- 60 unrelated hard negatives.
- 36 relevant examples for each of the nine status labels.
- 64 independent template families.

The labels are:

`APPLICATION_RECEIVED`, `UNDER_REVIEW`, `ASSESSMENT`, `INTERVIEW`, `NEXT_ROUND`, `OFFER`, `REJECTED`, `ACTION_REQUIRED`, and `UNKNOWN`.

## Leakage control

Every row has a `group_id`. All variants derived from one wording template share a group. Training uses a four-fold stratified group split, so an entire template family belongs to either training or evaluation—never both.

This is stricter than a random row split, but it does not eliminate broader generator-style leakage. All messages still share the vocabulary and writing style of one synthetic generator.

## Intended uses

- Verify ingestion and training code.
- Compare providers on an identical frozen split.
- Find obvious taxonomy and routing failures.
- Exercise relevance negatives and all status classes.
- Provide a reproducible portfolio demonstration without exposing private mail.

## Invalid uses

- Claiming production accuracy.
- Selecting final confidence thresholds.
- Claiming multilingual, HTML, thread, attachment, or OCR support.
- Fine-tuning and evaluating on variants from the same template group.
- Replacing a later, privately held real-world evaluation set.

## Known gaps

- English only.
- Cleaner and shorter than real recruiting email.
- No signatures, quoted threads, tracking text, attachment-only messages, or malformed HTML.
- Limited ambiguity and company-specific phrasing.
- Dates are text placeholders rather than extraction ground truth.
- Synthetic relevance negatives are easier than some real job alerts and recruiting newsletters.

## Reproduce

```powershell
uv run python -m scripts.generate_synthetic_dataset
uv run python -m scripts.train_baseline
uv run python -m scripts.benchmark_providers
```
