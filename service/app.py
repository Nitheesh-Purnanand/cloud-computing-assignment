"""Command-parser inference service.

Configuration (environment): MODEL_URI (s3://bucket/prefix/), MODEL_VERSION, S3_ENDPOINT,
MAX_NEW_TOKENS, and FAULT_INJECT (1 = replace the model output with "not json").
S3 credentials come from AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY, injected from a Kubernetes Secret.
"""
import json
import logging
import os
import pathlib
import socket
import threading
import time

import boto3
import jsonschema
import torch
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from transformers import AutoModelForCausalLM, AutoTokenizer

from prompting import first_line, prompt

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("parser")

MODEL_URI = os.environ.get("MODEL_URI", "s3://models/v1/")
MODEL_VERSION = os.environ.get("MODEL_VERSION", "v1")
S3_ENDPOINT = os.environ.get("S3_ENDPOINT", "http://localhost:8333")
MAX_NEW_TOKENS = int(os.environ.get("MAX_NEW_TOKENS", "48"))
FAULT_INJECT = os.environ.get("FAULT_INJECT", "0") == "1"
SCHEMA_FILE = os.environ.get("SCHEMA_FILE", str(pathlib.Path(__file__).with_name("schema.json")))
MODEL_DIR = pathlib.Path(os.environ.get("MODEL_CACHE", "/tmp/model"))
POD_NAME = socket.gethostname()

SCHEMA = json.loads(pathlib.Path(SCHEMA_FILE).read_text())["json_schema"]
state = {"model": None, "tok": None}
infer_lock = threading.Lock()
torch.set_num_threads(int(os.environ.get("TORCH_THREADS", "1")))

app = FastAPI()


class ParseRequest(BaseModel):
    text: str


def download_model():
    bucket, _, prefix = MODEL_URI.removeprefix("s3://").partition("/")
    s3 = boto3.client("s3", endpoint_url=S3_ENDPOINT, region_name="us-east-1")
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    keys = [o["Key"] for o in s3.list_objects_v2(Bucket=bucket, Prefix=prefix).get("Contents", [])]
    files = [k for k in keys if "/" not in k[len(prefix):] and not k.endswith(".tar.gz")]
    if not files:
        raise RuntimeError(f"no model files at {MODEL_URI}")
    for k in files:
        s3.download_file(bucket, k, str(MODEL_DIR / k.rsplit("/", 1)[-1]))
    log.info("downloaded model %s (%d files) from %s at %s in %.1fs", MODEL_VERSION, len(files), MODEL_URI,
             S3_ENDPOINT, time.time() - t0)


def load():
    try:
        download_model()
        state["tok"] = AutoTokenizer.from_pretrained(MODEL_DIR)
        state["model"] = AutoModelForCausalLM.from_pretrained(MODEL_DIR).eval()
        log.info("model %s loaded, ready", MODEL_VERSION)
    except Exception:
        log.exception("model load failed")
        os._exit(1)  # let Kubernetes restart the Pod


@app.on_event("startup")
def startup():
    threading.Thread(target=load, daemon=True).start()


def generate(text):
    tok, model = state["tok"], state["model"]
    enc = tok(prompt(text), return_tensors="pt")
    with infer_lock, torch.no_grad():
        out = model.generate(**enc, max_new_tokens=MAX_NEW_TOKENS, do_sample=False, pad_token_id=tok.eos_token_id)
    return first_line(tok.decode(out[0, enc["input_ids"].shape[1]:], skip_special_tokens=True))


def validate(raw):
    """Return the parsed object if it matches schema.json, else None."""
    try:
        obj = json.loads(raw)
        jsonschema.validate(obj, SCHEMA)
        return obj
    except (json.JSONDecodeError, jsonschema.ValidationError):
        return None


def headers():
    return {"X-Model-Version": MODEL_VERSION, "X-Served-By": POD_NAME}


@app.post("/parse")
def parse(req: ParseRequest):
    if state["model"] is None:
        return JSONResponse({"error": "model_not_ready"}, status_code=503, headers=headers())
    raw = generate(req.text)
    if FAULT_INJECT:
        raw = "not json"
    obj = validate(raw)
    if obj is None:
        log.warning("invalid model output for %r: %r", req.text, raw)
        return JSONResponse({"error": "invalid_model_output"}, status_code=500, headers=headers())
    return JSONResponse(obj, headers=headers())


@app.get("/healthz")
def healthz():
    return {"status": "alive"}


@app.get("/readyz")
def readyz():
    if state["model"] is None:
        return JSONResponse({"status": "loading"}, status_code=503)
    return {"status": "ready", "model_version": MODEL_VERSION}
