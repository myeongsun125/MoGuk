#!/usr/bin/env python3
"""convert_sources.py — data/sources/raw/ → data/sources/text/<ID>.md (M-29·D2, 07 선행).

manifest.yaml 의 fetched 항목만 대상으로, ID별 규칙에 따라 텍스트를 뽑아 text/ 에 쓴다.
원문 문장은 바꾸지 않는다(무변형). 바뀌는 것은 공백·줄바꿈 정리와 제외 규칙(NCS)뿐이며,
무엇을 어떻게 뽑았는지(방식·제외 내역)를 각 파일 머리 front matter 에 남긴다.

규칙 (2026-08-29 명선 지시)
  LAW-*        : pandoc 금지. XML 조문단위 파서. manifest target 조문·별표만, 조문 단위 원문 그대로.
  KOSHA pdf    : 텍스트 추출 (pypdf; 폰트 cmap 깨지는 파일은 PyMuPDF).
  KOSHA pptx   : 슬라이드 텍스트 추출 (OOXML a:t 런). 텍스트 0 → 변환 실패 보고.
  NCS-*        : 텍스트만 — 도표·사진·삽화·도면·별도 출처 표기 딸린 인용부 제외 (PyMuPDF 블록+표 감지+캡션 규칙).
  KOSHA-PRESS-3: jpg → 변환 제외 (OCR 금지).
  KOSHA-CASE-1 : 변환하되 front matter role: case.

usage:  python scripts/convert_sources.py [--only ID ...] [--dry-run]
requires: pyyaml, pypdf, pymupdf
"""
from __future__ import annotations

import argparse
import datetime as dt
import re
import sys
import unicodedata
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

import yaml


class _Dumper(yaml.SafeDumper):
    pass


def _str_repr(dumper, data):
    if "\n" in data:   # 여러 줄 문자열은 literal block(|) — 문안 verbatim 유지
        return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")
    return dumper.represent_scalar("tag:yaml.org,2002:str", data)


_Dumper.add_representer(str, _str_repr)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "data/sources/manifest.yaml"
OUT_DIR = ROOT / "data/sources/text"

# 07 산출물 헤더 주석 (명선 지시 문안, verbatim)
REDIST_TRIGGER = (
    "raw/ 재배포 검토 트리거: 레포 공개 전환 / raw 포함 외부 제출 / 상업화. 해당 시 미표시\n"
    "2건(M-96·M-138)과 PRESS-3 페이지 추출본 우선 재검토. RAG 적재분(text/ 13건) 포함."
)

# ---- ID별 변환 규칙 ---------------------------------------------------------
LAW_TARGETS = {
    # manifest note 의 target 대응 조문(조문 단위) / 별표(별표구분=별표)
    "LAW-KOSH-RULE": {"articles": [87, 91, 92, 102, 103, 104], "annexes": []},
    "LAW-KOSH-ENF": {"articles": [26], "annexes": [4, 5]},
}
PDF_PYPDF = {"KOSHA-LATHE", "KOSHA-LATHE-3", "KOSHA-PRESS", "KOSHA-PRESS-4",
             "KOSHA-COMMON-1", "KOSHA-COMMON-2", "KOSHA-COMMON-3"}
PDF_PYMUPDF = {"KOSHA-CASE-1"}          # pypdf: CID 폰트 cmap 깨짐 → PyMuPDF
NCS = {"NCS-LATHE", "NCS-LATHE-2", "NCS-COMMON"}
PPTX = {"KOSHA-PRESS-2"}
SKIP = {"KOSHA-PRESS-3": "jpg 원문 — OCR 금지(4유형 무변형 보장 불가), 검수 대조용 원문 유지 [규칙 d]"}
# 실물 대조에서 manifest 와 내용이 다른 파일 — 변환 보류(상신). 정정 반입 후 이 목록에서 제거.
HOLD = {
    "KOSHA-LATHE-2": "raw 내용 불일치 — 실물은 OPS 3호 '깔림(천장크레인)' 2026-교육총괄실-84, manifest '[안전기준] 공작기계 2024-교육혁신실-840' 아님",
    "KOSHA-LATHE-4": "raw 내용 불일치 — 실물은 '융자금 부정수급 안내' 2026-중소기업지원실-177, manifest '[안전기준] 원동기·회전축 2024-교육혁신실-837' 아님",
}

