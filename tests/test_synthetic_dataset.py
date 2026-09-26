from collections import Counter, defaultdict

from scripts.generate_synthetic_dataset import build_rows


def test_synthetic_dataset_is_balanced_unique_and_group_safe():
    rows = build_rows()
    assert len(rows) == 384
    assert len({row["external_id"] for row in rows}) == len(rows)

    relevant = [row for row in rows if row["is_relevant"] == "true"]
    negative = [row for row in rows if row["is_relevant"] == "false"]
    assert set(Counter(row["label"] for row in relevant).values()) == {36}
    assert len(negative) == 60
    assert len({row["group_id"] for row in rows}) == 64

    group_labels: dict[str, set[tuple[str, str]]] = defaultdict(set)
    for row in rows:
        group_labels[row["group_id"]].add((row["is_relevant"], row["label"]))
    assert all(len(labels) == 1 for labels in group_labels.values())
