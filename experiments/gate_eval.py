"""측정 #3 — 백트랜슬레이션 게이트 검출률 (07 재생성 testset 기준: 오염셋 vs 기준셋) → τ 확정 (M-10a). [명선+새봄]

입력
  testset/sentences_30.json  기준셋 — items[].ko(한국어 원문) · answer_vi(정답 번역, draft)
  testset/corrupted_30.json  오염셋 — items[].base_id · type · corrupted_vi

채점
  각 행을 backend 의 agents.verify.verify_backtranslation 으로 그대로 태운다(어댑터 경유 —
  되번역 local complete() 1회 + bge-m3 embed 1회 + 코사인). src = ko 원문 고정(M-34 c ② 기본축),
  기본값은 aux_src 미지정 → score_chunks 는 항상 null(오프라인엔 근거 청크 본문이 없다, Q3).

  --online-chunks 를 주면 근거축을 함께 잰다: ko 원문으로 retrieve(k=4) 한 청크를 graph 와 같은
  build_context() 로 묶어 aux_src 로 넘긴다. 게이트 축은 여전히 src(question) — gate_on 은 바꾸지
  않는다. DB·임베딩이 붙는 환경에서만 동작하며, 근거축 집계는 score_chunks 가 산출된 행만 센다.

표본 불균형 (읽을 때 주의)
  오염셋은 term_swap 30 / negation 20 / number 10 이다. number 는 base 의 answer_vi 에 숫자
  토큰이 있어야 rules.number("숫자만 변경")를 지킬 수 있는데 그런 문장이 9개뿐이라 10건이 상한이다
  (corrupted_30.json _meta.number_limit). 유형별 검출률은 by_type 과 n_by_type 을 함께 읽는다.

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
from app.agents.graph import build_context                         # noqa: E402
from app.agents.retrieve import retrieve                           # noqa: E402
from app.services import llm_adapter                               # noqa: E402

TESTSET = Path(__file__).resolve().parent / "testset"
OUT_DIR = Path(__file__).resolve().parent / "out"

SRC_KIND = "question"                 # M-34 c ② 기본축. 게이트 축은 --online-chunks 여부와 무관
RETRIEVE_K = 4                        # §3 sources 와 동수 — graph 의 근거 청크 수를 맞춘다
TAU_START, TAU_STOP, TAU_STEP = 0.50, 0.95, 0.05

# 집계에서 빼는 장애 분류 — 게이트 판정이 아니라 실행 실패인 행
EXCLUDED_CLASSES = {"local_failed", "retrieve_error"}

COLUMNS = [
    "id", "base_id", "variant_type", "safety", "src_kind", "ko_src", "vi_text",
    "back_text", "score_question", "score_chunks", "n_chunks", "back_ms", "timed_out",
    "error", "error_class", "chunks_error",
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


def fetch_context(query: str) -> tuple[str | None, int, str]:
    """--online-chunks 용 근거축 — graph 와 같은 retrieve→build_context 경로.

    반환 (context, n_chunks, error). 조회 실패는 그 행의 근거축만 포기하고(질문축은 그대로 잰다)
    chunks_error 에 사유를 남긴다 — 근거축 집계에서만 빠진다.
    """
    try:
        chunks = retrieve(query, k=RETRIEVE_K)
    except Exception as exc:                      # DB·임베딩 장애 — 행 전체를 버리지 않는다
        return None, 0, f"{type(exc).__name__}: {exc}"
    return (build_context(chunks) if chunks else None), len(chunks), ""


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
    # --online-chunks 를 DB 없이 형식만 확인할 수 있게 근거축도 결정적 mock 으로 대체한다.
    globals()["fetch_context"] = lambda query: (
        f"[1] 문서 0 · dry-run 근거\n{query}", RETRIEVE_K, "",
    )


def score_rows(rows: list[dict], *, online_chunks: bool = False) -> list[dict]:
    out = []
    for row in rows:
        aux, n_chunks, chunks_error = (None, 0, "")
        if online_chunks:
            aux, n_chunks, chunks_error = fetch_context(row["ko_src"])
        # gate_on 은 넘기지 않는다 — 게이트 축은 M-34 c ② 기본축(src) 고정, aux 는 측정만 한다.
        v = verify_mod.verify_backtranslation(row["ko_src"], row["vi_text"], aux_src=aux)
        out.append({
            **row,
            "src_kind": SRC_KIND,
            "back_text": v.back_text,
            "score_question": v.score_src,
            "score_chunks": v.score_aux,          # aux_src 미지정이면 None
            "n_chunks": n_chunks,
            "back_ms": v.back_ms,
            "timed_out": v.timed_out,
            "error": v.error or "",
            "error_class": classify_error(v.error),
            "chunks_error": chunks_error,
        })
    return out


def taus() -> list[float]:
    n = round((TAU_STOP - TAU_START) / TAU_STEP) + 1
    return [round(TAU_START + i * TAU_STEP, 2) for i in range(n)]


def _sweep(normals: list[dict], corrupts: list[dict], key: str) -> list[dict]:
    """τ 스윕 1축 — 검출률·오탐률·유형별 검출률. 분모가 0이면 null 로 남긴다."""
    types = sorted({r["variant_type"] for r in corrupts})
    rate = lambda rs, tau: (                                        # noqa: E731
        round(sum(1 for r in rs if r[key] < tau) / len(rs), 4) if rs else None
    )
    return [
        {
            "tau": t,
            "detection_rate": rate(corrupts, t),                    # 오염에서 passed=False 비율
            "false_positive_rate": rate(normals, t),                # 정상에서 passed=False 비율
            "by_type": {ty: rate([r for r in corrupts if r["variant_type"] == ty], t)
                        for ty in types},
        }
        for t in taus()
    ]


def _count_by_type(rows: list[dict]) -> dict:
    out: dict[str, int] = {}
    for r in rows:
        out[r["variant_type"]] = out.get(r["variant_type"], 0) + 1
    return dict(sorted(out.items()))


def summarize(scored: list[dict]) -> dict:
    usable = [r for r in scored if r["error_class"] not in EXCLUDED_CLASSES
              and r["score_question"] is not None]
    excluded = len(scored) - len(usable)
    normals = [r for r in usable if r["variant_type"] == "normal"]
    corrupts = [r for r in usable if r["variant_type"] != "normal"]

    # 근거축 — --online-chunks 로 score_chunks 가 실제로 산출된 행만 센다(질문축 집계와 독립).
    aux = [r for r in scored if r["error_class"] not in EXCLUDED_CLASSES
           and r.get("score_chunks") is not None]
    aux_normals = [r for r in aux if r["variant_type"] == "normal"]
    aux_corrupts = [r for r in aux if r["variant_type"] != "normal"]

    summary = {
        "n_rows": len(scored),
        "n_excluded": excluded,
        "n_usable": len(usable),
        "n_normal": len(normals),
        "n_corrupted": len(corrupts),
        "n_by_type": _count_by_type(usable),        # 유형별 표본수 — 검출률과 함께 읽는다
        "excluded_classes": sorted(EXCLUDED_CLASSES),
        "sample_note": (
            "표본 불균형 — number 는 10건이 상한이다(corrupted_30.json _meta.number_limit). "
            "유형별 검출률은 n_by_type 과 함께 읽는다."
        ),
        "by_tau": _sweep(normals, corrupts, "score_question"),
        "n_chunks_scored": len(aux),
        "by_tau_chunks": _sweep(aux_normals, aux_corrupts, "score_chunks") if aux else None,
    }
    return summary


def _print_sweep(by_tau: list[dict], title: str) -> None:
    types = list(by_tau[0]["by_type"]) if by_tau else []
    print(f"  [{title}]")
    print("  τ     검출률  오탐률  " + "  ".join(f"{t:>10}" for t in types))
    for row in by_tau:
        fmt = lambda v: "  n/a " if v is None else f"{v:6.3f}"      # noqa: E731
        print(f"  {row['tau']:.2f}  {fmt(row['detection_rate'])}  {fmt(row['false_positive_rate'])}  "
              + "  ".join(f"{fmt(row['by_type'][t]):>10}" for t in types))


def print_summary(s: dict) -> None:
    print(f"행 {s['n_rows']} / 집계 제외 {s['n_excluded']} ({', '.join(s['excluded_classes'])}) "
          f"/ 유효 {s['n_usable']} (정상 {s['n_normal']} · 오염 {s['n_corrupted']})")
    print("  유형별 표본: " + " · ".join(f"{k} {v}" for k, v in s["n_by_type"].items()))
    print(f"  ※ {s['sample_note']}")
    _print_sweep(s["by_tau"], "질문축 score_question — 게이트 판정축")
    if s.get("by_tau_chunks"):
        print(f"  근거축 표본 {s['n_chunks_scored']} 행 (--online-chunks)")
        _print_sweep(s["by_tau_chunks"], "근거축 score_chunks — 참고(게이트 판정축 아님)")


def main() -> None:
    ap = argparse.ArgumentParser(description="측정 #3 — 게이트 검출률 → τ 확정 (M-10a)")
    ap.add_argument("--dry-run", action="store_true",
                    help="LLM·임베딩을 결정적 mock 으로 대체 (점수는 더미 — 형식 확인용)")
    ap.add_argument("--online-chunks", action="store_true",
                    help="ko 원문으로 retrieve(k=4) 한 근거 청크를 aux_src 로 함께 채점 "
                         "(DB·임베딩 필요. 게이트 판정축은 질문축 그대로)")
    ap.add_argument("--limit", type=int, default=None, help="선두 N 행만")
    ap.add_argument("--out", type=Path, default=None, help="CSV 경로 (기본 out/gate_eval_<ts>.csv)")
    args = ap.parse_args()

    if args.dry_run:
        install_dry_run()

    rows = load_rows(args.limit)
    scored = score_rows(rows, online_chunks=args.online_chunks)

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
