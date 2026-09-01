"""C-lite (a) 규칙 축 — 숫자 대조·부정어 극성 단위 + trace 키. [새봄]

(a) 규칙 단위·trace 키: 인라인 케이스만 쓴다 — fixture·env·네트워크 무관.
(b) SSOT 재현: 판정 CSV 는 레포 밖(C:\IT\moguk-measure\2026-09-01\c-lite\)이
    단일 출처다. env C_LITE_JUDGED_CSV 로 경로를 준 실행에서만 돌고,
    미설정이면 skip 한다 — CSV 를 레포로 반입하지 않는다.

LLM·네트워크·스텁 사용 없음.
"""

import csv
import io
import os
from pathlib import Path

import pytest

from app.agents import graph as graph_mod
from app.agents.neg_lexicon import KO_NEG_LEXICON, ko_neg
from app.agents.num_compare import num_compare, num_tokens
from app.agents.verify import Verify

# ---------------------------------------------------------------- (a) 규칙 단위

# 숫자가 바뀐 쌍 (src, back, src_only, back_only) — 되번역이 자릿수·배수를 틀린 경우
NUM_HIT = [
    ("공작물은 척 조에서 20 mm 이상 물려야 한다.", "200mm 이상 고정해야 한다.", ["20"], ["200"]),
    ("금형 간격을 8 mm 이하로 하십시오.", "금형 간격을 80mm 이하로 유지하세요.", ["8"], ["80"]),
    ("급정지 시간이 320 ms 를 넘으면 정비하십시오.", "정지 시간이 3200 ms 를 넘으면 점검하세요.", ["320"], ["3200"]),
    ("돌출 길이는 생크 높이의 1~1.5배로 하십시오.", "길이는 몸통 높이의 1~2.5배이다.", ["1.5"], ["2.5"]),
    ("1회마다 스위치에서 발을 떼십시오.", "각 압착 후에는 발을 떼야 합니다.", ["1"], []),
]

# 부정어 극성이 바뀐 쌍 (src, back, src_hits, back_hits)
NEG_HIT = [
    ("상·하 금형 사이에 손을 넣지 마십시오.", "손을 상부 금형과 하부 금형 사이에 넣으세요.", 1, 0),
    ("광전자식 방호장치를 가리거나 위치를 옮기지 마십시오.", "광전 보호 장치를 가리거나 이동시켜 주세요.", 1, 0),
    ("금형을 교체할 때는 반드시 안전블록을 끼우십시오.", "교체 시 안전블록을 설치할 필요가 없습니다.", 0, 1),
    ("칩은 날카로우므로 맨손으로 잡지 마십시오.", "칩이 뜨거우니 손으로 직접 잡아야 합니다.", 1, 0),
]

# 정상 쌍 — 표현만 달라지고 숫자·극성은 보존
NO_HIT = [
    ("금형은 25 kg 이상이면 동력운반기를 쓰십시오.", "25kg 이상의 금형은 기계식 운반 장비를 사용해야 합니다."),
    ("회전 부위에는 손을 대지 않습니다.", "회전 중인 부품에 손을 대지 마세요."),
]


def test_lexicon_single_source():
    """사전은 seed_check 가 아니라 공유 모듈이 갖는다(D13-A)."""
    assert KO_NEG_LEXICON.pattern.startswith("(지")
    assert ko_neg("손을 대지 마십시오.") == 1
    assert ko_neg("손을 대세요.") == 0
    assert ko_neg("안전블록이 없다면 아니다") == 2


def test_num_tokens_rules():
    """천단위 제거 · 범위 2토큰 · 단위 미포함 · 문말 마침표 배제."""
    assert num_tokens("1,200 kg") == ["1200"]
    assert num_tokens("1~1.5배") == ["1", "1.5"]
    assert num_tokens("20 mm 이상") == ["20"]
    assert num_tokens("320 ms 를 넘으면.") == ["320"]
    assert num_tokens("숫자 없음") == []


def test_num_normalizes_decimal():
    assert num_compare("8 mm", "8.0mm")["mismatch"] is False


