"""측정 #3 게이트 평가 스크립트 — dry-run 형식·집계 규칙·근거축 (M-10a). [새봄]

오염셋 확장(30→60) 후에도 기대값은 테스트셋 실물에서 뽑는다 — 배분이 바뀌면 테스트가 따라간다.
"""

import csv
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "experiments"))

import gate_eval  # noqa: E402

TESTSET = ROOT / "experiments" / "testset"


def _expected_counts() -> dict:
    """기대값은 테스트셋 실물에서 뽑는다 — 오염셋이 늘어도 테스트가 따라간다."""
    sents = json.loads((TESTSET / "sentences_30.json").read_text(encoding="utf-8"))["items"]
    corr = json.loads((TESTSET / "corrupted_30.json").read_text(encoding="utf-8"))["items"]
    counts = {"normal": len(sents)}
    for c in corr:
        counts[c["type"]] = counts.get(c["type"], 0) + 1
    return counts


def test_dry_run_writes_csv_with_expected_shape(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["gate_eval", "--dry-run", "--out", str(tmp_path / "g.csv")])
    gate_eval.main()

    out = tmp_path / "g.csv"
    rows = list(csv.DictReader(out.open(encoding="utf-8")))
    counts = _expected_counts()

    assert len(rows) == sum(counts.values())              # 정상 + 오염 전건
    assert list(rows[0]) == gate_eval.COLUMNS             # 컬럼 집합·순서
    got = {}
    for r in rows:
        got[r["variant_type"]] = got.get(r["variant_type"], 0) + 1
    assert got == counts                                  # 유형별 실배분값

    # src 축·근거축 규약 (Q3)
    assert {r["src_kind"] for r in rows} == {"question"}
    assert {r["score_chunks"] for r in rows} == {""}      # aux_src 미지정 → 항상 null
    assert all(r["score_question"] for r in rows)         # 점수 산출됨
    assert all(r["error"] == "" for r in rows)            # dry-run 은 실패 0

    summary = json.loads((tmp_path / "g.summary.json").read_text(encoding="utf-8"))
    assert summary["n_rows"] == len(rows)
    assert [t["tau"] for t in summary["by_tau"]] == gate_eval.taus()
    assert gate_eval.taus()[0] == 0.50 and gate_eval.taus()[-1] == 0.95


def test_limit_flag_truncates(tmp_path, monkeypatch):
    monkeypatch.setattr(
        sys, "argv", ["gate_eval", "--dry-run", "--limit", "7", "--out", str(tmp_path / "g.csv")]
    )
    gate_eval.main()
    assert len(list(csv.DictReader((tmp_path / "g.csv").open(encoding="utf-8")))) == 7


@pytest.mark.parametrize(
    "error, expected",
    [
        (None, ""),
        ("", ""),
        ("local_failed[qwen3:8b:timeout]", "local_failed"),
        ("no_budget", "local_failed"),
        ("empty_backtranslation", "local_failed"),
        ("embed_failed[RuntimeError]", "retrieve_error"),
        ("empty_input", "other"),
    ],
)
def test_error_classification(error, expected):
    assert gate_eval.classify_error(error) == expected


def test_failed_rows_are_excluded_from_rates():
    """장애 분류(local_failed·retrieve_error)는 검출률·오탐률 분모에서 빠진다."""
    scored = [
        {"variant_type": "normal", "score_question": 0.9, "error_class": ""},
        {"variant_type": "normal", "score_question": None, "error_class": "local_failed"},
        {"variant_type": "negation", "score_question": 0.4, "error_class": ""},
        {"variant_type": "negation", "score_question": None, "error_class": "retrieve_error"},
        {"variant_type": "term_swap", "score_question": 0.4, "error_class": "other"},
    ]
    s = gate_eval.summarize(scored)
    assert s["n_rows"] == 5
    assert s["n_excluded"] == 2                       # local_failed + retrieve_error
    assert s["n_usable"] == 3                         # other 는 남는다
    assert s["n_normal"] == 1 and s["n_corrupted"] == 2

    at80 = next(t for t in s["by_tau"] if t["tau"] == 0.80)
    assert at80["detection_rate"] == 1.0              # 오염 2건 모두 0.4 < 0.80
    assert at80["false_positive_rate"] == 0.0         # 정상 1건 0.9 ≥ 0.80


