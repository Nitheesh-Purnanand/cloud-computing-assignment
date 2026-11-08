"""Sequence-level distillation: fine-tune Pythia-70M on the teacher's JSON replies (CPU).

Usage: python training/train.py --config training/config.yaml [--subset N] [--out DIR]
Each example is "Command: <text>\\nJSON: <teacher reply><eos>"; the loss is computed on the reply only.
"""
import argparse
import csv
import json
import math
import os
import random
import sys
import time

os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

import numpy as np
import torch
import yaml
from transformers import AutoModelForCausalLM, AutoTokenizer, get_linear_schedule_with_warmup

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from prompting import prompt  # noqa: E402


def set_seed(seed):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.use_deterministic_algorithms(True)


def build_examples(rows, tok, max_len):
    examples = []
    for r in rows:
        p = tok(prompt(r["text"]))["input_ids"]
        t = tok(" " + r["target"])["input_ids"] + [tok.eos_token_id]
        ids = (p + t)[:max_len]
        labels = ([-100] * len(p) + t)[:max_len]
        examples.append((ids, labels))
    return examples


def collate(batch, pad_id):
    n = max(len(ids) for ids, _ in batch)
    ids = torch.full((len(batch), n), pad_id)
    labels = torch.full((len(batch), n), -100)
    mask = torch.zeros((len(batch), n), dtype=torch.long)
    for i, (x, y) in enumerate(batch):
        ids[i, :len(x)] = torch.tensor(x)
        labels[i, :len(y)] = torch.tensor(y)
        mask[i, :len(x)] = 1
    return ids, labels, mask


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="training/config.yaml")
    ap.add_argument("--subset", type=int, default=0, help="train on the first N records only")
    ap.add_argument("--out", help="output directory (default artifacts/<version>)")
    a = ap.parse_args()
    cfg = yaml.safe_load(open(a.config))
    set_seed(cfg["seed"])
    torch.set_num_threads(max(1, os.cpu_count() or 1))

    with open(cfg["train_file"], encoding="utf-8") as f:
        rows = [json.loads(line) for line in f if line.strip()][: cfg["max_train_examples"]]
    if a.subset:
        rows = rows[: a.subset]
    out = a.out or f"artifacts/{cfg['version']}" + (f"-subset{a.subset}" if a.subset else "")

    tok = AutoTokenizer.from_pretrained(cfg["base_model"])
    tok.pad_token = tok.eos_token
    model = AutoModelForCausalLM.from_pretrained(cfg["base_model"])
    examples = build_examples(rows, tok, cfg["max_seq_length"])
    bs = cfg["batch_size"]
    steps_per_epoch = math.ceil(len(examples) / bs)
    total = steps_per_epoch * cfg["epochs"]
    opt = torch.optim.AdamW(model.parameters(), lr=cfg["learning_rate"], weight_decay=cfg["weight_decay"])
    sched = get_linear_schedule_with_warmup(opt, int(cfg["warmup_ratio"] * total), total)
    rng = random.Random(cfg["seed"])
    print(f"{len(examples)} examples, {cfg['epochs']} epochs, {total} steps -> {out}", flush=True)

    losses = []
    model.train()
    for epoch in range(1, cfg["epochs"] + 1):
        order = list(range(len(examples)))
        rng.shuffle(order)
        t0, epoch_loss = time.time(), 0.0
        for s in range(steps_per_epoch):
            ids, labels, mask = collate([examples[i] for i in order[s * bs:(s + 1) * bs]], tok.pad_token_id)
            loss = model(input_ids=ids, attention_mask=mask, labels=labels).loss
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
            sched.step()
            opt.zero_grad()
            epoch_loss += loss.item()
        losses.append(epoch_loss / steps_per_epoch)
        print(f"epoch {epoch}: loss {losses[-1]:.4f} ({time.time() - t0:.0f}s)", flush=True)

    os.makedirs(out, exist_ok=True)
    model.save_pretrained(out, safe_serialization=True)
    tok.save_pretrained(out)
    json.dump({"version": cfg["version"], "base_model": cfg["base_model"], "train_examples": len(examples),
               "config": cfg}, open(os.path.join(out, "version.json"), "w"), indent=2)
    loss_file = "training/loss.csv" if not a.subset else os.path.join(out, "loss.csv")
    if cfg["version"] != "v1" and not a.subset:
        loss_file = f"training/loss_{cfg['version']}.csv"
    with open(loss_file, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["epoch", "train_loss"])
        w.writerows([[i + 1, f"{v:.6f}"] for i, v in enumerate(losses)])
    print(f"saved model to {out}, losses to {loss_file}")


if __name__ == "__main__":
    main()
