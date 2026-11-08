# AI use

| Tool | What it was used for | How the output was checked |
|---|---|---|
| Claude Code (Anthropic, Claude Opus) | Scaffolding of the worker, `clean.py`, training/eval scripts, FastAPI service, Dockerfiles, Kubernetes manifests, Makefile, CI workflow, unit tests, and first drafts of `network/subnets.md` | Every script was run end to end on the real data/cluster; unit tests (`make test`) and `ruff`; subnet table re-derived by hand and NACL checked with `tools/nacl_sim.py` (6/6); counts in `results/clean_counts.json` checked to add up; all reported numbers come from files in `results/`, not from the assistant |

Problems found while checking AI-generated work, and fixed:

- The teacher sometimes generated thousands of tokens (seen in the Ollama log, `n_gen = 2417`), which stalled the workers; a `num_predict: 128` cap was added (temperature 0 and seed 42 unchanged).
- The first SeaweedFS settings (`-volume.max=10`, 512 MB volumes) left no free volumes for the second bucket; uploads to `models` failed with `No writable volumes`. Fixed in `k8s/10-seaweedfs.yaml`.
- `torch==2.5.1+cpu` does not exist for arm64 images; pinned `torch==2.5.1` from the CPU wheel index instead.
