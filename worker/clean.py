"""Clean the teacher shards into datasets/v1/train.jsonl (+ train.sha256).

Usage: python worker/clean.py [--local DIR] [--out DIR]
  --local DIR  read DIR/shard-*.jsonl instead of s3://datasets/teacher/, and write to --out (default datasets/v1)

Rejects, in this order: (a) not valid JSON, (b) keys not exactly intent/date/time/place,
(c) intent not one of the eight, (d) a slot that is neither null nor text found in the command,
(e) duplicate command text (the smallest id is kept). Output is in id order.
"""
import argparse
import hashlib
import json
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

KEYS = {"intent", "date", "time", "place"}
INTENTS = {"alarm_set", "alarm_query", "calendar_set", "calendar_query", "calendar_remove",
           "weather_query", "datetime_query", "recommendation_events"}


def reject_reason(text, raw):
    """Return 'a'..'d' if the reply must be rejected, else (None, parsed)."""
    try:
        obj = json.loads(raw.strip())
    except (json.JSONDecodeError, AttributeError):
        return "a", None
    if not isinstance(obj, dict) or set(obj) != KEYS:
        return "b", None
    if obj["intent"] not in INTENTS:
        return "c", None
    for k in ("date", "time", "place"):
        v = obj[k]
        if v is not None and not (isinstance(v, str) and v.strip() and v.lower() in text.lower()):
            return "d", None
    return None, obj


def clean(records):
    counts = {"input": len(records), "a": 0, "b": 0, "c": 0, "d": 0, "duplicates": 0, "kept": 0}
    seen, kept = set(), []
    for r in sorted(records, key=lambda r: r["id"]):
        reason, obj = reject_reason(r["text"], r["teacher_raw"])
        if reason:
            counts[reason] += 1
            continue
        key = " ".join(r["text"].lower().split())
        if key in seen:
            counts["duplicates"] += 1
            continue
        seen.add(key)
        # keep the teacher reply text exactly as generated (only surrounding whitespace removed)
        kept.append({"id": r["id"], "text": r["text"], "target": r["teacher_raw"].strip()})
    counts["kept"] = len(kept)
    return kept, counts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--local", help="read shard-*.jsonl from this directory instead of S3")
    ap.add_argument("--out", default="datasets/v1", help="output directory in --local mode")
    a = ap.parse_args()
    from common import read_jsonl_bytes, to_jsonl_bytes
    if a.local:
        records = []
        for p in sorted(pathlib.Path(a.local).glob("shard-*.jsonl")):
            records += read_jsonl_bytes(p.read_bytes())
    else:
        from common import s3
        client = s3()
        keys = [o["Key"] for o in client.list_objects_v2(Bucket="datasets", Prefix="teacher/shard-").get("Contents", [])]
        records = []
        for k in sorted(keys):
            records += read_jsonl_bytes(client.get_object(Bucket="datasets", Key=k)["Body"].read())
    ids = [r["id"] for r in records]
    if len(ids) != len(set(ids)):
        sys.exit("an id appears in more than one shard record")
    kept, counts = clean(records)
    body = to_jsonl_bytes(kept)
    digest = hashlib.sha256(body).hexdigest()
    sha_line = f"{digest}  train.jsonl\n".encode()
    if a.local:
        os.makedirs(a.out, exist_ok=True)
        pathlib.Path(a.out, "train.jsonl").write_bytes(body)
        pathlib.Path(a.out, "train.sha256").write_bytes(sha_line)
    else:
        client.put_object(Bucket="datasets", Key="v1/train.jsonl", Body=body)
        client.put_object(Bucket="datasets", Key="v1/train.sha256", Body=sha_line)
    os.makedirs("results", exist_ok=True)
    pathlib.Path("results/clean_counts.json").write_text(json.dumps(counts, indent=2) + "\n")
    print(json.dumps(counts, indent=2))
    print("sha256", digest)
    assert counts["input"] == counts["a"] + counts["b"] + counts["c"] + counts["d"] + counts["duplicates"] + counts["kept"]


if __name__ == "__main__":
    main()