PUBNO_RE = re.compile(r"(\d{4}-[가-힣]+-\d+|M\s*-\s*\d+\s*-\s*\d{4})")


# ---- 공통 --------------------------------------------------------------------
CTRL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")   # C0/C1 제어문자 (\n \t 제외)


def norm_lines(text: str) -> str:
    """줄 단위 rstrip + 연속 공백줄 → 1줄 + 제어문자(BEL 등) 제거. 문자 내용 변경 없음(NFC 정규화만)."""
    text = unicodedata.normalize("NFC", CTRL_RE.sub("", text))
    lines = [l.rstrip() for l in text.splitlines()]
    out, blank = [], 0
    for l in lines:
        if l.strip():
            out.append(l)
            blank = 0
        else:
            blank += 1
            if blank == 1:
                out.append("")
    return "\n".join(out).strip("\n") + "\n"


def front_matter(src: dict, method: str, extra: dict | None = None) -> str:
    fm = {
        "id": src["id"],
        "title": src.get("title"),
        "publisher": src.get("publisher"),
        "license": src.get("license"),
        "lang": src.get("lang"),
        "source_file": src.get("file"),
        "retrieved_at": (src["retrieved_at"].strftime("%Y-%m-%dT%H:%M:%SZ")
                         if isinstance(src.get("retrieved_at"), dt.datetime) else src.get("retrieved_at")),
        "converted_at": dt.date.today().isoformat(),
        "method": method,
    }
    if src.get("role"):
        fm["role"] = src["role"]
    if extra:
        fm.update(extra)
    fm["redistribution_trigger"] = REDIST_TRIGGER
    body = yaml.dump(fm, Dumper=_Dumper, allow_unicode=True, sort_keys=False, width=1000)
    return "---\n" + body + "---\n"


def manifest_pubno(src: dict) -> str | None:
    """manifest title/note 에 적힌 발간번호·규정번호 (첫 매치)."""
    for field in ("title", "note"):
        m = PUBNO_RE.search(str(src.get(field) or ""))
        if m:
            return re.sub(r"\s+", "", m.group(1))
    return None


def found_pubnos(text: str) -> list[str]:
    return sorted({re.sub(r"\s+", "", m) for m in PUBNO_RE.findall(text)})


