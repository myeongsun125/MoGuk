# DECISIONS — M-xx 결정 대장 색인

결정 본문의 원본은 [skeleton-v3.md §8](skeleton-v3.md#8-m-xx-결정-대장) (M-01 ~ M-27). 이 파일은 **비준 이후 추가·변경된 결정의 근거(WORKLOG/추적표) 색인**만 유지한다 — 본문을 여기 중복하지 않는다(R4). 예선 문서 대비 변경 사유(R6)는 [TRACEABILITY.md](TRACEABILITY.md)가 색인한다.

| ID | 한 줄 | 근거(WORKLOG) | 상태 |
|---|---|---|---|
| M-22 | edge-api 내부 DB 자격증명 0 · /health = self + core 릴레이 · core_net internal | [2026-08-23_skeleton-v3-security-gates.md](WORKLOG/2026-08-23_skeleton-v3-security-gates.md) | 확정 |
| M-23 | 암호문 시연 저장소 edge-db 자리 (published_content) | 동상 | 8/26 알파 확정 |
| M-10 개정 | 이중 검증 전면 → 안전 카테고리 선별 게이트 (R6 사유 소급) | [TRACEABILITY.md](TRACEABILITY.md) #11 | 확정 |
| M-16 개정 | Airflow → Dagster 사유 소급 (R6) | [TRACEABILITY.md](TRACEABILITY.md) #17 | 확정 |
| M-17a | 외부 API = OpenAI gpt-4o-mini · 8s · external→local 폴백 | [TRACEABILITY.md](TRACEABILITY.md) #18 (PR #4 대조: 레포 '미결'→확정) | 확정 |
| M-24 | 문서 위계: PRELIM 상위 계약 · M-xx 유일 변경 경로 · R6 신설 · 진입점 BLUEPRINT | [TRACEABILITY.md](TRACEABILITY.md) 요청 2 | 확정 |
| M-25 | 미디어 플로우: edge 암호화 단기 버퍼 → core outbound pull → 처리 → 사본 삭제 · S3=DB 백업 전용 | [TRACEABILITY.md](TRACEABILITY.md) #23 | 확정 |
| M-26 | 본선 시연=전체 플로우 · "선택 모듈 1종"=안전교육(상한 아님) | [TRACEABILITY.md](TRACEABILITY.md) #24 | 확정 |
| M-27 | PRELIM 정량 목표 ⑤ 설문 미확보 — 조작 금지, 방법·목표로 서술 | [TRACEABILITY.md](TRACEABILITY.md) #25 | 보류(추후 보정) |
