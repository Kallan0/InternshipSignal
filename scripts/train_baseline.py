import argparse
import json
from pathlib import Path

import joblib
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report, confusion_matrix
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.pipeline import Pipeline

from app.domain import ApplicationStatus


def main() -> None:
    parser = argparse.ArgumentParser(description="Train and honestly evaluate the TF-IDF baseline.")
    parser.add_argument("--data", default="data/labels.csv")
    parser.add_argument("--output", default="artifacts/status_classifier.joblib")
    parser.add_argument("--report", default="artifacts/baseline_metrics.json")
    parser.add_argument("--split", default="artifacts/evaluation_split.json")
    args = parser.parse_args()

    frame = pd.read_csv(args.data).fillna("")
    required = {"external_id", "group_id", "subject", "body", "label", "is_relevant"}
    if missing := required - set(frame.columns):
        raise SystemExit(f"Missing columns: {', '.join(sorted(missing))}")
    relevance = frame["is_relevant"].map(lambda value: str(value).strip().lower() in {"true", "1", "yes"})
    relevant_counts = frame.loc[relevance, "label"].value_counts()
    if len(frame) < 30 or relevant_counts.empty or relevant_counts.min() < 3:
        raise SystemExit("Collect at least 30 rows and 3 relevant examples per included status.")
    if relevance.nunique() != 2:
        raise SystemExit("Include both relevant emails and unrelated hard negatives.")
    if frame["external_id"].eq("").any():
        raise SystemExit("Every row needs a stable external_id so all providers use the same holdout set.")
    if frame["external_id"].duplicated().any():
        raise SystemExit("external_id values must be unique.")
    if frame["group_id"].eq("").any():
        raise SystemExit("Every row needs a template/thread group_id to prevent evaluation leakage.")
    invalid = sorted(set(frame["label"]) - {item.value for item in ApplicationStatus})
    if invalid:
        raise SystemExit(f"Unknown labels: {', '.join(invalid)}")

    strata = relevance.astype(str) + ":" + frame["label"]
    groups_per_stratum = frame.assign(_stratum=strata).groupby("_stratum")["group_id"].nunique()
    if groups_per_stratum.min() < 4:
        raise SystemExit("Each relevance/status combination needs at least 4 independent groups.")
    if frame.assign(_stratum=strata).groupby("group_id")["_stratum"].nunique().max() != 1:
        raise SystemExit("A group_id cannot contain multiple relevance/status labels.")
    splitter = StratifiedGroupKFold(n_splits=4, shuffle=True, random_state=42)
    train_indices, test_indices = next(splitter.split(frame, strata, groups=frame["group_id"]))
    train_indices, test_indices = train_indices.tolist(), test_indices.tolist()
    text = frame["subject"] + "\n" + frame["body"]
    train_x, test_x = text.iloc[train_indices].tolist(), text.iloc[test_indices].tolist()

    def new_model() -> Pipeline:
        return Pipeline([
            ("tfidf", TfidfVectorizer(ngram_range=(1, 2), min_df=1, max_features=30_000, sublinear_tf=True)),
            ("classifier", LogisticRegression(max_iter=2_000, class_weight="balanced")),
        ])

    relevance_model = new_model()
    relevance_model.fit(train_x, relevance.iloc[train_indices].tolist())
    relevance_predicted = relevance_model.predict(test_x)

    relevant_train = [index for index in train_indices if relevance.iloc[index]]
    relevant_test = [index for index in test_indices if relevance.iloc[index]]
    status_model = new_model()
    status_model.fit(text.iloc[relevant_train].tolist(), frame["label"].iloc[relevant_train].tolist())
    status_actual = frame["label"].iloc[relevant_test].tolist()
    status_predicted = status_model.predict(text.iloc[relevant_test].tolist())
    status_report = classification_report(status_actual, status_predicted, output_dict=True, zero_division=0)
    report = {
        "status": status_report,
        "relevance": classification_report(
            relevance.iloc[test_indices].tolist(), relevance_predicted, output_dict=True, zero_division=0
        ),
        "confusion_matrix": confusion_matrix(
            status_actual, status_predicted, labels=list(status_model.classes_)
        ).tolist(),
        "classes": list(status_model.classes_),
        "train_rows": len(train_indices),
        "test_rows": len(test_indices),
    }

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.report).parent.mkdir(parents=True, exist_ok=True)
    Path(args.split).parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({"version": 2, "relevance": relevance_model, "status": status_model}, args.output)
    Path(args.report).write_text(json.dumps(report, indent=2), encoding="utf-8")
    Path(args.split).write_text(json.dumps({
        "seed": 42,
        "strategy": "StratifiedGroupKFold(n_splits=4)",
        "test_group_ids": sorted(frame["group_id"].iloc[test_indices].unique().tolist()),
        "test_external_ids": frame["external_id"].iloc[test_indices].tolist(),
    }, indent=2), encoding="utf-8")
    print(f"Saved model to {args.output}")
    print(f"Status macro F1: {report['status']['macro avg']['f1-score']:.3f}")
    print(f"Relevance macro F1: {report['relevance']['macro avg']['f1-score']:.3f}")


if __name__ == "__main__":
    main()
