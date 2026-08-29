<!--
raw/ 재배포 검토 트리거: 레포 공개 전환 / raw 포함 외부 제출 / 상업화. 해당 시 미표시
2건(M-96·M-138)과 PRESS-3 페이지 추출본 우선 재검토.
-->
# data/seed/kosha — KOSHA 실자료 자리 (07, M-29)

**이 디렉터리에는 생성물(합성 문서)을 두지 않는다.** 07부터 KOSHA·법령·NCS 원문은 `data/sources/`로 이관되었다.

| 항목 | 위치 |
|---|---|
| 근거 자료 SSOT(ID·라이선스·상태) | `data/sources/manifest.yaml` (20항목, fetched 17) |
| 원문 파일 | `data/sources/raw/` (18파일, EOL 변환 제외) |
| 텍스트 변환본(인용 대조용) | `data/sources/text/<ID>.md` (13건, `scripts/convert_sources.py`) |
| RAG 비적재 영상·교육자료 링크 | `data/sources/media_links.md` (D10) |

## 시드에서의 인용 규칙

- 시드 문장은 `[src: <manifest ID> <위치>]`로 근거를 표기한다. manifest에 없는 ID는 어디서도 쓸 수 없다.
- 공공누리 4유형(KOSHA-PRESS·KOSHA-COMMON-1 등)은 「」 안 원문 무변형 발췌만, 2유형은 발췌·재구성, 법령·NCS·KOSHA GUIDE(M-96·M-138)는 출처 표시 인용.
- `KOSHA-CASE-1`(role: case)과 `KOSHA-PRESS-3`(jpg)은 매뉴얼·퀴즈·테스트셋 근거로 인용하지 않는다.
- 검증: `python scripts/seed_check.py` (① [src:] 커버리지 · ② manifest 존재 · ③ 4유형 무변형 · ⑥ case 인용 0).

## 이 디렉터리의 용도

- V6+ 교육 콘텐츠 연계 시 KOSHA 다국어 자료(KOSHA-ML-01·EPS-GUIDE, 현재 pending)를 반입할 자리.
- 반입 규칙: 원본 무수정, manifest 등재 후 파일명 `kosha_<주제>_<언어코드>.<확장자>`, 공공누리 유형 확인 전 반입 보류.

**상태: 07 시점 실파일 없음(.gitkeep). 근거 자료는 data/sources/ 참조.**
