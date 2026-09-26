import joblib
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline

from app.domain import ApplicationStatus
from app.services.classifiers import BaselineMLClassifier


def fit(texts, labels):
    model = Pipeline([
        ("tfidf", TfidfVectorizer()),
        ("classifier", LogisticRegression()),
    ])
    return model.fit(texts, labels)


def test_two_head_baseline_separates_relevance_from_unknown_status(tmp_path):
    texts = [
        "application update candidate", "interview for candidate", "weekly cooking newsletter", "bank receipt",
    ]
    relevance = fit(texts, [True, True, False, False])
    status = fit(
        ["application update candidate", "interview for candidate", "status is unclear", "please schedule interview"],
        ["UNKNOWN", "INTERVIEW", "UNKNOWN", "INTERVIEW"],
    )
    path = tmp_path / "baseline.joblib"
    joblib.dump({"version": 2, "relevance": relevance, "status": status}, path)

    classifier = BaselineMLClassifier(str(path))
    result = classifier.classify("Interview", "jobs@example.test", "Please schedule interview for candidate")
    assert result.is_relevant is True
    assert result.status is ApplicationStatus.INTERVIEW
    assert len(result.evidence) == 2
