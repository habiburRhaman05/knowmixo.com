"""Harness entrypoint. `python -m eval.harness --config <name> [--ship-gate]`."""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from pathlib import Path

from .judge import judge
from .metrics import aggregate, ship_gate_fails
from .pipelines import _load_corpus, run_v1
from .report import render
from .schema import GoldenCase

ROOT = Path(__file__).parent
GOLDEN_ROOT = ROOT / "golden"


def _load_golden() -> list[GoldenCase]:
    cases: list[GoldenCase] = []
    for path in sorted(glob.glob(str(GOLDEN_ROOT / "**" / "*.jsonl"), recursive=True)):
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                cases.append(GoldenCase.from_dict(json.loads(line)))
    return cases


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="baseline_v1")
    parser.add_argument("--ship-gate", action="store_true")
    parser.add_argument("--out", default=None, help="write Markdown report to this path")
    parser.add_argument("--only", default=None, help="filter by bucket prefix")
    args = parser.parse_args()

    # Day 1 only supports baseline_v1 (offline fake providers). v2 lands Day 4.
    if args.config != "baseline_v1":
        print(f"[harness] Config '{args.config}' not yet wired (Day 1 ships baseline_v1 only).")
        return 2

    cases = _load_golden()
    if args.only:
        cases = [c for c in cases if c.bucket.startswith(args.only)]
    if not cases:
        print("[harness] No golden cases loaded.")
        return 1

    corpus = _load_corpus("acme")

    verdicts = []
    for case in cases:
        run = run_v1(case, corpus)
        verdicts.append(judge(case, run))

    metrics = aggregate(verdicts)
    report = render(args.config, verdicts, metrics)

    out_path = args.out or (ROOT.parent.parent / "launch" / "eval" / f"{args.config}.md")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    Path(out_path).write_text(report, encoding="utf-8")
    print(f"[harness] wrote {out_path}")
    print(f"[harness] cases={metrics.cases} pass={metrics.passes} pass_rate={metrics.pass_rate:.2%}")
    print(f"[harness] hit@5={metrics.hit_at_5} faithfulness={metrics.faithfulness} abstain={metrics.correct_abstention} safety={metrics.safety_correct}")

    if args.ship_gate:
        fails = ship_gate_fails(metrics)
        if fails:
            print("[harness] SHIP-GATE FAILED:")
            for f in fails:
                print(f"  - {f}")
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
