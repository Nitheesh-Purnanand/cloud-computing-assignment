"""Generate raw predictions for score.py.

Usage: python training/predict.py MODEL_DIR_OR_NAME data/validation.jsonl OUT.jsonl [--max-new-tokens 48]
       python training/predict.py --teacher data/validation.jsonl OUT.jsonl
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from prompting import first_line, prompt  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("args", nargs="+")
    ap.add_argument("--teacher", action="store_true")
    ap.add_argument("--max-new-tokens", type=int, default=48)
    a = ap.parse_args()
    if a.teacher:
        gold, out = a.args
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "worker"))
        from common import ask_teacher
        gen = ask_teacher
    else:
        model_dir, gold, out = a.args
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer
        torch.manual_seed(0)
        tok = AutoTokenizer.from_pretrained(model_dir)
        model = AutoModelForCausalLM.from_pretrained(model_dir).eval()

        def gen(text):
            enc = tok(prompt(text), return_tensors="pt")
            with torch.no_grad():
                o = model.generate(**enc, max_new_tokens=a.max_new_tokens, do_sample=False,
                                   pad_token_id=tok.eos_token_id)
            return first_line(tok.decode(o[0, enc["input_ids"].shape[1]:], skip_special_tokens=True))
    rows = [json.loads(line) for line in open(gold, encoding="utf-8") if line.strip()]
    with open(out, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps({"id": r["id"], "prediction": gen(r["text"])}) + "\n")
    print(f"wrote {len(rows)} predictions to {out}")


if __name__ == "__main__":
    main()
