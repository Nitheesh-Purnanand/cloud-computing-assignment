from worker import shard_rows


def test_shards_cover_every_line_exactly_once():
    rows = [{"id": f"C{i:04d}"} for i in range(103)]
    shards = [shard_rows(rows, i, 3) for i in range(3)]
    ids = [r["id"] for s in shards for r in s]
    assert sorted(ids) == sorted(r["id"] for r in rows)
    assert len(ids) == len(set(ids))
    assert shards[1][0]["id"] == "C0001" and shards[1][1]["id"] == "C0004"
