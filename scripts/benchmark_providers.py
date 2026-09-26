import argparse
import json
from pathlib import Path
from time import perf_counter

import pandas as pd
from sklearn.metrics import classification_report, confusion_matrix, f1_score

from app.config import get_settings
from app.schemas import ClassificationResult
from app.services.classifiers import BaselineMLClassifier, LayaClassifier, RulesClassifier
from app.services.decision_router import ConfidenceRouter
from app.services.normalizer import normalize_email
from app.services.rules import classify_with_rules


def as_bool(value: object) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes"}


def metrics(rows: pd.DataFrame, predictions: list[ClassificationResult], elapsed: float) -> dict:
    actual_relevance = [as_bool(value) for value in rows["is_relevant"]]
    predicted_relevance = [item.is_relevant for item in predictions]
    relevant_indices = [index for index, value in enumerate(actual_relevance) if value]
    actual_status = [rows.iloc[index]["label"] for index in relevant_indices]
    predicted_status = [predictions[index].status.value for index in relevant_indices]
    labels = sorted(set(actual_status) | set(predicted_status))
    relevant_predictions = [item for item in predictions if item.is_relevant]
    low = sum(item.confidence < get_settings().ml_medium_confidence for item in relevant_predictions)
    return {
        "rows": len(rows),
        "status_macro_f1": f1_score(actual_status, predicted_status, average="macro", zero_division=0),
        "relevance_macro_f1": f1_score(actual_relevance, predicted_relevance, average="macro", zero_division=0),
        "manual_review_rate": sum(item.needs_review for item in predictions) / len(predictions),
        "llm_escalation_rate": low / max(len(relevant_predictions), 1),
        "average_latency_ms_per_email": elapsed * 1000 / len(rows),
        "status_report": classification_report(
            actual_status, predicted_status, labels=labels, output_dict=True, zero_division=0
        ),
        "confusion_matrix": confusion_matrix(actual_status, predicted_status, labels=labels).tolist(),
        "classes": labels,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare Laya, the baseline, rules, and routed hybrids.")
    parser.add_argument("--data", default="data/labels.csv")
    parser.add_argument("--split", default="artifacts/evaluation_split.json")
    parser.add_argument("--output", default="artifacts/provider_benchmark.json")
    parser.add_argument("--batch-size", type=int, default=16)
    args = parser.parse_args()

    settings = get_settings()
    frame = pd.read_csv(args.data).fillna("")
    required = {"external_id", "group_id", "sender", "subject", "body", "label", "is_relevant"}
    if missing := required - set(frame.columns):
        raise SystemExit(f"Missing columns: {', '.join(sorted(missing))}")
    split = json.loads(Path(args.split).read_text(encoding="utf-8"))
    test_ids = set(split["test_external_ids"])
    rows = frame[frame["external_id"].isin(test_ids)].copy()
    if len(rows) != len(test_ids):
        raise SystemExit("The dataset no longer matches the saved evaluation split.")
    inputs = [
        (row.subject, row.sender, normalize_email(None, row.body))
        for row in rows.itertuples(index=False)
    ]

    providers = {
        "tfidf": BaselineMLClassifier(settings.classifier_model_path),
        "laya": LayaClassifier(settings.laya_model, settings.laya_device, settings.laya_max_loaded),
        "rules": RulesClassifier(),
    }
    report: dict[str, dict] = {}
    confidence_router = ConfidenceRouter(settings.ml_high_confidence, settings.ml_medium_confidence)
    for name, provider in providers.items():
        started = perf_counter()
        if isinstance(provider, LayaClassifier):
            raw = provider.classify_many(inputs, batch_size=args.batch_size)
        else:
            raw = [provider.classify(*item) for item in inputs]
        elapsed = perf_counter() - started
        report[name] = metrics(rows, raw, elapsed)

        if name != "rules":
            routed = [
                confidence_router.route(
                    result.model_copy(deep=True), classify_with_rules(subject, body)
                )
                for result, (subject, _sender, body) in zip(raw, inputs, strict=True)
            ]
            report[f"{name}+rules"] = metrics(rows, routed, elapsed)

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Saved benchmark to {output}")
    for name, result in report.items():
        print(f"{name:14} macro F1={result['status_macro_f1']:.3f} review={result['manual_review_rate']:.1%}")


if __name__ == "__main__":
    main()