def test_corrupted_set_composition_matches_meta():
    """오염셋 확장 실물 — _meta.counts 와 items 실배분이 일치하고 규칙 전제가 유지된다."""
    corr_raw = json.loads((TESTSET / "corrupted_30.json").read_text(encoding="utf-8"))
    sents = {s["id"]: s for s in
             json.loads((TESTSET / "sentences_30.json").read_text(encoding="utf-8"))["items"]}
    items = corr_raw["items"]

    counts = {}
    for c in items:
        counts[c["type"]] = counts.get(c["type"], 0) + 1
    assert counts == corr_raw["_meta"]["counts"]      # 선언과 실물 일치
    assert counts == {"term_swap": 30, "negation": 20, "number": 10}
    assert len(items) == 60

    ids = [c["id"] for c in items]
    assert len(set(ids)) == len(ids)                  # id 유일
    prefix = {"C": "term_swap", "N": "negation", "M": "number"}
    assert all(prefix[c["id"][0]] == c["type"] for c in items)
    assert all(c["base_id"] in sents for c in items)

    # negation base 는 전건 safety:true (D13-A 전제)
    assert all(sents[c["base_id"]]["safety"] for c in items if c["type"] == "negation")
    # number 10% 상한 근거가 _meta 에 남아 있다 (판정 3항 ①)
    assert "number_limit" in corr_raw["_meta"]


def test_summary_reports_per_type_sample_sizes(tmp_path, monkeypatch):
    """유형별 검출률은 표본수와 함께 나온다 — 표본 불균형(30/20/10)을 숨기지 않는다."""
    monkeypatch.setattr(sys, "argv", ["gate_eval", "--dry-run", "--out", str(tmp_path / "g.csv")])
    gate_eval.main()

    summary = json.loads((tmp_path / "g.summary.json").read_text(encoding="utf-8"))
    counts = _expected_counts()
    assert summary["n_by_type"] == dict(sorted(counts.items()))     # 정상 포함 전 유형
    assert summary["n_by_type"]["number"] == 10
    assert sum(summary["n_by_type"].values()) == summary["n_usable"]
    assert "number" in summary["sample_note"]

    at80 = next(t for t in summary["by_tau"] if t["tau"] == 0.80)
    assert set(at80["by_type"]) == set(counts) - {"normal"}         # 오염 유형만 검출률 축
    assert summary["by_tau_chunks"] is None                         # 기본 실행은 근거축 없음
    assert summary["n_chunks_scored"] == 0


def test_online_chunks_adds_grounding_axis(tmp_path, monkeypatch):
    """--online-chunks 는 aux_src 를 채워 근거축을 낸다. 게이트 판정축은 질문축 그대로."""
    seen = {}

    def fake_verify(src, out, *, aux_src=None, **kw):
        seen["aux_src"] = aux_src
        seen["gate_on"] = kw.get("gate_on", "src")
        return real_verify(src, out, aux_src=aux_src, **kw)

    real_verify = gate_eval.verify_mod.verify_backtranslation
    monkeypatch.setattr(gate_eval.verify_mod, "verify_backtranslation", fake_verify)
    monkeypatch.setattr(
        sys, "argv",
        ["gate_eval", "--dry-run", "--online-chunks", "--limit", "6", "--out", str(tmp_path / "g.csv")],
    )
    gate_eval.main()

    assert seen["aux_src"]                              # 근거 결합문이 실제로 넘어갔다
    assert seen["gate_on"] == "src"                     # 게이트 축 미변경 (M-34 c ② 기본축)

    rows = list(csv.DictReader((tmp_path / "g.csv").open(encoding="utf-8")))
    assert len(rows) == 6
    assert all(r["score_chunks"] for r in rows)         # aux 점수 산출됨
    assert all(int(r["n_chunks"]) == gate_eval.RETRIEVE_K for r in rows)
    assert all(r["chunks_error"] == "" for r in rows)

    summary = json.loads((tmp_path / "g.summary.json").read_text(encoding="utf-8"))
    assert summary["n_chunks_scored"] == 6
    assert [t["tau"] for t in summary["by_tau_chunks"]] == gate_eval.taus()


def test_chunk_fetch_failure_keeps_row_on_question_axis(monkeypatch):
    """근거 조회 실패는 그 행의 근거축만 포기한다 — 질문축 점수는 그대로 남는다."""
    # install_dry_run 은 모듈 전역을 갈아끼운다 — 원복 지점을 monkeypatch 에 먼저 등록한다.
    monkeypatch.setattr(gate_eval.verify_mod, "complete", gate_eval.verify_mod.complete)
    monkeypatch.setattr(gate_eval.verify_mod, "embed", gate_eval.verify_mod.embed)
    monkeypatch.setitem(gate_eval.__dict__, "fetch_context", gate_eval.fetch_context)
    gate_eval.install_dry_run()
    monkeypatch.setitem(gate_eval.__dict__, "fetch_context",
                        lambda q: (None, 0, "OperationalError: connection refused"))

    rows = gate_eval.load_rows(limit=3)
    scored = gate_eval.score_rows(rows, online_chunks=True)

    assert all(r["score_question"] is not None for r in scored)     # 질문축 유지
    assert all(r["score_chunks"] is None for r in scored)           # 근거축만 비었다
    assert all(r["chunks_error"].startswith("OperationalError") for r in scored)
    assert all(r["error_class"] == "" for r in scored)              # 행 자체는 장애가 아니다

    s = gate_eval.summarize(scored)
    assert s["n_usable"] == 3 and s["n_excluded"] == 0
    assert s["n_chunks_scored"] == 0 and s["by_tau_chunks"] is None