@pytest.mark.parametrize("src,back,src_only,back_only", NUM_HIT)
def test_num_detects(src, back, src_only, back_only):
    m = num_compare(src, back)
    assert m["mismatch"] is True
    assert m["src_only"] == src_only
    assert m["back_only"] == back_only


@pytest.mark.parametrize("src,back,ns,nb", NEG_HIT)
def test_neg_detects(src, back, ns, nb):
    r = graph_mod._rule_trace(src, back)
    assert (r["neg"]["src"], r["neg"]["back"]) == (ns, nb)
    assert r["neg"]["hit"] is True
    assert r["neg"]["delta"] == nb - ns


@pytest.mark.parametrize("src,back", NO_HIT)
def test_no_false_hit(src, back):
    r = graph_mod._rule_trace(src, back)
    assert r["num"]["mismatch"] is False
    assert r["neg"]["hit"] is False


# ---------------------------------------------------------------- trace 키

def _bt(back_text):
    return Verify(score=0.9, passed=True, score_src=0.9, score_aux=0.8,
                  back_text=back_text, back_ms=12)


def test_trace_keys_present():
    t = graph_mod._backtrans_trace(
        _bt("금형 간격을 80mm 이하로 유지하세요."),
        high_risk=True, src_kind="question", chunks_joined="",
        src_text="금형 간격을 8 mm 이하로 하십시오.",
    )
    assert t["num"] == {"mismatch": True, "src_only": ["8"], "back_only": ["80"]}
    assert t["neg"] == {"src": 0, "back": 0, "delta": 0, "hit": False}
    # 기존 키는 그대로 (§3 응답 4키 무접촉)
    assert t["score_question"] == 0.9 and t["score_chunks"] == 0.8
    assert t["src_kind"] == "question" and t["high_risk"] is True
    assert t["back_ms"] == 12 and t["timed_out"] is False


def test_trace_neg_delta():
    t = graph_mod._backtrans_trace(
        _bt("손을 넣으세요."), high_risk=False, src_kind="question",
        src_text="손을 넣지 마십시오.",
    )
    assert t["neg"] == {"src": 1, "back": 0, "delta": -1, "hit": True}
    assert t["num"]["mismatch"] is False


def test_trace_keys_none_when_no_backtranslation():
    t = graph_mod._backtrans_trace(None, high_risk=False, src_kind="question")
    assert t["num"] is None and t["neg"] is None
    assert t["back_text"] is None


# ---------------------------------------------------------------- (b) SSOT 재현

JUDGED_ENV = "C_LITE_JUDGED_CSV"


def _judged_rows():
    path = os.getenv(JUDGED_ENV)
    if not path:
        pytest.skip(f"{JUDGED_ENV} 미설정 — 판정 CSV 는 레포 밖 SSOT(반입 금지)")
    p = Path(path)
    if not p.is_file():
        pytest.skip(f"{JUDGED_ENV}={path} 경로에 파일 없음")
    with io.open(p, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def _hit(row):
    r = graph_mod._rule_trace(row["src_text"], row["back_text"])
    return r["num"]["mismatch"] or r["neg"]["hit"]


def test_ssot_shape():
    rows = _judged_rows()
    assert len(rows) == 60
    assert sum(1 for r in rows if r["category"] == "normal") == 30
    for t in ("term_swap", "negation", "number"):
        assert sum(1 for r in rows if r["contam_type"] == t) == 10


def test_ssot_detection_rates():
    """2026-09-01 실측 재현 — 오염 19/30 · 정상 오탐 2/30(S18·S21) · 유형별 0/9/10."""
    rows = _judged_rows()
    contam = [r for r in rows if r["category"] == "contam"]
    normal = [r for r in rows if r["category"] == "normal"]
    assert sum(1 for r in contam if _hit(r)) == 19
    assert [r["case_id"] for r in normal if _hit(r)] == ["S18", "S21"]
    by_type = {t: sum(1 for r in contam if r["contam_type"] == t and _hit(r))
               for t in ("term_swap", "negation", "number")}
    assert by_type == {"term_swap": 0, "negation": 9, "number": 10}
