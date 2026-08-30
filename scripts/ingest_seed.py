#!/usr/bin/env python3
"""ingest_seed.py — V2-2 시드 적재: documents/chunks(bge-m3 1024) + glossary. [명선]

WORKORDER 67행(인제스천: 분류→마스킹→청킹 500–800/오버랩 100→bge-m3→적재) 의 시드 실행체.
2026-08-30 로컬 compose·EC2 tenant_axis_demo 적재에 사용한 실행분을 scripts/ 로 편입 + 제어문자 후처리 추가.

적재 규칙
  - documents : 매뉴얼 2건 (origin='seed', source=seed_file, category=front matter category_map 다수결, masked=false —
                시드는 가상 장비 문서라 마스킹 대상 없음)
  - chunks    : `## 장` / `### 절` 단위 → 500–800자, 초과 시 줄 경계 분할 + 100자 오버랩.
                본문의 [src: …] 태그는 제거(잔존 0)하고 manifest ID 를 meta.src 로 이동.
                meta = {src:[ID…], draft, lang, seed_file, section, category, machine, doc_version}
                (retrieve.py 는 meta @> 필터 + meta->>'category' 를 읽는다 — #14 fixture 정합)
  - embedding : ollama /api/embed, EMBED_MODEL(기본 bge-m3), 1024 아니면 예외 (M-02 / M-02a 단일 런타임)
  - glossary  : glossary_50.json 50건 status='draft'
  - 후처리    : 제어문자(C0/C1, \\n·\\t 제외) 제거 + NFC — 원문 추출물(예: text/KOSHA-CASE-1 의 BEL) 유입 차단
  - 멱등      : 같은 seed_file 의 기존 documents(origin='seed') 삭제 후 재적재(chunks 는 CASCADE),
                glossary 는 draft·source_question_id IS NULL 행만 교체 (승인·질문 유래 행 무접촉)
  - 미적재    : phrases·quiz·safety_courses·testset — V3-1·V5-1 범위 (phrases.note 기본선 유지)
  - text/ 코퍼스(--sources text|all, 2026-08-30 판정 4건): manifest status=fetched ∧ text/<ID>.md 실재 → 13건.
                단위 = 페이지 표식(<!-- p.N -->) 또는 ## 헤딩(LAW 조문·별표) → 500–800/오버랩 100.
                documents(origin='seed', source=text 경로, version 1) — 시드 42청크와 source 가 달라 보존.
                meta.category = LAW·KOSHA→safety / NCS→instruction (①), KOSHA-CASE-1 포함 + meta.role='case' (② 근거 노출 제외는 SB),
                draft:false (③), meta.license 동반. 라이선스 트리거 문안 "RAG 적재분(text/ 13건) 포함" 확장 (④)

실행 (compose 안 postgres·ollama 는 포트 미공개 → core_net 에 붙은 러너 컨테이너에서 실행. core_net 은 외부 차단이라 pip 는 bridge 에서 먼저)
  docker run -d --name ingest-runner -v <repo>:/repo:ro -e DATABASE_URL=<core-api 와 동일> \\
      -e OLLAMA_URL=http://ollama:11434 -e TENANT_SLUG=axis_demo python:3.11-slim sleep 3600
  docker exec ingest-runner pip install -q 'psycopg[binary]' httpx pyyaml
  docker network connect moguk_core_net ingest-runner
  docker exec ingest-runner python /repo/scripts/ingest_seed.py --slug axis_demo
  docker rm -f ingest-runner
dry-run(청킹 통계만, DB·ollama 불필요): python scripts/ingest_seed.py --dry-run
requires: pyyaml (+ psycopg[binary], httpx — 실제 적재 시)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import unicodedata
from pathlib import Path

import yaml

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(os.environ.get("REPO_ROOT") or Path(__file__).resolve().parents[1])
MANUALS = ["data/seed/manuals/cnc_lathe_manual.md", "data/seed/manuals/press_manual.md"]
GLOSSARY = "data/seed/glossary/glossary_50.json"
MARK = re.compile(r"\s*\[src:\s*([^\]]*)\]")
ID_RE = re.compile(r"[A-Z][A-Z0-9]+(?:-[A-Z0-9]+)*")
FRONT = re.compile(r"^---\n(.*?)\n---\n", re.S)
CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")   # C0/C1 제어문자 (\n \t 제외)
EMBED_DIM = 1024
MAX_CHARS, OVERLAP = 800, 100
_removed_ctrl = 0


def clean_text(s: str) -> str:
    """제어문자 제거 + NFC. 문자 내용은 바꾸지 않는다(제거 건수는 _removed_ctrl 에 집계)."""
    global _removed_ctrl
    s2, n = CTRL.subn("", s)
    _removed_ctrl += n
    return unicodedata.normalize("NFC", s2)


def parse_ids(s: str) -> list[str]:
    out = []
    for seg in re.split(r"[;,/]", s):
        m = ID_RE.search(seg.strip())
        if m and m.group(0) not in out:
            out.append(m.group(0))
    return out


def split_manual(md: str):
    """front matter + 장/절 단위 섹션 [{section, title, category, lines}]."""
    m = FRONT.match(md)
    fm = yaml.safe_load(m.group(1)) if m else {}
    body = md[m.end():] if m else md
    cat_map = {}
    for c in fm.get("category_map", []) or []:
        mm = re.match(r"\s*(\d+)", str(c.get("section", "")))
        if mm:
            cat_map[mm.group(1)] = c.get("category")
    sections, cur, cur_cat, in_code = [], None, None, False
    for line in body.splitlines():
        if line.strip().startswith("```"):
            in_code = not in_code
        h2 = re.match(r"^##\s+(\d+)\.\s*(.*)", line)
        h3 = re.match(r"^###\s+(\d+\.\d+)\s*(.*)", line)
        if h2 and not in_code:
            cur_cat = cat_map.get(h2.group(1))
            cur = {"section": f"§{h2.group(1)}", "title": h2.group(2).strip(), "category": cur_cat, "lines": []}
            sections.append(cur)
            continue
        if h3 and not in_code:
            cur = {"section": f"§{h3.group(1)}", "title": h3.group(2).strip(), "category": cur_cat, "lines": []}
            sections.append(cur)
            continue
        if cur is not None and line.strip() and not line.startswith("`category:") and line.strip() != "---":
            cur["lines"].append(line)
    return fm, [s for s in sections if s["lines"]]


def make_chunks(fm: dict, sections: list[dict], seed_file: str) -> list[dict]:
    chunks = []
    for s in sections:
        ids: list[str] = []
        clean_lines = []
        for line in s["lines"]:
            for mm in MARK.finditer(line):
                for i in parse_ids(mm.group(1)):
                    if i not in ids:
                        ids.append(i)
            clean_lines.append(MARK.sub("", line).rstrip())
        text = clean_text(f"{s['section']} {s['title']}\n" + "\n".join(clean_lines))
        assert "[src:" not in text
        parts = [text]
        if len(text) > MAX_CHARS:
            parts, buf = [], ""
            for line in text.splitlines():
                if len(buf) + len(line) + 1 > MAX_CHARS and buf:
                    parts.append(buf)
                    buf = buf[-OVERLAP:] + "\n" + line
                else:
                    buf = (buf + "\n" + line) if buf else line
            if buf:
                parts.append(buf)
        for pi, p in enumerate(parts):
            chunks.append({
                "content": p,
                "meta": {
                    "src": ids, "draft": bool(fm.get("draft", True)), "lang": fm.get("lang", "ko"),
                    "seed_file": seed_file, "section": s["section"] + (f"#{pi + 1}" if len(parts) > 1 else ""),
                    "category": s["category"], "machine": fm.get("machine"), "doc_version": fm.get("version", 1),
                },
            })
    return chunks


def embed(texts: list[str]) -> list[list[float]]:
    """ollama /api/embed (M-02a 단일 런타임). 차원 1024 강제(M-02)."""
    import httpx

    url = os.environ.get("OLLAMA_URL", "http://ollama:11434")
    model = os.environ.get("EMBED_MODEL", "bge-m3")
    out: list[list[float]] = []
    for i in range(0, len(texts), 16):
        r = httpx.post(f"{url}/api/embed",
                       json={"model": model, "input": texts[i:i + 16], "keep_alive": os.environ.get("OLLAMA_KEEP_ALIVE", "10m")},
                       timeout=float(os.environ.get("EMBED_TIMEOUT_S", "120")))
        r.raise_for_status()
        vecs = r.json()["embeddings"]
        for v in vecs:
            if len(v) != EMBED_DIM:
                raise ValueError(f"embed: 차원 불일치 — {len(v)} != {EMBED_DIM} (M-02 고정, model={model})")
        out += vecs
    if len(out) != len(texts):
        raise ValueError(f"embed: 입력 {len(texts)}건 대비 벡터 {len(out)}건")
    return out


# ── text/ 근거 원문 코퍼스 (2026-08-30 판정 4건: category 매핑 / CASE-1 포함+role / draft:false / 트리거 문안 확장) ──
MANIFEST = "data/sources/manifest.yaml"
TEXT_DIR = "data/sources/text"
CATEGORY_BY_PREFIX = {"LAW": "safety", "KOSHA": "safety", "NCS": "instruction"}   # 판정 ① (NULL 방치 기각)
PAGE_MARK = re.compile(r"^<!-- (p\.\d+|slide \d+) -->$", re.M)


def _split_800(text: str) -> list[str]:
    """줄 경계 기준 MAX_CHARS 분할 + OVERLAP 꼬리 (make_chunks 의 분할 규칙과 동일, 별도 함수 — 기존 로직 무접촉)."""
    if len(text) <= MAX_CHARS:
        return [text]
    parts, buf = [], ""
    for line in text.splitlines():
        if len(buf) + len(line) + 1 > MAX_CHARS and buf:
            parts.append(buf)
            buf = buf[-OVERLAP:] + "\n" + line
        else:
            buf = (buf + "\n" + line) if buf else line
    if buf:
        parts.append(buf)
    return parts


def split_text_source(md: str) -> tuple[dict, list[dict]]:
    """text/<ID>.md → front matter + 단위 [{section, text}].
    단위 경계 = `<!-- p.N -->` 페이지 표식(KOSHA·NCS) 또는 `## ` 헤딩(LAW 조문·별표). fenced 블록(별표 표)은 단위 안에 유지."""
    m = FRONT.match(md)
    fm = yaml.safe_load(m.group(1)) if m else {}
    body = md[m.end():] if m else md
    units: list[dict] = []
    if PAGE_MARK.search(body):
        pos = [(mm.start(), mm.end(), mm.group(1)) for mm in PAGE_MARK.finditer(body)]
        for i, (s, e, label) in enumerate(pos):
            seg = body[e:pos[i + 1][0] if i + 1 < len(pos) else len(body)]
            if seg.strip():
                units.append({"section": label, "text": seg.strip()})
    else:
        cur, in_code = None, False
        for line in body.splitlines():
            if line.strip().startswith("```"):
                in_code = not in_code
            h = re.match(r"^##\s+(.*)", line)
            if h and not in_code:
                cur = {"section": h.group(1).strip()[:60], "lines": []}
                units.append(cur)
                continue
            if cur is not None and line.strip():
                cur["lines"].append(line)
        units = [{"section": u["section"], "text": "\n".join(u["lines"])} for u in units if u["lines"]]
    return fm, units


def load_text_plan() -> list[dict]:
    """manifest 연동: status=fetched ∧ text/<ID>.md 실재 → 13건. documents(origin='seed', source=text 경로, version 1)."""
    manifest = yaml.safe_load((ROOT / MANIFEST).read_text(encoding="utf-8"))["sources"]
    docs = []
    for src in manifest:
        sid = src["id"]
        rel = f"{TEXT_DIR}/{sid}.md"
        if src.get("status") != "fetched" or not (ROOT / rel).exists():
            continue
        fm, units = split_text_source((ROOT / rel).read_text(encoding="utf-8"))
        if fm.get("id") != sid:
            raise ValueError(f"{rel}: front matter id {fm.get('id')!r} != manifest {sid!r}")
        category = CATEGORY_BY_PREFIX[sid.split("-")[0]]
        chunks = []
        for u in units:
            parts = _split_800(clean_text(f"{sid} {u['section']}\n{u['text']}"))
            for pi, p in enumerate(parts):
                chunks.append({
                    "content": p,
                    "meta": {
                        "src": [sid], "draft": False, "lang": fm.get("lang", src.get("lang", "ko")),       # 판정 ③
                        "seed_file": rel, "section": u["section"] + (f"#{pi + 1}" if len(parts) > 1 else ""),
                        "category": category, "machine": None, "doc_version": 1,
                        "license": str(src.get("license") or ""), "role": src.get("role"),                   # 판정 ② role='case'
                    },
                })
        docs.append({"title": clean_text(str(fm.get("title") or src.get("title") or sid)), "category": category,
                     "source": rel, "version": 1, "chunks": chunks})
        print(f"{rel}: units {len(units)}, chunks {len(chunks)}, max {max(len(c['content']) for c in chunks)} chars, role={src.get('role')}")
    return docs


def load_plan() -> tuple[list[dict], list[dict]]:
    docs = []
    for rel in MANUALS:
        md = (ROOT / rel).read_text(encoding="utf-8")
        fm, secs = split_manual(md)
        chunks = make_chunks(fm, secs, rel)
        cats = [s["category"] for s in secs if s["category"]]
        category = max(set(cats), key=cats.count) if cats else None
        docs.append({"title": clean_text(str(fm.get("title", rel))), "category": category, "source": rel,
                     "version": fm.get("version", 1), "chunks": chunks})
        print(f"{rel}: sections {len(secs)}, chunks {len(chunks)}, max {max(len(c['content']) for c in chunks)} chars")
    gl = json.loads((ROOT / GLOSSARY).read_text(encoding="utf-8"))
    for g in gl:
        for k in ("term_ko", "term_vi", "term_in", "note"):
            if isinstance(g.get(k), str):
                g[k] = clean_text(g[k])
    print(f"glossary: {len(gl)}건 / 제어문자 제거 {_removed_ctrl}자")
    return docs, gl


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--slug", default=os.environ.get("TENANT_SLUG", "axis_demo"))
    ap.add_argument("--dry-run", action="store_true", help="청킹·정제 통계만 출력 (DB·ollama 불필요)")
    ap.add_argument("--sources", choices=("seed", "text", "all"), default="seed",
                    help="seed=매뉴얼 2+glossary(기본, 기존 동작) / text=근거 원문 text/ 13건 / all=둘 다. 멱등 키는 documents.source 라 서로 보존")
    a = ap.parse_args()
    docs, gl = [], []
    if a.sources in ("seed", "all"):
        docs, gl = load_plan()
    if a.sources in ("text", "all"):
        docs += load_text_plan()
    if a.dry_run:
        print("dry-run: no DB write")
        return 0
    import psycopg
    from psycopg import sql

    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        raise RuntimeError("required env DATABASE_URL is not set")
    schema = f"tenant_{a.slug}"
    if not re.match(r"^[a-z0-9_]+$", a.slug):
        raise ValueError(f"tenant slug 형식 위반: {a.slug!r}")
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(sql.SQL("SET search_path TO {}, public").format(sql.Identifier(schema)))   # M-04b/M-04c 순서
        for d in docs:
            cur.execute("DELETE FROM documents WHERE origin='seed' AND source=%s", (d["source"],))
            cur.execute("INSERT INTO documents (title, category, origin, source, version, masked) "
                        "VALUES (%s,%s,'seed',%s,%s,false) RETURNING id",
                        (d["title"], d["category"], d["source"], d["version"]))
            doc_id = cur.fetchone()[0]
            vecs = embed([c["content"] for c in d["chunks"]])
            for idx, (c, v) in enumerate(zip(d["chunks"], vecs)):
                cur.execute("INSERT INTO chunks (document_id, chunk_idx, content, embedding, meta) VALUES (%s,%s,%s,%s::vector,%s)",
                            (doc_id, idx, c["content"], "[" + ",".join(repr(float(x)) for x in v) + "]",
                             json.dumps(c["meta"], ensure_ascii=False)))
            print(f"documents.id={doc_id} chunks={len(d['chunks'])}")
        cur.execute("DELETE FROM glossary WHERE status='draft' AND source_question_id IS NULL")
        for g in gl:
            cur.execute("INSERT INTO glossary (term_ko, term_vi, term_in, note, status) VALUES (%s,%s,%s,%s,'draft')",
                        (g["term_ko"], g.get("term_vi"), g.get("term_in"), g.get("note")))
        cur.execute("SELECT (SELECT count(*) FROM documents), (SELECT count(*) FROM chunks), (SELECT count(*) FROM glossary), "
                    "(SELECT count(*) FROM chunks WHERE content LIKE '%[src:%'), "
                    "(SELECT count(DISTINCT vector_dims(embedding)) FROM chunks)")
        print("counts documents/chunks/glossary/src-tag-residue/dim-distinct:", cur.fetchone())
        conn.commit()
    return 0


if __name__ == "__main__":
    sys.exit(main())
