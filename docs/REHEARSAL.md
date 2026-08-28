# 리허설 체크리스트 (V6 측정+리허설1 · V7 리허설2)

## 시연 전 (매회)
- [ ] ollama 워밍업: 8b·bge-m3 각 1회 호출 — 재기동 첫 로드 81s/28.9s(GPU AMI 실측), warm 5.2s/69ms (M-02a)
- [ ] 모델 로딩 중 클라이언트 중단(Ctrl+C) 금지 — ollama abort로 큐 정체, 재시작 필요
- [ ] edge /health·core /health 확인

## 배포·전환
- [ ] blue-green 전환 시 릴레이 인메모리 큐 in-flight 유실 — 전환 전 큐 드레인 확인 (V7, M-28a)

## 측정 (V6)
- [ ] trace.relay{enqueued_at, leased_at, responded_at}로 릴레이 오버헤드/LLM 시간 분리 — 내부 계측 전용, API 응답 미노출
- [ ] τ·오류 검출률·발표 수치는 하드웨어 확정 상태에서만 (M-03a)
