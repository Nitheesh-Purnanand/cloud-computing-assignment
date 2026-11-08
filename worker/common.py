"""Shared helpers: S3 client for SeaweedFS and the teacher call."""
import json
import os
import pathlib
import time

import boto3
import requests

PROMPT_FILE = os.environ.get("PROMPT_FILE", str(pathlib.Path(__file__).resolve().parent.parent / "prompts" / "teacher_prompt.txt"))
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
TEACHER_MODEL = os.environ.get("TEACHER_MODEL", "phi3.5")
# num_predict caps runaway replies (phi3.5 sometimes rambles for thousands of tokens); a valid reply needs ~30.
TEACHER_OPTIONS = {"temperature": 0, "seed": 42, "num_predict": 128}


def s3():
    # Credentials come from AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY (a Kubernetes Secret in the cluster).
    return boto3.client("s3", endpoint_url=os.environ.get("S3_ENDPOINT", "http://localhost:8333"),
                        region_name="us-east-1")


def read_jsonl_bytes(data):
    return [json.loads(line) for line in data.decode("utf-8").splitlines() if line.strip()]


def to_jsonl_bytes(rows):
    return "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows).encode("utf-8")


def ask_teacher(text, prompt_template=None):
    """Return the teacher's exact reply text for one command."""
    template = prompt_template or pathlib.Path(PROMPT_FILE).read_text(encoding="utf-8")
    body = {"model": TEACHER_MODEL, "prompt": template.replace("{command}", text),
            "stream": False, "options": TEACHER_OPTIONS}
    for attempt in range(5):  # Ollama sometimes answers 500 while (re)loading the model
        try:
            r = requests.post(f"{OLLAMA_URL}/api/generate", timeout=600, json=body)
            r.raise_for_status()
            return r.json()["response"]
        except requests.RequestException:
            if attempt == 4:
                raise
            time.sleep(5 * (attempt + 1))