# ---- LAW: XML 조문단위 파서 --------------------------------------------------
def law_convert(src: dict, cfg: dict) -> tuple[str, dict]:
    root = ET.parse(ROOT / src["file"]).getroot()
    info = {c.tag: (c.text or "").strip() for c in root.find("기본정보")}
    units = root.find("조문").findall("조문단위")
    parts, stats = [], {}
    for n in cfg["articles"]:
        hit = [u for u in units if u.findtext("조문여부") == "조문"
               and u.findtext("조문번호", "").strip() == str(n)
               and not (u.findtext("조문가지번호") or "").strip()]
        if len(hit) != 1:
            raise RuntimeError(f"{src['id']} 제{n}조 조문단위 {len(hit)}건 — 1건이어야 함")
        u = hit[0]
        head = u.findtext("조문내용").strip()
        m = re.match(r"^(제\d+조(?:의\d+)?\([^)]*\))\s*(.*)$", head, re.S)
        lines = [f"## {m.group(1)}"] + ([m.group(2).strip()] if m and m.group(2).strip() else []) if m else [f"## {head}"]
        cnt = {"항": 0, "호": 0, "목": 0}
        for e in u.iter():
            if e.tag in ("항내용", "호내용", "목내용"):
                t = (e.text or "").strip()
                if t:
                    lines.append(t)
                    cnt[e.tag[0]] += 1
        ref = (u.findtext("조문참고자료") or "").strip()
        if ref:
            lines.append(ref)
        parts.append("\n".join(lines))
        stats[f"제{n}조"] = (f"{u.findtext('조문제목')} — 항 {cnt['항']}·호 {cnt['호']}·목 {cnt['목']}"
                            f" (시행 {u.findtext('조문시행일자')})")
    for n in cfg["annexes"]:
        hit = [u for u in root.find("별표").findall("별표단위")
               if u.findtext("별표구분") == "별표" and int(u.findtext("별표번호")) == n
               and (u.findtext("별표가지번호") or "00") == "00"]
        if len(hit) != 1:
            raise RuntimeError(f"{src['id']} 별표{n} 별표단위 {len(hit)}건")
        u = hit[0]
        body = norm_lines(u.findtext("별표내용") or "")
        parts.append(f"## [별표 {n}] {u.findtext('별표제목')}\n\n```text\n{body}```")
        stats[f"별표{n}"] = f"{u.findtext('별표제목')} — {sum(1 for l in body.splitlines() if l.strip())}줄"
    method = ("XML 조문단위 파서 (xml.etree) — 조문여부=조문·조문번호 일치 단위만, "
              "조문내용→항내용→호내용→목내용 순 원문 그대로 (별표: 별표구분=별표, 별표내용 원문·공백줄 정리만). pandoc 미사용")
    extra = {
        "law_id": info.get("법령ID"), "promulgated": info.get("공포일자"), "promulgation_no": info.get("공포번호"),
        "effective": info.get("시행일자"), "target_units": stats,
    }
    text = (front_matter(src, method, extra) + "\n# " + info.get("법령명_한글", src["title"]) + "\n\n"
            + "\n\n".join(parts) + "\n")
    return text, stats


# ---- KOSHA pdf -----------------------------------------------------------------
def pdf_pypdf(path: Path):
    import pypdf
    from pypdf import PdfReader
    r = PdfReader(str(path))
    return [p.extract_text() or "" for p in r.pages], f"pypdf {pypdf.__version__} page.extract_text() 페이지 단위"


def pdf_pymupdf(path: Path):
    import pymupdf
    d = pymupdf.open(str(path))
    return [p.get_text("text") for p in d], f"PyMuPDF {pymupdf.version[0]} page.get_text('text') 페이지 단위"


def pages_to_body(pages: list[str]) -> str:
    return "\n".join(f"<!-- p.{i} -->\n" + norm_lines(t) for i, t in enumerate(pages, 1))


def kosha_convert(src: dict, use_mupdf: bool) -> tuple[str, dict]:
    path = ROOT / src["file"]
    pages, method = (pdf_pymupdf if use_mupdf else pdf_pypdf)(path)
    if use_mupdf:
        method += " (pypdf 는 CID 폰트 cmap 미해석으로 본문 깨짐 → 대체)"
    body = pages_to_body(pages)
    nums = found_pubnos(body)
    mp = manifest_pubno(src)
    extra = {"pages": len(pages), "pub_no": mp, "pub_no_in_document": nums}
    if mp and nums and mp not in nums:
        extra["pub_no_check"] = f"MISMATCH — manifest {mp} / 문서 내 {nums} (내용은 title 과 일치, 번호 불일치 상신)"
    else:
        extra["pub_no_check"] = "OK" if mp else "manifest 번호 없음"
    stats = {"pages": len(pages), "chars": sum(len(p) for p in pages), "pubno": extra["pub_no_check"]}
    return front_matter(src, method, extra) + "\n" + body, stats


