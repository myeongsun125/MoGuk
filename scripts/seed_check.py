#!/usr/bin/env python3
"""seed_check.py — V2-1 시드 초안 자동 검증 (감수 보조, 읽기 전용).

data/seed/* 와 experiments/testset/* 를 읽어 수량·구조·draft 플래그·용어 일관성·
안전 비중·오염셋 무결성·금지어·시크릿을 표(markdown)로 출력한다. 파일을 수정하지 않는다.

usage:  python scripts/seed_check.py [--base main] [--json out.json]

07 추가(M-29 근거 인용 검사 ①②③⑥⑦)는 src_checks() — 파일 말미 주석 참조. requires: pyyaml
exit :  0 = FAIL 없음 / 1 = FAIL 있음 / 2 = 필수 파일 누락
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[1]
P = {
    "glossary": ROOT / "data/seed/glossary/glossary_50.json",
    "quiz_learning": ROOT / "data/seed/quiz/quiz_learning_1.json",
    "quiz_safety": ROOT / "data/seed/quiz/quiz_safety_1.json",
    "phrases": ROOT / "data/seed/phrases/phrases_10.json",
    "special": ROOT / "data/seed/safety_courses/special_press.json",
    "lathe": ROOT / "data/seed/manuals/cnc_lathe_manual.md",
    "press": ROOT / "data/seed/manuals/press_manual.md",
    "kosha": ROOT / "data/seed/kosha/README.md",
    "sentences": ROOT / "experiments/testset/sentences_30.json",
    "corrupted": ROOT / "experiments/testset/corrupted_30.json",
    "exp_readme": ROOT / "experiments/README.md",
}

# 시드 산출물이 있어야만 수행 가능한 검사 섹션 (부재 시 SKIP 행으로 대체)
SEED_SECTIONS = ("수량·구조", "draft 플래그", "용어 일관성", "안전 비중", "오염셋 무결성", "vi 구조 대조(보조)")

ROWS: list[dict] = []


def row(section: str, item: str, status: str, detail: str = "") -> None:
    ROWS.append({"section": section, "item": item, "status": status, "detail": detail})


def load_json(key: str):
    return json.loads(P[key].read_text(encoding="utf-8"))


# ---------- 매뉴얼 파싱 ----------
FRONT = re.compile(r"^---.*?---\s*", re.S)


def strip_front(md: str) -> str:
    return FRONT.sub("", md, count=1)


def parse_sections(md: str) -> dict[str, str]:
    """'§4.1' -> 절 본문, '§4' -> 장 전체."""
    secs: dict[str, str] = {}
    cur_ch = cur_sub = None
    for line in strip_front(md).splitlines():
        m_ch = re.match(r"^## (\d+)\.", line)
        m_sub = re.match(r"^### (\d+\.\d+)", line)
        if m_ch:
            cur_ch, cur_sub = m_ch.group(1), None
            secs.setdefault(f"§{cur_ch}", "")
        elif m_sub:
            cur_sub = m_sub.group(1)
            secs.setdefault(f"§{cur_sub}", "")
        if cur_ch:
            secs[f"§{cur_ch}"] += line + "\n"
        if cur_sub:
            secs[f"§{cur_sub}"] += line + "\n"
    return secs


PARTICLES = ["에서는", "에는", "으로", "에서", "까지", "부터", "마다", "처럼", "보다",
             "은", "는", "이", "가", "을", "를", "의", "에", "로", "과", "와", "도"]
ENDINGS = ["마십시오", "하십시오", "십시오", "합니다", "입니다", "됩니다", "니다", "마세요", "하세요", "세요"]


def ko_stems(text: str) -> list[str]:
    out = []
    for tok in re.findall(r"[가-힣A-Za-z0-9.,]+", text):
        tok = tok.strip(".,")
        for e in ENDINGS:
            if tok.endswith(e) and len(tok) > len(e):
                tok = tok[: -len(e)]
                break
        for p in PARTICLES:
            if tok.endswith(p) and len(tok) - len(p) >= 2:
                tok = tok[: -len(p)]
                break
        if len(tok) >= 2:
            out.append(tok)
    return out


def lcs_len(a: str, b: str) -> int:
    """최장 공통 부분문자열 길이(문자 단위)."""
    best = 0
    prev = [0] * (len(b) + 1)
    for i in range(1, len(a) + 1):
        cur = [0] * (len(b) + 1)
        for j in range(1, len(b) + 1):
            if a[i - 1] == b[j - 1]:
                cur[j] = prev[j - 1] + 1
                if cur[j] > best:
                    best = cur[j]
        prev = cur
    return best


# ---------- 수치·부정 ----------
def ko_numbers(s: str) -> list[float]:
    s = re.sub(r"\d+행정", "", s)  # '1행정'은 어휘
    return sorted(float(x.replace(",", "")) for x in re.findall(r"\d[\d,]*(?:\.\d+)?", s))


def vi_numbers(s: str) -> list[float]:
    out = []
    for x in re.findall(r"\d[\d.,]*", s):
        x = x.strip(".,")
        if re.fullmatch(r"\d{1,3}(\.\d{3})+", x):
            x = x.replace(".", "")
        x = x.replace(",", ".")
        out.append(float(x))
    return sorted(out)


# D13-A 확정 사양: negation 판정용 언어별 부정어 사전.
# vi 사전 = không / đừng / chẳng / chưa (2026-08-29 확정)
VI_NEG_LEXICON = ("không", "đừng", "chẳng", "chưa")


def vi_neg(s: str) -> int:
    return len(re.findall(r"\b(" + "|".join(VI_NEG_LEXICON) + r")\b", s, flags=re.I))


# ko 사전 (2026-08-29 총괄 확정): 장형 부정(-지 않다/-지 못하다)·금지형(-지 말다/-여서는 안 되다)·
# 존재 부정(없다)·계사 부정(아니다) 포함. 단형 안/못, 명사 '금지', '모르다' 제외.
KO_NEG_LEXICON = re.compile(
    r"(지\s?않|지\s?못|지\s?마|지\s?말|(?:어|아|여|해|워|라|서)서는\s?(?:안|아니)\s?(?:되|됩)"
    r"|없(?=다|습|어|으|는|이|음|을|고|지)|아니(?=다|ㅂ|에|야|고|며|라|오)|아닙|아닌)")


def ko_neg(s: str) -> int:
    return len(KO_NEG_LEXICON.findall(s))


def strip_numbers(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"\d[\d.,]*", "#", s)).strip()


# ---------- 안전지시 분류 ----------
PROHIB = re.compile(r"(마십시오|마세요|않습니다|금지)")
IMPER = re.compile(r"(십시오|하세요|해야)")
SAFETY_KW = re.compile(r"(정지|멈|금지|위험|보호구|보안경|안전|비상|손|전원|차단|착용|집게|장갑|끼|잠금|LOTO|인터록|방호|덮개|블록|반드시)")


def is_safety_instruction(ko: str) -> bool:
    return bool(PROHIB.search(ko) or (IMPER.search(ko) and SAFETY_KW.search(ko)))


# ---------- 금지어 ----------
BRAND_KO = r"(삼성|두산|현대|화천|위아|포스코|한화|효성|심팩|DN솔루션즈|스맥|화낙|마작|하스|지멘스|아마다|아이다|코마츠|미쓰비시|오쿠마|하이덴하인|파낙|야스카와|보쉬|트럼프)"
BRAND_EN_I = r"\b(Fanuc|Mazak|Haas|Siemens|Amada|Aida|Komatsu|Mitsubishi|Okuma|Heidenhain|Doosan|Hyundai|Samsung|Hwacheon|Simpac|Trumpf|Bystronic|Yaskawa|Bosch|Makino|Hurco|Hardinge|Tsugami|Yamazaki|Nissei|Hanwha|Posco)\b"
BRAND_EN_CS = r"\b(LG|SK|Kia|DMG|Mori|Star|Citizen|Brother)\b"
NAME_TITLE = r"(?<![가-힣])[가-힣]{2,3}\s?(씨|님|과장|대리|주임|반장|팀장|사원|기사|부장|차장|사장|이사|선생|강사)(?![가-힣])"
TEAM_NAMES = ["명선", "새봄", "정현", "병갑", "김명선"]

SECRET_PATTERNS = [
    (r"AKIA[0-9A-Z]{16}", "AWS access key"),
    (r"ghp_[A-Za-z0-9]{20,}", "GitHub PAT"),
    (r"github_pat_[A-Za-z0-9_]{20,}", "GitHub fine-grained PAT"),
    (r"sk-[A-Za-z0-9_-]{20,}", "OpenAI-style key"),
    (r"-----BEGIN [A-Z ]*PRIVATE KEY", "private key"),
    (r"xox[bap]-[A-Za-z0-9-]+", "Slack token"),
    (r"(?i)\b(password|passwd|secret|api[_-]?key|access[_-]?token)\b\s*[:=]\s*['\"]?[A-Za-z0-9/+_\-]{8,}", "credential assignment"),
]


def paren_variants(t: str) -> list[str]:
    v = [t]
    m = re.match(r"^(.+?)\((.+)\)$", t)
    if m:
        v += [m.group(1).strip(), m.group(2).strip()]
    return v
# 시드 산출물에 의존하는 검사 묶음. 입력이 하나라도 없으면 호출하지 않는다(SKIP).
def seed_checks() -> None:
    gl = load_json("glossary")
    ql = load_json("quiz_learning")
    qs = load_json("quiz_safety")
    ph = load_json("phrases")
    sp = load_json("special")
    se = load_json("sentences")
    co = load_json("corrupted")
    lathe_md = P["lathe"].read_text(encoding="utf-8")
    press_md = P["press"].read_text(encoding="utf-8")
    manuals = {"cnc_lathe_manual.md": lathe_md, "press_manual.md": press_md}
    sections = {k: parse_sections(v) for k, v in manuals.items()}
    manual_all = strip_front(lathe_md) + "\n" + strip_front(press_md)

    # ---------------- [수량·구조] ----------------
    S = "수량·구조"
    row(S, "glossary_50 건수", "PASS" if len(gl) == 50 else "FAIL", f"{len(gl)}건")
    want = {"term_ko", "term_vi", "term_in", "note", "draft"}
    bad = [i for i, g in enumerate(gl) if set(g.keys()) != want]
    row(S, "glossary_50 필드 {term_ko,term_vi,term_in,note,draft}", "PASS" if not bad else "FAIL",
        "전 건 일치" if not bad else f"불일치 idx={bad}")
    kos = [g["term_ko"] for g in gl]
    dup = sorted({k for k in kos if kos.count(k) > 1})
    row(S, "glossary_50 term_ko 중복", "PASS" if not dup else "FAIL", "0" if not dup else str(dup))
    null_in = [g["term_ko"] for g in gl if g.get("term_in") in (None, "")]
    row(S, "glossary_50 term_in null", "INFO", f"{len(null_in)}건: {', '.join(null_in)}")

    for name, q in (("quiz_learning_1", ql), ("quiz_safety_1", qs)):
        items = q.get("items", [])
        probs = []
        for i, it in enumerate(items):
            if len(it.get("choices", [])) != 4:
                probs.append(f"#{i+1} choices={len(it.get('choices', []))}")
            if not (isinstance(it.get("answer_idx"), int) and 0 <= it["answer_idx"] <= 3):
                probs.append(f"#{i+1} answer_idx={it.get('answer_idx')}")
            if not it.get("q_vi"):
                probs.append(f"#{i+1} q_vi 없음")
        ok = len(items) == 5 and not probs
        row(S, f"{name} 5건·choices4·answer_idx∈0..3·q_vi", "PASS" if ok else "FAIL",
            f"{len(items)}건" + ("" if not probs else "; " + "; ".join(probs)))
        miss_src = []
        for i, it in enumerate(items):
            m = re.match(r"(\S+\.md)\s+(§[\d.]+)", it.get("source", ""))
            if not m or m.group(1) not in sections or m.group(2) not in sections[m.group(1)]:
                miss_src.append(f"#{i+1}:{it.get('source')}")
        row(S, f"{name} source 절 존재", "PASS" if not miss_src else "FAIL", "전 건" if not miss_src else str(miss_src))

    hr = sum(1 for p in ph if p.get("high_risk") is True)
    row(S, "phrases_10 10건·high_risk≥3", "PASS" if len(ph) == 10 and hr >= 3 else "FAIL", f"{len(ph)}건, high_risk={hr}")

    # 건수 기대값은 _meta.counts 선언을 따른다(오염셋 확장 추종, 하드코딩 폐지).
    # sentences_30 은 counts 선언이 없는 기준셋(S01~S30 정의)이라 30 을 그대로 쓴다.
    for name, d in (("sentences_30", se), ("corrupted_30", co)):
        keys = list(d.keys())
        row(S, f"{name} dict 키(구조 변경 금지)", "PASS" if len(keys) == 3 else "FAIL", f"{len(keys)}개: {keys}")
        declared = d.get("_meta", {}).get("counts")
        expected = sum(declared.values()) if declared else 30
        row(S, f"{name} items {expected}건",
            "PASS" if len(d["items"]) == expected else "FAIL", f"{len(d['items'])}건")
    sids = [s["id"] for s in se["items"]]
    dup_s = sorted({k for k in sids if sids.count(k) > 1})
    row(S, "sentences id 유일", "PASS" if not dup_s else "FAIL", "중복 0" if not dup_s else str(dup_s))
    types: dict[str, int] = {}
    for c in co["items"]:
        types[c["type"]] = types.get(c["type"], 0) + 1
    # 선언(_meta.counts)과 실배분이 정확히 같아야 한다. 선언이 없으면 기본값을 만들지 않고 FAIL.
    declared_types = co.get("_meta", {}).get("counts")
    ok = bool(declared_types) and types == declared_types
    label = ("corrupted type별 " + "/".join(str(v) for v in declared_types.values())
             if declared_types else "corrupted type별 _meta.counts 부재")
    row(S, label, "PASS" if ok else "FAIL", str(types))
    pref = {"C": "term_swap", "N": "negation", "M": "number"}
    bad_pref = [c["id"] for c in co["items"] if pref.get(c["id"][0]) != c["type"]]
    row(S, "corrupted id 접두(C/N/M)↔type", "PASS" if not bad_pref else "FAIL", "전 건 일치" if not bad_pref else str(bad_pref))
    bad_base = [c["id"] for c in co["items"] if c["base_id"] not in sids]
    row(S, "corrupted base_id ⊂ sentences id", "PASS" if not bad_base else "FAIL", "전 건 존재" if not bad_base else str(bad_base))

    row(S, 'special_press course_type="special"', "PASS" if sp.get("course_type") == "special" else "FAIL", str(sp.get("course_type")))
    row(S, "special_press required_minutes=960", "PASS" if sp.get("required_minutes") == 960 else "FAIL", str(sp.get("required_minutes")))
    refs = sp.get("content_doc_refs", [])
    ok = any("manuals/press_manual.md" in r for r in refs)
    row(S, "special_press content_doc_refs → manuals/press_manual.md", "PASS" if ok else "FAIL", "; ".join(refs))
    miss_ref = [r for r in refs + sp.get("quiz_set_refs", []) if not (ROOT / r.split("#")[0]).exists()]
    row(S, "special_press refs 파일 존재", "PASS" if not miss_ref else "FAIL", "전 건" if not miss_ref else str(miss_ref))
    cur = sp.get("curriculum", [])
    total = sum(c.get("minutes", 0) for c in cur)
    row(S, "special_press curriculum 합계=required_minutes", "PASS" if total == sp.get("required_minutes") else "FAIL",
        f"{len(cur)}단원 합계 {total}분")
    miss_cur = []
    for c in cur:
        for s_ in re.findall(r"§[\d.]+", c.get("doc_ref", "")):
            if s_ not in sections["press_manual.md"]:
                miss_cur.append(f"{c['unit']}:{s_}")
    row(S, "special_press curriculum doc_ref 절 존재", "PASS" if not miss_cur else "FAIL", "전 건" if not miss_cur else str(miss_cur))

    # ---------------- [draft 플래그] ----------------
    S = "draft 플래그"
    miss_draft = []
    for i, g in enumerate(gl):
        if g.get("draft") is not True:
            miss_draft.append(f"glossary[{i}] {g.get('term_ko')}")
    for name, q in (("quiz_learning_1", ql), ("quiz_safety_1", qs)):
        if q.get("_meta", {}).get("draft") is not True:
            miss_draft.append(f"{name}._meta")
        for i, it in enumerate(q["items"]):
            if it.get("draft") is not True:
                miss_draft.append(f"{name}.items[{i}]")
    for i, p in enumerate(ph):
        if p.get("draft") is not True:
            miss_draft.append(f"phrases[{i}] {p.get('text_ko')}")
    if se.get("_meta", {}).get("draft") is not True:
        miss_draft.append("sentences._meta")
    for s in se["items"]:
        if s.get("draft") is not True:
            miss_draft.append(f"sentences.{s['id']}")
    n_total = len(gl) + len(ql["items"]) + len(qs["items"]) + len(ph) + len(se["items"]) + 3
    row(S, "vi 텍스트 레코드 draft:true (glossary·quiz·phrases·sentences)", "PASS" if not miss_draft else "FAIL",
        f"검사 {n_total}건, 누락 {len(miss_draft)}" + ("" if not miss_draft else ": " + "; ".join(miss_draft)))
    co_item_draft = sum(1 for c in co["items"] if "draft" in c)
    row(S, "corrupted items 개별 draft 필드", "INFO",
        f"_meta.draft={co.get('_meta', {}).get('draft')} / items 개별 필드 {co_item_draft}/{len(co['items'])} (스키마에 draft 없음 — 검사 범위 외)")
    fm_ok = all(re.search(r"^draft: true", m, re.M) for m in manuals.values())
    row(S, "매뉴얼 front matter draft", "PASS" if fm_ok else "FAIL",
        ", ".join(f"{k}={'true' if re.search(r'^draft: true', v, re.M) else '없음'}" for k, v in manuals.items()))
    row(S, "special_press draft", "PASS" if sp.get("draft") is True else "FAIL", str(sp.get("draft")))

    # ---------------- [용어 일관성] ----------------
    S = "용어 일관성"
    hit, miss = [], []
    for g in gl:
        t = g["term_ko"]
        variants = paren_variants(t) + [v.strip() for v in re.split(r"[·/]", t) if len(v.strip()) >= 2]
        found = next((v for v in variants if v in manual_all), None)
        (hit if found else miss).append(t if not found or found == t else f"{t}(={found})")
    rate = f"{len(hit)}/{len(gl)} ({100*len(hit)//len(gl)}%)"
    row(S, "glossary term_ko 매뉴얼 본문 등장률", "INFO", rate)
    row(S, "glossary term_ko 매뉴얼 미등장 목록", "INFO" if not miss else "WARN", "없음" if not miss else ", ".join(miss))
    variant_hits = [h for h in hit if "(=" in h]
    if variant_hits:
        row(S, "glossary term_ko 변형 표기로만 등장", "INFO", ", ".join(variant_hits))

    ko_set = set(kos)
    miss_terms = [f"{s['id']}:{t}" for s in se["items"] for t in s.get("terms", []) if t not in ko_set]
    row(S, "sentences terms[] ⊂ glossary term_ko", "PASS" if not miss_terms else "FAIL", "전 건 존재" if not miss_terms else ", ".join(miss_terms))

    unfounded, ground_detail = [], []
    for s in se["items"]:
        m = re.match(r"(\S+\.md)\s+(§[\d.]+)", s.get("source", ""))
        doc = m.group(1) if m else None
        sec = m.group(2) if m else None
        sec_text = sections.get(doc, {}).get(sec, "") if doc else ""
        doc_text = strip_front(manuals[doc]) if doc in manuals else manual_all
        stems = ko_stems(s["ko"])
        in_sec = sum(1 for st in stems if st in sec_text)
        in_doc = sum(1 for st in stems if st in doc_text)
        r_sec = in_sec / len(stems) if stems else 0
        r_doc = in_doc / len(stems) if stems else 0
        lcs = lcs_len(s["ko"], sec_text) if sec_text else 0
        grounded = (sec_text != "") and (r_sec >= 0.5 or lcs >= 8 or r_doc >= 0.7)
        ground_detail.append((s["id"], sec_text != "", in_sec, in_doc, len(stems), lcs))
        if not grounded:
            unfounded.append(f"{s['id']}({s.get('source')}: 절일치 {in_sec}/{len(stems)}, LCS={lcs})")
    row(S, "sentences ko ↔ 매뉴얼 대응(source 절 어간 ≥50% or 공통문자열 ≥8)", "PASS" if not unfounded else "FAIL",
        f"근거 확인 {30-len(unfounded)}/30" + ("" if not unfounded else "; 무근거: " + "; ".join(unfounded)))
    weak = [f"{i} 절일치 {a}/{n} 문서일치 {b}/{n} LCS={l}" for i, ok_, a, b, n, l in ground_detail if l < 8]
    row(S, "sentences 대응 근거 약한 건(LCS<8, 참고)", "INFO", "없음" if not weak else "; ".join(weak))

    # ---------------- [안전 비중] ----------------
    S = "안전 비중"
    cls = [s["id"] for s in se["items"] if is_safety_instruction(s["ko"])]
    intent = [s["id"] for s in se["items"] if s.get("intent") == "safety"]
    n = len(cls)
    row(S, "sentences 안전지시(명령/금지형) 분류 n/30 ≥15", "PASS" if n >= 15 else "FAIL",
        f"{n}/30" + ("" if n >= 15 else "; 목록: " + ", ".join(cls)))
    only_cls = sorted(set(cls) - set(intent))
    only_int = sorted(set(intent) - set(cls))
    row(S, "분류기 vs intent=safety 대조", "INFO",
        f"intent=safety {len(intent)}/30 (_meta {se.get('_meta', {}).get('safety_ratio')}); 분류기만={only_cls or '없음'}, intent만={only_int or '없음'}")

    # ---------------- [오염셋 무결성] ----------------
    S = "오염셋 무결성"
    gl_vi = {g["term_ko"]: g["term_vi"] for g in gl}
    smap = {s["id"]: s for s in se["items"]}

    def vi_variants(t: str) -> list[str]:
        v = paren_variants(t) + [x.strip() for x in t.split("/") if len(x.strip()) >= 3]
        return [x.lower() for x in v if x]

    bad_c = []
    for c in co["items"]:
        base = smap[c["base_id"]]
        a, b = base["answer_vi"], c["corrupted_vi"]
        na, nb = vi_numbers(a), vi_numbers(b)
        ga, gb = vi_neg(a), vi_neg(b)
        t = c["type"]
        if t == "term_swap":
            swapped = []
            for term in base.get("terms", []):
                for v in vi_variants(gl_vi.get(term) or ""):
                    if v in a.lower() and v not in b.lower():
                        swapped.append(f"{term}→'{v}' 제거")
                        break
            ok = bool(swapped) and na == nb and ga == gb
            why = "" if ok else ("용어 미치환" if not swapped else f"수치/부정 동반 변경(num {na}->{nb}, neg {ga}->{gb})")
        elif t == "negation":
            # D13-A: 원문 대비 오염문 부정어 개수 변화 ±1 = PASS, 0 = FAIL.
            # 반의어·양태 치환(개수 불변)과 다중 부정 조작(|delta|>=2)을 함께 배제한다.
            delta = gb - ga
            ok = abs(delta) == 1 and na == nb
            if ok:
                why = ""
            elif na != nb:
                why = f"수치 동반 변경 {na}->{nb}"
            elif delta == 0:
                why = f"부정어 수 동일({ga}->{gb}) — 삽입/제거 아님(반의어·양태 치환)"
            else:
                why = f"부정어 {abs(delta)}개 동시 변경({ga}->{gb}) — 단일 삽입/제거만 허용"
        else:  # number
            ok = na != nb and strip_numbers(a) == strip_numbers(b)
            why = "" if ok else ("숫자 미변경" if na == nb else "숫자 외 텍스트도 변경")
        if not ok:
            bad_c.append(f"{c['id']}({c['base_id']},{t}): {why}")
    n_c = len(co["items"])
    row(S, "corrupted_vi vs answer_vi type별 프로그램 대조", "PASS" if not bad_c else "FAIL",
        f"{n_c-len(bad_c)}/{n_c} type대로" + ("" if not bad_c else "; 불일치: " + "; ".join(bad_c)))

    # ---------------- [vi 구조 대조 (§3 보조)] ----------------
    S = "vi 구조 대조(보조)"
    num_mis, neg_mis = [], []
    pairs = [(s["id"], s["ko"], s["answer_vi"]) for s in se["items"]]
    pairs += [(f"quiz_learning#{i+1}", it["q_ko"], it["q_vi"]) for i, it in enumerate(ql["items"])]
    pairs += [(f"quiz_safety#{i+1}", it["q_ko"], it["q_vi"]) for i, it in enumerate(qs["items"])]
    pairs += [(f"phrases[{i}]", p["text_ko"], p["text_vi"]) for i, p in enumerate(ph)]
    pairs += [(f"glossary:{g['term_ko']}", g["term_ko"], g["term_vi"]) for g in gl]
    for pid, ko, vi in pairs:
        kn, vn = ko_numbers(ko), vi_numbers(vi)
        if kn != vn:
            num_mis.append(f"{pid} ko{kn} vi{vn}")
        if (ko_neg(ko) > 0) != (vi_neg(vi) > 0):
            neg_mis.append(f"{pid} ko_neg={ko_neg(ko)} vi_neg={vi_neg(vi)}")
    row(S, "ko↔vi 수치 집합 일치 (sentences·quiz·phrases·glossary)", "PASS" if not num_mis else "WARN",
        f"{len(pairs)}쌍 검사" + ("" if not num_mis else "; 불일치: " + "; ".join(num_mis)))
    row(S, "ko↔vi 부정 극성 일치", "PASS" if not neg_mis else "WARN",
        f"{len(pairs)}쌍 검사" + ("" if not neg_mis else "; 불일치: " + "; ".join(neg_mis)))





# =====================================================================
# 07 근거 인용 검사 (M-29) — main판 seed_check 위에 선행분(feat/ms-seed-07) 재적용.
# 시드가 없어도 실행된다(소스 정합만). 검사 규칙:
#   ① 안전·절차 문장 [src:] 커버리지 100%  (매뉴얼 줄 + JSON 레코드 ko 문장)
#   ② 인용 src ID ⊂ manifest (날조 0) ∧ status fetched/collected
#   ③ 공공누리 4유형 인용 문장 = data/sources/text/<ID>.md 원문 부분문자열(공백 제거 후 대조, 무변형)
#   ⑥ role: case 소스 인용 0 (매뉴얼·quiz·testset = FAIL, 그 외 WARN)
#   ⑦ draft:true 필드 집계
# 인용 표기: 매뉴얼 `[src: ID 위치]`(`;` 구분), 「…」/“…” 안이 있으면 그 안만 ③ 대조. JSON 은 `src` 필드(+`quote`).
import unicodedata

import yaml

SRC_MANIFEST = ROOT / "data/sources/manifest.yaml"
SRC_TEXT_DIR = ROOT / "data/sources/text"
SRC_ID_RE = re.compile(r"[A-Z][A-Z0-9]+(?:-[A-Z0-9]+)*")
SRC_MARK_RE = re.compile(r"\[src:\s*([^\]]*)\]")
SRC_FRONT_RE = re.compile(r"^---\n.*?\n---\n", re.S)
SRC_QUOTE_RE = re.compile(r"「([^」]+)」|“([^”]+)”")
SRC_KO_KEYS = ("ko", "q_ko", "text_ko", "term_ko")
SRC_KEYS = ("src", "source_ref", "src_ids")
SRC_IMPER = re.compile(r"(십시오|하세요|해야|하여야|할 것|하도록)")
SRC_PROHIB = re.compile(r"(마십시오|마세요|않습니다|않는다|금지|안 됩니다|안 된다|아니 된다)")
SRC_SENT_END = re.compile(r"(다\.|십시오\.?|세요\.?|것\.?)$")


def src_squash(s: str) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFC", s))


def src_parse_ids(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [i for v in value for i in src_parse_ids(v)]
    out = []
    for seg in re.split(r"[;,/]", str(value)):
        m = SRC_ID_RE.search(seg.strip())
        if m:
            out.append(m.group(0))
    return out


def src_strip_md(line: str) -> str:
    s = re.sub(r"^\s*(?:[-*+]|\d+[.)]|>)\s+", "", line)
    return re.sub(r"\*\*|__|`", "", s).strip()


def src_is_safety_or_procedure(ko: str, chapter_cat: str | None = None) -> bool:
    if SRC_PROHIB.search(ko) or (SRC_IMPER.search(ko) and SAFETY_KW.search(ko)):
        return True
    return chapter_cat in ("safety", "instruction") and bool(SRC_SENT_END.search(ko.strip()))


def src_parse_manual(md: str) -> tuple[dict, list[dict]]:
    m = SRC_FRONT_RE.match(md)
    fm = yaml.safe_load(m.group(0).strip("-\n")) if m else {}
    cat_map = {}
    for c in (fm or {}).get("category_map", []) or []:
        mm = re.match(r"\s*(\d+)", str(c.get("section", "")))
        if mm:
            cat_map[mm.group(1)] = c.get("category")
    lines, cur_cat, in_code = [], None, False
    body = md[m.end():] if m else md
    offset = md[:m.end()].count("\n") if m else 0
    for i, line in enumerate(body.splitlines(), offset + 1):
        if line.strip().startswith("```"):
            in_code = not in_code
            continue
        if in_code or not line.strip() or line.lstrip().startswith(("<!--", "|", "---")):
            continue
        h = re.match(r"^##\s+(\d+)\.", line)
        if h:
            cur_cat = cat_map.get(h.group(1))
        if line.lstrip().startswith("#"):
            continue
        lines.append({"line_no": i, "text": src_strip_md(line), "chapter_cat": cur_cat})
    return fm or {}, lines


def src_walk_records(obj, path="$") -> list[tuple[str, dict]]:
    out = []
    if isinstance(obj, dict):
        if any(k in obj for k in SRC_KO_KEYS) or "draft" in obj or any(k in obj for k in SRC_KEYS):
            out.append((path, obj))
        for k, v in obj.items():
            if k.startswith("_") and k != "_meta":
                continue
            out += src_walk_records(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            out += src_walk_records(v, f"{path}[{i}]")
    return out


def src_rec_ko(rec: dict) -> str | None:
    for k in SRC_KO_KEYS:
        if isinstance(rec.get(k), str):
            return rec[k]
    return None


def src_rec_ids(rec: dict) -> list[str]:
    ids = []
    for k in SRC_KEYS:
        ids += src_parse_ids(rec.get(k))
    for m in SRC_MARK_RE.finditer(src_rec_ko(rec) or ""):
        ids += src_parse_ids(m.group(1))
    return ids


def src_checks() -> None:
    S = "근거 소스 정합"
    if not SRC_MANIFEST.exists():
        row(S, "manifest", "FAIL", f"{SRC_MANIFEST.relative_to(ROOT).as_posix()} 없음")
        return
    manifest = {s["id"]: s for s in yaml.safe_load(SRC_MANIFEST.read_text(encoding="utf-8")).get("sources", [])}
    texts: dict[str, dict] = {}
    if SRC_TEXT_DIR.exists():
        for f in sorted(SRC_TEXT_DIR.glob("*.md")):
            raw = f.read_text(encoding="utf-8")
            m = SRC_FRONT_RE.match(raw)
            fm = (yaml.safe_load(m.group(0).strip("-\n")) if m else {}) or {}
            body = re.sub(r"<!--.*?-->", "", raw[m.end():] if m else raw)
            texts[f.stem] = {"fm": fm, "squash": src_squash(body)}
    fetched = {i for i, s in manifest.items() if s.get("status") in ("fetched", "collected")}
    type4 = {i for i, s in manifest.items() if "4유형" in str(s.get("license", ""))}
    case_ids = {i for i, s in manifest.items() if s.get("role") == "case"}
    row(S, "manifest 항목", "INFO", f"{len(manifest)}건 — fetched {len(fetched)}, 4유형 {len(type4)}, role:case {sorted(case_ids)}")
    bad = [k for k, t in texts.items() if t["fm"].get("id") != k or k not in manifest]
    row(S, "text/ 파일 id = 파일명 ∧ manifest 존재", "PASS" if not bad else "FAIL", f"{len(texts)}건" + ("" if not bad else f"; 불일치 {bad}"))
    role_bad = [k for k, t in texts.items() if (t["fm"].get("role") or None) != (manifest.get(k, {}).get("role") or None)]
    row(S, "text/ front matter role = manifest role", "PASS" if not role_bad else "FAIL", "일치" if not role_bad else str(role_bad))
    row(S, "4유형 fetched 소스 중 text/ 부재(③ 수동 대조 대상)", "INFO", str(sorted(i for i in type4 & fetched if i not in texts)))

    # ---- 시드 수집 (있는 것만) ----
    manual_keys = [k for k in ("lathe", "press") if P[k].exists()]
    json_keys = [k for k in ("glossary", "quiz_learning", "quiz_safety", "phrases", "special", "sentences", "corrupted") if P[k].exists()]
    if not manual_keys and not json_keys:
        row("① [src:] 커버리지", "시드 부재", "SKIP", "07 산출물 없음 — ①②③⑥⑦ 건너뜀")
        return
    manual_lines: dict[str, list[dict]] = {}
    for k in manual_keys:
        _, lines = src_parse_manual(P[k].read_text(encoding="utf-8"))
        manual_lines[P[k].name] = lines
    records: dict[str, list[tuple[str, dict]]] = {}
    for k in json_keys:
        records[P[k].relative_to(ROOT).as_posix()] = src_walk_records(load_json(k))

    # ---- ① 커버리지 ----
    S = "① [src:] 커버리지"
    need = have = 0
    miss = []
    for name, lines in manual_lines.items():
        for l in lines:
            if src_is_safety_or_procedure(l["text"], l["chapter_cat"]):
                need += 1
                if SRC_MARK_RE.search(l["text"]):
                    have += 1
                else:
                    miss.append(f"{name}:{l['line_no']} {l['text'][:40]}")
    for rel, recs in records.items():
        for path, rec in recs:
            ko = src_rec_ko(rec)
            if ko and src_is_safety_or_procedure(ko):
                need += 1
                if src_rec_ids(rec):
                    have += 1
                else:
                    miss.append(f"{rel}{path[1:]} {ko[:40]}")
    row(S, "안전·절차 문장 src 커버리지 = 100%", "PASS" if not miss else "FAIL",
        f"{have}/{need}" + ("" if not miss else "; 누락: " + "; ".join(miss[:30]) + (" …" if len(miss) > 30 else "")))
    total_lines = sum(len(v) for v in manual_lines.values())
    marked = sum(1 for v in manual_lines.values() for l in v if SRC_MARK_RE.search(l["text"]))
    row(S, "매뉴얼 전체 문장 중 [src:] 부착 비율(참고)", "INFO", f"{marked}/{total_lines}" + (f" ({100 * marked // total_lines}%)" if total_lines else ""))

    # ---- 인용 수집 ----
    cites: list[dict] = []
    for name, lines in manual_lines.items():
        for l in lines:
            ms = list(SRC_MARK_RE.finditer(l["text"]))
            if not ms:
                continue
            ids = [i for m in ms for i in src_parse_ids(m.group(1))]
            plain = SRC_MARK_RE.sub("", l["text"]).strip()
            spans = [next(g for g in q.groups() if g) for q in SRC_QUOTE_RE.finditer(plain)] or [plain]
            cites.append({"where": f"{name}:{l['line_no']}", "ids": ids, "texts": spans, "kind": "manual"})
    for rel, recs in records.items():
        kind = "quiz" if "/quiz/" in rel else "testset" if "testset" in rel else "json"
        for path, rec in recs:
            ids = src_rec_ids(rec)
            if not ids:
                continue
            t = rec.get("quote") if isinstance(rec.get("quote"), str) else SRC_MARK_RE.sub("", src_rec_ko(rec) or "").strip()
            cites.append({"where": f"{rel}{path[1:]}", "ids": ids, "texts": [t] if t else [], "kind": kind})
    dist: dict[str, int] = {}
    for c in cites:
        for i in c["ids"]:
            dist[i] = dist.get(i, 0) + 1
    row(S, "소스별 인용 분포", "INFO", ", ".join(f"{k} {v}" for k, v in sorted(dist.items())) or "인용 0")

    # ---- ② manifest 존재 ----
    S = "② src ID ⊂ manifest"
    unknown = sorted({f"{c['where']}→{i}" for c in cites for i in c["ids"] if i not in manifest})
    not_fetched = sorted({f"{c['where']}→{i}" for c in cites for i in c["ids"] if i in manifest and i not in fetched})
    row(S, "인용 ID 전부 manifest 존재(날조 0)", "PASS" if not unknown else "FAIL",
        f"인용 {len(cites)}건, ID {len(dist)}종" + ("" if not unknown else "; 미존재: " + "; ".join(unknown[:20])))
    row(S, "인용 ID status ∈ {fetched, collected}", "PASS" if not not_fetched else "FAIL", "전 건" if not not_fetched else "; ".join(not_fetched[:20]))

    # ---- ③ 4유형 무변형 ----
    S = "③ 4유형 무변형(text/ 부분문자열)"
    ok4, bad4, manual4, other_bad, ok_other = 0, [], [], [], 0
    for c in cites:
        for i in c["ids"]:
            if i not in manifest:
                continue
            for t in c["texts"]:
                if len(src_squash(t)) < 6:
                    continue
                if i not in texts:
                    if i in type4:
                        manual4.append(f"{c['where']}→{i}")
                    continue
                hit = src_squash(t) in texts[i]["squash"]
                if i in type4:
                    if hit:
                        ok4 += 1
                    else:
                        bad4.append(f"{c['where']}→{i} '{t[:30]}…'")
                elif hit:
                    ok_other += 1
                else:
                    other_bad.append(f"{c['where']}→{i} '{t[:30]}…'")
    row(S, "4유형 인용 문장 = 원문 부분문자열(공백 제거 비교)", "PASS" if not bad4 else "FAIL",
        f"일치 {ok4}" + ("" if not bad4 else "; 불일치: " + "; ".join(bad4[:20])))
    row(S, "4유형 인용 중 text/ 부재(수동 대조 필요)", "INFO" if not manual4 else "WARN", "없음" if not manual4 else "; ".join(manual4[:20]))
    row(S, "4유형 외 소스 인용 문장 원문 대조(참고 — 재구성 허용)", "INFO",
        f"원문 일치 {ok_other} / 재구성 {len(other_bad)}")

    # ---- ⑥ role: case ----
    S = "⑥ role:case 인용 금지"
    hard = [f"{c['where']}→{i}" for c in cites for i in c["ids"] if i in case_ids and c["kind"] in ("manual", "quiz", "testset")]
    soft = [f"{c['where']}→{i}" for c in cites for i in c["ids"] if i in case_ids and c["kind"] not in ("manual", "quiz", "testset")]
    row(S, "매뉴얼·quiz·testset 의 case 소스 인용 = 0", "PASS" if not hard else "FAIL", "0" if not hard else "; ".join(hard))
    row(S, "그 외 파일의 case 소스 인용", "INFO" if not soft else "WARN", "0" if not soft else "; ".join(soft))

    # ---- ⑦ draft 집계 ----
    S = "⑦ draft 집계"
    tot_true = 0
    for rel, recs in records.items():
        t = sum(1 for _, r in recs if r.get("draft") is True)
        f = sum(1 for _, r in recs if r.get("draft") is False)
        n = sum(1 for _, r in recs if "draft" not in r)
        tot_true += t
        row(S, f"{rel} draft", "INFO", f"레코드 {len(recs)}: true {t} / false {f} / 없음 {n}")
    row(S, "draft:true 필드 총계(JSON 레코드)", "INFO", str(tot_true))

# =====================================================================
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="main", help="시크릿 검사용 diff 기준 브랜치")
    ap.add_argument("--json", help="결과를 JSON으로도 저장")
    args = ap.parse_args()

    missing = [k for k, p in P.items() if not p.exists()]

    if missing:
        rel = [P[k].relative_to(ROOT).as_posix() for k in missing]
        print("입력 부재 — 시드 의존 검사 SKIP")
        print("  누락:", ", ".join(rel))
        print("  사유: 06 시드 폐기(M-29) 후 07 재생성 전 구간. 파일 복원 시 자동 재개.")
        print("")
        for sec in SEED_SECTIONS:
            row(sec, "시드 의존 검사", "SKIP", f"입력 부재 {len(rel)}건: " + ", ".join(rel))
    else:
        seed_checks()

    src_checks()   # 07 근거 인용 검사 (①②③⑥⑦) — 시드 부재 시 소스 정합만 수행

    # ---------------- [금지어] ----------------
    S = "금지어"
    scan_keys = ("glossary", "quiz_learning", "quiz_safety", "phrases", "special", "lathe", "press", "kosha", "sentences", "corrupted", "exp_readme")
    scan_keys = tuple(k for k in scan_keys if P[k].exists())
    brand_hits, name_hits, team_hits = [], [], []
    for k in scan_keys:
        f = P[k]
        rel = f.relative_to(ROOT).as_posix()
        for ln, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            for pat, flags in ((BRAND_KO, 0), (BRAND_EN_I, re.I), (BRAND_EN_CS, 0)):
                for m in re.finditer(pat, line, flags):
                    brand_hits.append(f"{rel}:{ln} '{m.group(0)}' — {line.strip()[:60]}")
            for m in re.finditer(NAME_TITLE, line):
                name_hits.append(f"{rel}:{ln} '{m.group(0)}' — {line.strip()[:60]}")
            for nm in TEAM_NAMES:
                if nm in line:
                    team_hits.append(f"{rel}:{ln} '{nm}' — {line.strip()[:60]}")
    row(S, "실존 기업·상표·모델명", "PASS" if not brand_hits else "FAIL", "검출 0" if not brand_hits else "; ".join(brand_hits))
    row(S, "한글 성명+호칭 패턴", "PASS" if not name_hits else "WARN", "검출 0" if not name_hits else "; ".join(name_hits))
    row(S, "팀원 실명(명선·새봄·정현·병갑)", "INFO" if not team_hits else "WARN",
        "검출 0" if not team_hits else f"{len(team_hits)}건: " + "; ".join(team_hits))

    # ---------------- [시크릿] ----------------
    S = "시크릿"
    try:
        diff = subprocess.run(["git", "diff", f"{args.base}...HEAD"], cwd=ROOT, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", check=True).stdout
        added = [l[1:] for l in diff.splitlines() if l.startswith("+") and not l.startswith("+++")]
        files = re.findall(r"^\+\+\+ b/(.+)$", diff, flags=re.M)
        sec_hits = []
        for pat, label in SECRET_PATTERNS:
            for l in added:
                if re.search(pat, l):
                    sec_hits.append(f"{label}: {l.strip()[:60]}")
        env_files = [f for f in files if re.search(r"(^|/)\.env(\.|$)", f) and not f.endswith(".env.example")]
        row(S, f"브랜치 diff({args.base}...HEAD) 키·토큰 패턴", "PASS" if not sec_hits else "FAIL",
            f"변경 파일 {len(files)}개, 추가 줄 {len(added)}" + ("" if not sec_hits else "; " + "; ".join(sec_hits)))
        row(S, ".env 계열 파일 추가", "PASS" if not env_files else "FAIL", "없음" if not env_files else str(env_files))
    except Exception as e:  # git 없음 등
        row(S, "브랜치 diff 시크릿 검사", "WARN", f"실행 불가: {e}")

    # ---------------- 출력 ----------------
    print("## seed_check.py 결과\n")
    cur_sec = None
    for i, r in enumerate(ROWS, 1):
        if r["section"] != cur_sec:
            cur_sec = r["section"]
            print(f"\n### [{cur_sec}]\n")
            print("| # | 항목 | 결과 | 상세 |")
            print("|---|---|---|---|")
        print(f"| {i} | {r['item']} | {r['status']} | {r['detail'].replace('|', '¦')} |")
    counted = [r for r in ROWS if r["status"] in ("PASS", "FAIL")]
    fails = [r["item"] for r in ROWS if r["status"] == "FAIL"]
    warns = [r["item"] for r in ROWS if r["status"] == "WARN"]
    print(f"\n**요약**: PASS {len(counted)-len(fails)}/{len(counted)}"
          + (f" — FAIL: {'; '.join(fails)}" if fails else "")
          + (f" / WARN {len(warns)}: {'; '.join(warns)}" if warns else ""))
    if args.json:
        Path(args.json).write_text(json.dumps(ROWS, ensure_ascii=False, indent=1), encoding="utf-8")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
