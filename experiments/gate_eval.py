"""측정 #3 — 백트랜슬레이션 게이트 검출률 (07 재생성 testset 기준: 오염셋 vs 기준셋) → τ 확정 (M-10a). [명선+새봄]

입력
  testset/sentences_30.json  기준셋 — items[].ko(한국어 원문) · answer_vi(정답 번역, draft)
  testset/corrupted_30.json  오염셋 — items[].base_id · type · corrupted_vi

채점
  각 행을 backend 의 agents.verify.verify_backtranslation 으로 그대로 태운다(어댑터 경유 —
  되번역 local complete() 1회 + bge-m3 embed 1회 + 코사인). src = ko 원문 고정(M-34 c ② 기본축),
  aux_src 는 주지 않는다 → score_chunks 는 항상 null(오프라인엔 근거 청크 본문이 없다, Q3).

장애 분류 제외 (온라인 분석도 같은 규칙)
  "grounded=false ∧ 장애 분류 제외" — 게이트 성능은 점수가 실제로 산출된 행에서만 센다.
  오프라인에서 grounded 개념에 대응하는 것은 되번역 실패다: error_class ∈ {local_failed,
  retrieve_error} 인 행(되번역 타임아웃·LLM 오류 등)은 검출률·오탐률 집계에서 뺀다.
  제외 후 남은 표본 수(n)를 요약에 함께 적는다.

출력
  experiments/out/gate_eval_<ts>.csv  행 단위 실측
  stdout + gate_eval_<ts>.summary.json  τ 0.50~0.95(step 0.05) 별 검출률·오탐률·유형별 검출률
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.agents import verify as verify_mod                        # noqa: E402
from app.services import llm_adapter                               # noqa: E402

TESTSET = Path(__file__).resolve().parent / "testset"
OUT_DIR = Path(__file__).resolve().parent / "out"

SRC_KIND = "question"                 # M-34 c ② 기본축. 오프라인은 이 축 단독(Q3)
TAU_START, TAU_STOP, TAU_STEP = 0.50, 0.95, 0.05

# 집계에서 빼는 장애 분류 — 게이트 판정이 아니라 실행 실패인 행
EXCLUDED_CLASSES = {"local_failed", "retrieve_error"}

COLUMNS = [
    "id", "base_id", "variant_type", "safety", "src_kind", "ko_src", "vi_text",
    "back_text", "score_question", "score_chunks", "back_ms", "timed_out",
    "error", "error_class",
]


def classify_error(error: str | None) -> str:
    """Verify.error → 집계용 분류. 되번역이 성립한 행은 빈 문자열."""
    if not error:
        return ""
    if error.startswith("local_failed") or error in {"no_budget", "empty_backtranslation"}:
        return "local_failed"
    if error.startswith("embed_failed"):
        return "retrieve_error"          # 임베딩 = 검색축 실패 — 게이트 판정 불가
    return "other"


def load_rows(limit: int | None = None) -> list[dict]:
    sentences = json.loads((TESTSET / "sentences_30.json").read_text(encoding="utf-8"))["items"]
    corrupted = json.loads((TESTSET / "corrupted_30.json").read_text(encoding="utf-8"))["items"]
    by_id = {s["id"]: s for s in sentences}

    rows = [
        {
            "id": s["id"], "base_id": s["id"], "variant_type": "normal",
            "safety": bool(s.get("safety")), "ko_src": s["ko"], "vi_text": s["answer_vi"],
        }
        for s in sentences
    ]
    for c in corrupted:
        base = by_id[c["base_id"]]
        rows.append({
            "id": c["id"], "base_id": c["base_id"], "variant_type": c["type"],
            "safety": bool(base.get("safety")), "ko_src": base["ko"],
            "vi_text": c["corrupted_vi"],
        })
    return rows[:limit] if limit else rows


# ── dry-run mock — 결정적(해시 기반). 점수는 재현용 더미이지 실측치가 아니다 ──
def _fake_vector(text: str) -> list[float]:
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    return [b / 255.0 for b in digest[:16]]


def install_dry_run() -> None:
    verify_mod.complete = lambda prompt, tier, timeout_s=None: llm_adapter.LLMResult(
        text=f"[dry-run 되번역] {prompt.splitlines()[-1][:40]}",
        tier_used="local", model="dry-run", latency_ms=1, error=None,
    )
    verify_mod.embed = lambda texts: [_fake_vector(t) for t in texts]


def score_rows(rows: list[dict]) -> list[dict]:
    out = []
    for row in rows:
        v = verify_mod.verify_backtranslation(row["ko_src"], row["vi_text"], aux_src=None)
        out.append({
            **row,
            "src_kind": SRC_KIND,
            "back_text": v.back_text,
            "score_question": v.score_src,
            "score_chunks": v.score_aux,          # 항상 None (aux_src 미지정)
            "back_ms": v.back_ms,
            "timed_out": v.timed_out,
            "error": v.error or "",
            "error_class": classify_error(v.error),
        })
    return out


def taus() -> list[float]:
    n = round((TAU_STOP - TAU_START) / TAU_STEP) + 1
    return [round(TAU_START + i * TAU_STEP, 2) for i in range(n)]


def summarize(scored: list[dict]) -> dict:
    usable = [r for r in scored if r["error_class"] not in EXCLUDED_CLASSES
              and r["score_question"] is not None]
    excluded = len(scored) - len(usable)
    normals = [r for r in usable if r["variant_type"] == "normal"]
    corrupts = [r for r in usable if r["variant_type"] != "normal"]
    types = sorted({r["variant_type"] for r in corrupts})

    rate = lambda rs, tau: (                                        # noqa: E731
        round(sum(1 for r in rs if r["score_question"] < tau) / len(rs), 4) if rs else None
    )
    return {
        "n_rows": len(scored),
        "n_excluded": excluded,
        "n_usable": len(usable),
        "n_normal": len(normals),
        "n_corrupted": len(corrupts),
        "excluded_classes": sorted(EXCLUDED_CLASSES),
        "by_tau": [
            {
                "tau": t,
                "detection_rate": rate(corrupts, t),                # 오염에서 passed=False 비율
                "false_positive_rate": rate(normals, t),            # 정상에서 passed=False 비율
                "by_type": {ty: rate([r for r in corrupts if r["variant_type"] == ty], t)
                            for ty in types},
            }
            for t in taus()
        ],
    }


def print_summary(s: dict) -> None:
    print(f"행 {s['n_rows']} / 집계 제외 {s['n_excluded']} ({', '.join(s['excluded_classes'])}) "
          f"/ 유효 {s['n_usable']} (정상 {s['n_normal']} · 오염 {s['n_corrupted']})")
    types = list(s["by_tau"][0]["by_type"]) if s["by_tau"] else []
    print("  τ     검출률  오탐률  " + "  ".join(f"{t:>10}" for t in types))
    for row in s["by_tau"]:
        fmt = lambda v: "  n/a " if v is None else f"{v:6.3f}"      # noqa: E731
        print(f"  {row['tau']:.2f}  {fmt(row['detection_rate'])}  {fmt(row['false_positive_rate'])}  "
              + "  ".join(f"{fmt(row['by_type'][t]):>10}" for t in types))


def main() -> None:
    ap = argparse.ArgumentParser(description="측정 #3 — 게이트 검출률 → τ 확정 (M-10a)")
    ap.add_argument("--dry-run", action="store_true",
                    help="LLM·임베딩을 결정적 mock 으로 대체 (점수는 더미 — 형식 확인용)")
    ap.add_argument("--limit", type=int, default=None, help="선두 N 행만")
    ap.add_argument("--out", type=Path, default=None, help="CSV 경로 (기본 out/gate_eval_<ts>.csv)")
    args = ap.parse_args()

    if args.dry_run:
        install_dry_run()

    rows = load_rows(args.limit)
    scored = score_rows(rows)

    ts = time.strftime("%Y%m%d_%H%M%S")
    out_csv = args.out or (OUT_DIR / f"gate_eval_{ts}.csv")
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with out_csv.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNS)
        w.writeheader()
        for r in scored:
            w.writerow({k: r[k] for k in COLUMNS})

    summary = summarize(scored)
    summary_path = out_csv.with_suffix(".summary.json")
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"CSV     : {out_csv}")
    print(f"summary : {summary_path}")
    if args.dry_run:
        print("※ --dry-run — 점수는 해시 기반 더미다. 검출률 수치에 의미 없음(형식 확인 전용).")
    print_summary(summary)


if __name__ == "__main__":
    main()
