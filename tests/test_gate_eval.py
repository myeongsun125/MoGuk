"""측정 #3 게이트 평가 스크립트 — dry-run 형식·집계 규칙 (M-10a). [새봄]"""

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
