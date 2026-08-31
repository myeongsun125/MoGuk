# 리허설 체크리스트 (V6 측정+리허설1 · V7 리허설2)

## 시연 전 (매회)
- [ ] ollama 워밍업: 8b·4b·bge-m3 3모델 각 1회 호출 — 재기동 첫 로드 81s/23.5s/28.9s(GPU AMI 실측, 4b 최장 주의), warm 5.2s/3.1s/69ms (M-02a·M-03)
- [ ] 모델 로딩 중 클라이언트 중단(Ctrl+C) 금지 — ollama abort로 큐 정체, 재시작 필요
- [ ] edge /health·core /health 확인
- [ ] 릴레이 보류 상한: edge 보류 30s 초과 시 504 (M-28a, §3 이동분) — 시연 중 504 = 정상 동작(재질의 안내), 장애 아님
- [ ] Caddy /internal 미라우팅 재검(M-22a 1차 방어): 외부에서 `curl -s http://3.39.197.190/internal/relay/pending | head -c 30` → HTML(<!doctype)이면 frontend fallback 흡수 = edge 미도달 정상 (JSON이면 라우팅 오설정)

## 배포·전환
- [ ] blue-green 전환 시 릴레이 인메모리 큐 in-flight 유실 — 전환 전 큐 드레인 확인 (V7, M-28a)
- [ ] 본선 당일 SSH 계획: 핫스팟 IP 사전 등록 vs 한시 개방·폐회 즉시 원복 — 9/1 리허설에서 결정 (SG 22 화이트리스트 원칙 유지)
- [ ] admin 경로 IP 화이트리스트(Caddy, env ADMIN_ALLOW_IPS) — 범위: /api/v1/admin/* 전체, 해제 조건: 관리자 인증 도입(M-15b 해소). 시연장 IP는 9/1 SSH 계획과 함께 결정
- [ ] HTTPS: https://moguk.ai.kr (Caddy 자동 TLS, 인증서는 caddy_data 볼륨 보존 — 볼륨 삭제·재생성 금지, LE 발급 제한 주 5회). QR·검증 URL 전부 https 기준

## 측정 (V6)
- [ ] trace.relay{enqueued_at, leased_at, responded_at}로 릴레이 오버헤드/LLM 시간 분리 — 내부 계측 전용, API 응답 미노출
- [ ] τ·오류 검출률·발표 수치는 하드웨어 확정 상태에서만 (M-03a)

## 리허설 순서 ①~⑩ (V6 리허설1, 2026-08-31 18:30 실시 — main 46d2884, τ 0.45)
| 단계 | 담당 | 조작 | 합격 기준 | 0831 결과 |
|---|---|---|---|---|
| ① 초대→활성화→/ask | SB | QR 스캔→PIN→/ask vi | activate 200·답변 vi·sources≥1·gated=false·score 배지 | PASS 0.72 |
| ② 법령 질의 | SB | /ask 별표4 vi | "12 giờ"·doc4 인용·score≥τ | PASS 0.71 |
| ③ 무근거 | SB | /ask 코퍼스 부재 질의 | 단일 문구·answer 비움·gate_reason=grounding·unanswered +1 | PASS |
| ④ 위험보고 제출 | JH | 활성화→제출(in) | 202→수초 내 done·ko_summary·severity | PASS 1.0s high |
| ⑦ confirm | JH | 근로자 confirm | reporter_confirmed=true | PASS |
| ⑤ ack→resolve | JH | 관리자 전이 | submitted→acknowledged→resolved | PASS |
| ⑥ 세부 조회 | JH | 상세→원문 | original_text + original_viewed 이벤트 | PASS |
| ⑧ 대시보드 | JH | KPI | open 0·resolved n·unanswered·추이 | PASS |
| ⑨ glossary | JH+SB | approve/reject | 상태 전이·draft −2·admin_events 2행 | PASS |
| ⑩ 감사 로그 | JH | /admin/events | 전이·열람·승인 이벤트 표시 | 부분 → M-36 |
측정: 릴레이 enqueue→lease 10~40ms, LLM 2~3s, 되번역 0.5~1.6s, 콜드 22s(OLLAMA_KEEP_ALIVE 10m → 24h로 해소).
결함: D-1 활성화 상태 안내 / D-2 lang(M-35) / D-3 워커 네비 / D-4 confirm 신원 / D-5 반려 사유 / D-6 감사 로그(M-36) / D-7 KST / D-8 요약 0.01s.
- [ ] 시연 전: /ask 워밍 1회(콜드 재발 시 대비), 초대 토큰은 담당자별 1장(1회용), 관리자 시연은 화이트리스트 IP 노트북