# ---- pptx --------------------------------------------------------------------
def pptx_convert(src: dict):
    A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
    z = zipfile.ZipFile(ROOT / src["file"])
    slides = sorted([n for n in z.namelist() if re.match(r"ppt/slides/slide\d+\.xml$", n)],
                    key=lambda s: int(re.search(r"(\d+)", s).group(1)))
    texts, runs = [], 0
    for s in slides:
        root = ET.fromstring(z.read(s))
        ts = [t.text for t in root.iter(A + "t") if t.text and t.text.strip()]
        runs += len(ts)
        texts.append("\n".join(ts))
    media = sum(1 for n in z.namelist() if n.startswith("ppt/media/"))
    stats = {"slides": len(slides), "text_runs": runs, "media": media}
    if runs == 0:
        return None, stats
    body = "\n".join(f"<!-- slide {i} -->\n{norm_lines(t)}" for i, t in enumerate(texts, 1))
    return front_matter(src, "OOXML ppt/slides/slideN.xml a:t 런 추출 (zipfile+xml.etree)", stats) + "\n" + body, stats


# ---- NCS: 텍스트만 (도표·사진·삽화·도면·출처표기 인용부 제외) -----------------
CAP_RE = re.compile(r"^\s*[\[<［〈]\s*(그림|표)\s*\d+\s*[-–]\s*\d+\s*[\]>］〉](?![의은는이가을를과와에도로으])")  # 캡션 줄만(본문의 "[그림 1-28]의 …" 참조문은 제외 안 함)
SRC_RE = re.compile(r"^\s*출처\s*[:：]")
HEAD_RE = re.compile(r"^\s*(?:[󰀀-󿿿]|[①-⑳]|\(\s*[가-힣0-9]+\s*\)|\d+[.)]\s|[가-힣][.)]\s|학습\s*\d|수행\s*순서|[○●■□▪•‣※Ÿ․·ㆍ-]\s*\S)")
PROSE_END = ("다.", "다", ".", ":", "：", ")", "）", "것", "함", "음", "요")


def _is_prose(t: str) -> bool:
    t = t.strip()
    return len(t) >= 12 and (t.endswith(PROSE_END) or len(t) >= 38)


def _pop_back(out_lines: list[str], cap: int = 400) -> int:
    """출처 줄 직전까지의 표 조각 줄을 뒤에서부터 제거. 산문 줄·머리글 줄·페이지 표식에서 멈춘다."""
    n = 0
    while out_lines and n < cap:
        t = out_lines[-1]
        if not t.strip():
            out_lines.pop()
            continue
        if _is_prose(t) or HEAD_RE.search(t) or t.startswith("<!--"):
            break
        out_lines.pop()
        n += 1
    return n


def _pop_forward(lines: list[str], start: int, cap: int = 400) -> int:
    n, j = 0, start
    while j < len(lines) and n < cap:
        t = lines[j]
        if t.strip() and (_is_prose(t) or HEAD_RE.search(t) or CAP_RE.search(t) or SRC_RE.search(t)):
            break
        j += 1
        n += 1
    return n


HEAD_STRICT = re.compile(r"^\s*(?:[\U000F0000-\U000FFFFF]|\(\s*[가-힣0-9]+\s*\)|\d+\.\s|학습\s*\d|수행\s*순서|수행\s*내용|평가)")


