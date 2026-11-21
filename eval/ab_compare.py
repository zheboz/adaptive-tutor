"""Compare two evaluation runs side by side: python -m eval.ab_compare A/runs.jsonl B/runs.jsonl"""

import json
import math
import sys

STALL_SECONDS = 30


def summary(path):
    rows = [json.loads(line) for line in open(path)]
    out = {}
    for suite in ("qa", "diagnosis"):
        for system in ("baseline", "agent"):
            chosen = [r for r in rows if r["system"] == system and (r["category"] == "diagnosis") == (suite == "diagnosis")]
            if not chosen:
                continue
            latencies = sorted(r["latency"] for r in chosen)
            calls = [s["seconds"] for r in chosen for s in r["spans"] if s["name"].startswith("model")]
            outcomes = {}
            for r in chosen:
                outcomes.setdefault(r["id"], []).append(r["passed"])
            mean = lambda key: sum(r[key] for r in chosen) / len(chosen)
            out[f"{suite} {system}"] = {
                "accuracy": f"{mean('passed'):.0%}",
                "pass@3": f"{sum(map(any, outcomes.values())) / len(outcomes):.0%}" if system == "agent" else "",
                "pass^3": f"{sum(map(all, outcomes.values())) / len(outcomes):.0%}" if system == "agent" else "",
                "turns": f"{mean('turns'):.2f}",
                "avg latency": f"{mean('latency'):.1f} s",
                "p95 latency": f"{latencies[math.ceil(0.95 * len(latencies)) - 1]:.1f} s",
                "tokens": f"{mean('tokens'):,.0f}",
                "gave up (failed)": str(sum((r["reply"] or {}).get("kind") == "failed" for r in chosen)),
                f"calls > {STALL_SECONDS} s": str(sum(c > STALL_SECONDS for c in calls)),
                "slowest call": f"{max(calls):.0f} s",
            }
    return out


def main():
    a, b = summary(sys.argv[1]), summary(sys.argv[2])
    for group in a:
        print(f"\n### {group}\n\n| Metric | A (before) | B (after) |\n|---|---|---|")
        for metric in a[group]:
            if a[group][metric]:
                print(f"| {metric} | {a[group][metric]} | {b[group][metric]} |")


if __name__ == "__main__":
    main()
