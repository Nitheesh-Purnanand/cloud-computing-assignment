"""Create the datasets and models buckets and upload commands_pool.jsonl (idempotent)."""
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "worker"))
from common import s3  # noqa: E402

client = s3()
existing = {b["Name"] for b in client.list_buckets().get("Buckets", [])}
for bucket in ("datasets", "models"):
    if bucket not in existing:
        client.create_bucket(Bucket=bucket)
client.upload_file("data/commands_pool.jsonl", "datasets", "commands_pool.jsonl")
print("buckets:", sorted(b["Name"] for b in client.list_buckets()["Buckets"]))
print("datasets:", [o["Key"] for o in client.list_objects_v2(Bucket="datasets").get("Contents", [])])
