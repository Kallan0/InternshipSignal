from app.services.normalizer import normalize_email


def test_html_is_cleaned_and_tracking_content_is_removed():
    result = normalize_email("<html><body><h1>Interview</h1><p>Tomorrow</p><img src='pixel'/></body></html>", None)
    assert "Interview" in result
    assert "Tomorrow" in result
    assert "pixel" not in result


def test_quoted_history_is_removed():
    result = normalize_email(None, "Please schedule.\n\nOn Tue, Person wrote:\n> old content")
    assert result == "Please schedule."
