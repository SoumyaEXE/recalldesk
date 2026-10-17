"""Optional: download the trained LoRA from Tinker and convert it to a PEFT adapter for local serving.

    python -m ml.download_adapter [--path tinker://.../sampler_weights/...] [--out ml/results/adapter] [--peft]

Uses tinker_cookbook.weights.download and weights.build_lora_adapter (PEFT format for vLLM `--lora-modules`,
SGLang or PEFT; then point RECALLDESK_MODEL_PROVIDER=openai at that server). Adapter files are gitignored.
"""
from __future__ import annotations

import argparse

from ml.common import RESULTS, STUDENT_MODEL, require_key, tinker_model_path, utf8_stdout


def main() -> None:
    utf8_stdout()
    ap = argparse.ArgumentParser()
    ap.add_argument("--path", default=None)
    ap.add_argument("--out", default=str(RESULTS / "adapter"))
    ap.add_argument("--peft", action="store_true", help="also convert to PEFT format (<out>-peft)")
    args = ap.parse_args()
    require_key("TINKER_API_KEY", "adapter download")
    from tinker_cookbook import weights

    path = args.path or tinker_model_path()
    if not path:
        raise SystemExit("no model path - run python -m ml.train_tinker first")
    d = weights.download(tinker_path=path, output_dir=args.out)
    print("downloaded Tinker adapter to", d)
    if args.peft:
        out = args.out.rstrip("/\\") + "-peft"
        weights.build_lora_adapter(base_model=STUDENT_MODEL, adapter_path=d, output_path=out)
        print("PEFT adapter written to", out)


if __name__ == "__main__":
    main()