def _table_cells(blocks, text_w: float) -> set[int]:
    """표 셀 블록 판정.
    1) 씨앗: 같은 행(세로 겹침)에 가로로 나란한 블록이 있고 (폭 < 60% 또는 이웃 2개 이상)
    2) 씨앗을 세로 근접(20pt)으로 묶어 표 영역을 만들고, 영역과 겹치거나 15pt 이내로 붙은
       비산문·비머리글 블록을 영역에 편입(반복). 산문 블록(문장 종결·긴 줄, 폭 50% 이상)과 머리글은 항상 제외."""
    n = len(blocks)
    txt_ok = [bool(re.search(r"\w", t)) for _, t in blocks]
    prose = [any(_is_prose(l) for l in t.strip().splitlines()) for _, t in blocks]
    head = [bool(HEAD_STRICT.search(t.strip()[:6])) for _, t in blocks]
    seeds: set[int] = set()
    for i in range(n):
        ri, _ = blocks[i]
        if not txt_ok[i] or head[i]:
            continue
        neigh = 0
        for j in range(n):
            if i == j or not txt_ok[j]:
                continue
            rj, _ = blocks[j]
            ov = min(ri.y1, rj.y1) - max(ri.y0, rj.y0)
            if ov > 1 and (ri.x1 <= rj.x0 + 2 or rj.x1 <= ri.x0 + 2):
                neigh += 1
        if neigh >= 1 and (ri.width < 0.6 * text_w or neigh >= 2) and not (prose[i] and ri.width >= 0.5 * text_w):
            seeds.add(i)
    if not seeds:
        return set()
    regions: list[list[float]] = []
    for i in sorted(seeds, key=lambda k: blocks[k][0].y0):
        r = blocks[i][0]
        if regions and r.y0 - regions[-1][1] < 20:
            regions[-1][1] = max(regions[-1][1], r.y1)
        else:
            regions.append([r.y0, r.y1])
    cells = set(seeds)
    changed = True
    while changed:
        changed = False
        for i in range(n):
            if i in cells or head[i] or not txt_ok[i]:
                continue
            r = blocks[i][0]
            if prose[i] and r.width >= 0.5 * text_w:
                continue
            for reg in regions:
                if r.y1 > reg[0] - 15 and r.y0 < reg[1] + 15:
                    cells.add(i)
                    reg[0], reg[1] = min(reg[0], r.y0), max(reg[1], r.y1)
                    changed = True
                    break
    return cells


def ncs_convert(src: dict) -> tuple[str, dict]:
    import pymupdf
    d = pymupdf.open(str(ROOT / src["file"]))
    body_parts, excl_log = [], []
    n_tbl = n_cell = n_cap = n_src = n_img = n_heur = 0
    for pno, page in enumerate(d, 1):
        raw = [b for b in page.get_text("blocks") if b[6] == 0]        # 텍스트 블록만(이미지 블록 제외)
        blocks = [(pymupdf.Rect(b[:4]), b[4]) for b in raw]
        tables = [pymupdf.Rect(t.bbox) for t in page.find_tables().tables]
        images = [pymupdf.Rect(i["bbox"]) for i in page.get_image_info()]
        text_w = (max((r.x1 for r, _ in blocks), default=0) - min((r.x0 for r, _ in blocks), default=0)) or page.rect.width
        cells = _table_cells(blocks, text_w)
        keep = []
        for k, (r, txt) in enumerate(blocks):
            if any(r.intersects(t) and abs(r & t) / max(abs(r), 1e-6) > 0.5 for t in tables):
                n_tbl += 1
                continue                                                 # 도표(괘선 감지 표) 내부 텍스트
            if any(r.intersects(i) and abs(r & i) / max(abs(r), 1e-6) > 0.7 for i in images):
                n_img += 1
                continue                                                 # 사진·삽화·도면 위 텍스트
            if k in cells:
                n_cell += 1
                continue                                                 # 도표(가로 나란한 셀 블록·표 영역)
            keep.append(txt)
        # 줄 단위 규칙: 캡션·출처 줄 제거 + 캡션 주변 잔여 조각 줄(표 셀) 양방향 제거
        lines = [l for t in keep for l in t.splitlines()]
        out_lines, i = [], 0
        while i < len(lines):
            l = lines[i]
            if SRC_RE.search(l):
                n_src += 1
                nxt = lines[i + 1] if i + 1 < len(lines) else ""
                if CAP_RE.search(nxt):
                    kind = "표" if "표" in nxt else "그림"
                    removed = _pop_back(out_lines) if kind == "표" else 0
                    n_heur += removed
                    excl_log.append(f"p.{pno} {nxt.strip()[:40]} — 출처 표기 {kind}, 캡션·출처 줄" + (f"·앞 조각 {removed}줄" if removed else "") + " 제외")
                    i += 2
                    n_cap += 1
                    continue
                excl_log.append(f"p.{pno} 출처 줄 제외: {l.strip()[:40]}")
                i += 1
                continue
            if CAP_RE.search(l):
                n_cap += 1
                if "표" in l:
                    back = _pop_back(out_lines)
                    fwd = _pop_forward(lines, i + 1)
                    n_heur += back + fwd
                    if back or fwd:
                        excl_log.append(f"p.{pno} {l.strip()[:40]} — 표 조각 앞 {back}·뒤 {fwd}줄 제외")
                    i += 1 + fwd
                    continue
                i += 1
                continue
            out_lines.append(l)
            i += 1
        body_parts.append(f"<!-- p.{pno} -->\n" + norm_lines("\n".join(out_lines)))
    method = (f"PyMuPDF {pymupdf.version[0]} page.get_text('blocks') 텍스트 블록만 — 제외: (1) find_tables 괘선 표 내부 블록 "
              "(2) 같은 행에 가로로 나란한 셀 블록과 그 세로 근접 표 영역의 비산문 블록(산문·머리글 제외) (3) 이미지 bbox 위 블록 "
              "(4) [그림 n-n]/<표 n-n> 캡션 줄·'출처:' 줄 (5) 표 캡션 앞뒤의 잔여 조각 줄(산문·머리글에서 정지). 문자 변경 없음")
    excluded = {"table_blocks_ruled": n_tbl, "table_blocks_geometry": n_cell, "image_overlay_blocks": n_img,
                "caption_lines": n_cap, "source_lines": n_src, "fragment_lines_near_caption": n_heur}
    extra = {"pages": len(d), "excluded": excluded, "exclusion_log": excl_log,
             "residual_risk": "표·그림 자동 판별은 한계가 있음(1열 표, 셀 안 긴 문장, 표지·목차 오검출). 인용 시 원본 페이지 대조 필수"}
    stats = dict(excluded, pages=len(d))
    return front_matter(src, method, extra) + "\n" + "\n".join(body_parts), stats


