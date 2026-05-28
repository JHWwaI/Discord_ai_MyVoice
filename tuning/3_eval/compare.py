"""
Base vs Fine-tuned 비교 리포트 생성.

사용:
    python compare.py --base base_report.json --tuned tuned_report.json --out comparison.md
"""
import argparse
import json
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base",  required=True)
    ap.add_argument("--tuned", required=True)
    ap.add_argument("--out",   default="comparison.md")
    args = ap.parse_args()

    b = json.loads(Path(args.base).read_text(encoding="utf-8"))
    t = json.loads(Path(args.tuned).read_text(encoding="utf-8"))

    delta_mean = (b["cer_mean"] - t["cer_mean"]) / b["cer_mean"] * 100 if b["cer_mean"] else 0
    delta_p95  = (b["cer_p95"]  - t["cer_p95"])  / b["cer_p95"]  * 100 if b["cer_p95"]  else 0

    md = []
    md.append("# XTTS Korean Fine-Tuning — Eval Comparison\n")
    md.append("| Metric | Base | Fine-tuned | Δ |")
    md.append("|---|---|---|---|")
    md.append(f"| CER mean | {b['cer_mean']:.3%} | {t['cer_mean']:.3%} | **{delta_mean:+.1f}%** |")
    md.append(f"| CER p95  | {b['cer_p95']:.3%}  | {t['cer_p95']:.3%}  | **{delta_p95:+.1f}%** |")
    md.append(f"| Latency mean | {b['latency_mean_ms']}ms | {t['latency_mean_ms']}ms | — |")
    md.append(f"| Latency p95  | {b['latency_p95_ms']}ms  | {t['latency_p95_ms']}ms  | — |")
    md.append("")
    md.append("## 케이스별 비교\n")
    md.append("| ID | 원문 | Base 인식 | Tuned 인식 | Base CER | Tuned CER |")
    md.append("|---|---|---|---|---|---|")
    by_id = {r["id"]: r for r in t["results"]}
    for br in b["results"]:
        tr = by_id.get(br["id"], {})
        md.append(
            f"| {br['id']} | {br['ref'][:30]} | {br['hyp'][:30]} | {tr.get('hyp','')[:30]} "
            f"| {br['cer']:.2%} | {tr.get('cer',0):.2%} |"
        )

    Path(args.out).write_text("\n".join(md), encoding="utf-8")
    print(f"comparison report → {args.out}")
    print(f"CER mean: {b['cer_mean']:.3%} → {t['cer_mean']:.3%}  ({delta_mean:+.1f}%)")
    print(f"CER p95 : {b['cer_p95']:.3%} → {t['cer_p95']:.3%}   ({delta_p95:+.1f}%)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
