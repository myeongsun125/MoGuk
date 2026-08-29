# 리허설 체크리스트 (V6 측정+리허설1 · V7 리허설2)

## 시연 전 (매회)
- [ ] ollama 워밍업: 8b·4b·bge-m3 3모델 각 1회 호출 — 재기동 첫 로드 81s/23.5s/28.9s(GPU AMI 실측, 4b 최장 주의), warm 5.2s/3.1s/69ms (M-02a·M-03)
- [ ] 모델 로딩 중 클라이언트 중단(Ctrl+C) 금지 — ollama abort로 큐 정체, 재시작 필요
- [ ] edge /health·core /health 확인
- [ ] 릴레이 보류 상한: edge 보류 30s 초과 시 504 (M-28a, §3 이동분) — 시연 중 504 = 정상 동작(재질의 안내), 장애 아님
- [ ] Caddy /internal 미라우팅 재검(M-22a 1차 방어): 외부에서 `curl -s http://3.39.197.190/internal/relay/pending | head -c 30` → HTML(<!doctype)이면 frontend fallback 흡수 = edge 미도달 정상 (JSON이면 라우팅 오설정)

## 배포·전환
- [ ] blue-green 전환 시 릴레이 인메모리 큐 in-flight 유실 — 전환 전 큐 드레인 확인 (V7, M-28a)

## 측정 (V6)
- [ ] trace.relay{enqueued_at, leased_at, responded_at}로 릴레이 오버헤드/LLM 시간 분리 — 내부 계측 전용, API 응답 미노출
- [ ] τ·오류 검출률·발표 수치는 하드웨어 확정 상태에서만 (M-03a)
