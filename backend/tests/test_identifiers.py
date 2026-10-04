from concurrent.futures import ThreadPoolExecutor
from uuid import RFC_4122

from app.core.identifiers import uuid7


def test_uuid7_timestamp_and_randomness(monkeypatch):
    timestamp = 1645557742000
    monkeypatch.setattr(
        "app.core.identifiers.time.time_ns", lambda: timestamp * 1_000_000
    )
    values = [uuid7() for _ in range(1000)]
    assert all(v.version == 7 and v.variant == RFC_4122 for v in values)
    assert all(v.int >> 80 == timestamp for v in values)
    assert len(set(values)) == len(values)


def test_uuid7_parallel_unique():
    with ThreadPoolExecutor(max_workers=8) as pool:
        values = list(pool.map(lambda _: uuid7(), range(5000)))
    assert len(set(values)) == len(values)