# ---- main --------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*", help="변환할 ID")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    sources = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))["sources"]
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    report = []
    for src in sources:
        sid = src["id"]
        if a.only and sid not in a.only:
            continue
        if src.get("status") != "fetched":
            report.append((sid, "SKIP", f"status={src.get('status')}"))
            continue
        if sid in SKIP:
            report.append((sid, "SKIP", SKIP[sid]))
            continue
        if sid in HOLD:
            report.append((sid, "HOLD", HOLD[sid]))
            continue
        try:
            if sid in LAW_TARGETS:
                text, st = law_convert(src, LAW_TARGETS[sid])
            elif sid in PDF_PYPDF:
                text, st = kosha_convert(src, use_mupdf=False)
            elif sid in PDF_PYMUPDF:
                text, st = kosha_convert(src, use_mupdf=True)
            elif sid in NCS:
                text, st = ncs_convert(src)
            elif sid in PPTX:
                text, st = pptx_convert(src)
                if text is None:
                    report.append((sid, "FAIL", f"슬라이드 텍스트 런 0 — {st} (슬라이드 전부 이미지, OCR 금지)"))
                    continue
            else:
                report.append((sid, "SKIP", "규칙 없음"))
                continue
        except Exception as e:  # 파일별 사유 보고, 계속 진행
            report.append((sid, "FAIL", f"{type(e).__name__}: {e}"))
            continue
        out = OUT_DIR / f"{sid}.md"
        if not a.dry_run:
            out.write_text(text, encoding="utf-8", newline="\n")
        report.append((sid, "OK", f"{out.relative_to(ROOT).as_posix()} {len(text):,}자 {st}"))
    for sid, s, d in report:
        print(f"[{s:4s}] {sid:16s} {d}")
    return 1 if any(s == "FAIL" for _, s, _ in report) else 0


if __name__ == "__main__":
    sys.exit(main())
