"""Teacher-labelling worker.

Takes every command whose 0-based line number n satisfies n % SHARD_COUNT == SHARD_INDEX,
asks the teacher, and writes {"id", "text", "teacher_raw"} lines to
s3://datasets/teacher/shard-<SHARD_INDEX>.jsonl. Progress is flushed every FLUSH_EVERY
records, and a restarted worker resumes from what is already stored.
"""
import os
import sys

from botocore.exceptions import ClientError

from common import ask_teacher, read_jsonl_bytes, s3, to_jsonl_bytes

BUCKET = os.environ.get("BUCKET", "datasets")
POOL_KEY = os.environ.get("POOL_KEY", "commands_pool.jsonl")


def shard_rows(rows, index, count):
    return [r for n, r in enumerate(rows) if n % count == index]


def main():
    index, count = int(os.environ["SHARD_INDEX"]), int(os.environ["SHARD_COUNT"])
    if not 0 <= index < count:
        sys.exit("need 0 <= SHARD_INDEX < SHARD_COUNT")
    flush_every = int(os.environ.get("FLUSH_EVERY", "25"))
    out_key = f"teacher/shard-{index}.jsonl"
    client = s3()
    pool = read_jsonl_bytes(client.get_object(Bucket=BUCKET, Key=POOL_KEY)["Body"].read())
    mine = shard_rows(pool, index, count)
    try:
        done = read_jsonl_bytes(client.get_object(Bucket=BUCKET, Key=out_key)["Body"].read())
    except ClientError:
        done = []
    done_ids = {r["id"] for r in done}
    print(f"shard {index}/{count}: {len(mine)} commands, {len(done_ids)} already done", flush=True)
    for i, row in enumerate(mine):
        if row["id"] in done_ids:
            continue
        done.append({"id": row["id"], "text": row["text"], "teacher_raw": ask_teacher(row["text"])})
        if len(done) % flush_every == 0:
            client.put_object(Bucket=BUCKET, Key=out_key, Body=to_jsonl_bytes(done))
            print(f"shard {index}: {len(done)}/{len(mine)}", flush=True)
    client.put_object(Bucket=BUCKET, Key=out_key, Body=to_jsonl_bytes(done))
    print(f"shard {index}: finished, {len(done)} records in s3://{BUCKET}/{out_key}", flush=True)


if __name__ == "__main__":
    main()
