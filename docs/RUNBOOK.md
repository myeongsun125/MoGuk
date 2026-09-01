# MoGuk 본선 운영 런북 (9/2~9/3) — 인프라 [BG]
> v2 (0902 00:30) — §3 아이패드·핫스팟 절차·화이트리스트 현황 반영, §7 제거 시점 갱신

## 0. 상수
- 서비스: https://moguk.ai.kr (EIP 3.39.197.190, Caddy 자동 TLS · http→https 리다이렉트)
- EC2: g4dn.xlarge / `ssh -i ~/.ssh/moguk-bg.pem ubuntu@3.39.197.190` (MS: 개인키 등록분) → **반드시 `cd ~/MoGuk`**
- compose 호출 고정: `docker compose -f docker-compose.yml -f docker-compose.gpu.yml` (아래 `dc`로 표기)
- 화이트리스트: `.env` ADMIN_ALLOW_IPS(공백 구분, 쉼표 금지) — /api/v1/admin/* 한정, 근로자 경로(/activate·/ask·/reports·/auth/*) 무관
- 백업: `~/backups/` / 판정 CSV SSOT: `experiments/gate_eval_results/` (삭제·이동 금지)

## 1. 아침 점검 (시연 전 매회, 5분)
1. `dc ps` — 6종 Up (core-api·edge-api healthy)
2. `curl -s -o /dev/null -w "%{http_code}\n" https://moguk.ai.kr/health` → 200
3. `dc exec ollama ollama ps` — qwen3:8b · qwen3:4b · bge-m3 3종 100% GPU, UNTIL 확인 → 없거나 짧으면 §2 워밍업
4. `dc exec core-api printenv TENANT_SLUG BASE_URL GATE_TAU OLLAMA_KEEP_ALIVE` → axis_final / https://moguk.ai.kr / 0.45 / 24h
5. 폰(LTE)에서 https://moguk.ai.kr/activate → 자물쇠 + vi 안내 화면

## 2. 워밍업 (재기동·재부팅·언로드 후 필수 — 3종 전부, keep_alive 24h)

```bash
dc exec core-api python3 -c "import json,urllib.request; body=json.dumps({'model':'qwen3:8b','prompt':'워밍업','stream':False,'think':False,'keep_alive':'24h','options':{'num_predict':10}}).encode(); urllib.request.urlopen(urllib.request.Request('http://ollama:11434/api/generate',body,{'Content-Type':'application/json'}),timeout=300).read(); print('8b warm')"
dc exec core-api python3 -c "import json,urllib.request; body=json.dumps({'model':'qwen3:4b','prompt':'워밍업','stream':False,'think':False,'keep_alive':'24h','options':{'num_predict':10}}).encode(); urllib.request.urlopen(urllib.request.Request('http://ollama:11434/api/generate',body,{'Content-Type':'application/json'}),timeout=300).read(); print('4b warm')"
dc exec core-api python3 -c "import json,urllib.request; body=json.dumps({'model':'bge-m3','input':'워밍업','keep_alive':'24h'}).encode(); urllib.request.urlopen(urllib.request.Request('http://ollama:11434/api/embed',body,{'Content-Type':'application/json'}),timeout=300).read(); print('embed warm')"
dc exec ollama ollama ps
```

- cold 로드 실측: 8b 81s · 4b 23.5s · bge-m3 29s — 로딩 중 Ctrl+C 금지(ollama abort → 큐 정체)
- 원인 기록: core llm_adapter가 요청마다 keep_alive(env OLLAMA_KEEP_ALIVE) 전송 → 24h 미만이면 유휴 시 언로드(0831 리허설 콜드 22s 원인)

## 3. 현장 IP 추가 — 관리자 화면 (본선장 절차, 0901 핫스팟 경로 검증 완료)
- 기기 구성: **관리자 화면 아이패드 = BG 폰 핫스팟 연결·당일 유지** / 근로자 아이패드·폰 = 아무 망(화이트리스트 무관) / BG 노트북 SSH = 아무 망(22 개방)
- 절차(3분):
  1. BG 폰: 와이파이 끄기(행사장 와이파이 자동 접속 방지) → 개인용 핫스팟 켜기 → 충전 연결·저전력 모드 끄기
  2. 관리자 아이패드: BG 핫스팟 연결 → 다른 와이파이 자동 접속 끄기 → 사파리 `ifconfig.me` → 표시 IP 확인
  3. 표시 IP가 등록분(223.38.***, 0901 예행)과 같으면 https://moguk.ai.kr/admin 대시보드 로드 확인 → 완료
     다르면(핫스팟 재시작 시 통신사 재할당 — 가능성 높음): 노트북 SSH → `cd ~/MoGuk && infra/scripts/admin_ip_add.sh <새IP> venue-0902` → 아이패드 /admin 재확인
  4. 시연 중 아이패드·폰 거리 유지(핫스팟 범위), 아이패드가 다른 망으로 넘어가지 않게. 시연 직전 /admin 1회 재확인(§1-5)
  5. 예비: 아이패드 자체 셀룰러가 있으면 그 IP도 등록(30초) — 폰을 촬영·통화에 써야 할 때 대비
- `admin_ip_add.sh`: .env ADMIN_ALLOW_IPS 갱신 + caddy만 재생성(--no-deps), 중복 검사 내장. 검증: 해당 기기에서 /api/v1/admin/dashboard 200
- 화이트리스트 현황(0902 00:30): 6개 — 112.144.197.191(BG 자택, **stale** — 자택 IP 변경됨) / 211.176.35.122(MS) / 210.96.90.90(SB) / 211.177.255.138(JH) / 112.144.197.182(0831 카페, MS 공용) / 223.38.111.192(BG 핫스팟 0901). 221.150.44.3(0901 카페)은 이탈 시 제거 완료
- 제거 시점: 본선장 IP·핫스팟 IP·.182·stale .191 → **9/2 시연 종료 시** 제거 후 통지(§7-2). 팀원 자택 IP 3개는 9/4 원복 시 판정
- 설계 한계: 같은 네트워크의 근로자 폰도 admin API를 통과함(M-15b 수용, 관리자 인증 도입이 해제 조건)

## 4. 재배포 (총괄 지시 시만 — 재기동은 단톡 1줄 선통지 후)

```bash
cd ~/MoGuk && git pull && git log -1 --oneline
dc build --build-arg VITE_USE_MOCK=false frontend
dc build core-api edge-api
dc up -d frontend core-api edge-api          # caddy·ollama·postgres 무재기동
```

검증·보고 항목: https health 200 / 번들 해시(`curl -s https://moguk.ai.kr/ | grep -o 'src="[^"]*"'`) / core printenv 7키(BASE_URL·JOBS_POLL_S·GATE_TAU·BACKTRANS_TIMEOUT_S·GATE_SRC·OLLAMA_KEEP_ALIVE·TENANT_SLUG) / ollama ps / gate_eval_results 보존 / 배포 sha·기동 시각(`dc ps`). 재배포 후 §2 워밍업 3종.

## 5. 테넌트 전환 (axis_demo → axis_final, 총괄 지시 시)
1. [BG] 백업: `dc exec -T postgres pg_dump -U moguk -d moguk > ~/backups/moguk-$(date +%m%d-%H%M)-pre-final.sql`
2. [MS] 001 적용: `sed 's/{slug}/axis_final/g' db/migrations/001_tenant_template.sql | dc exec -T postgres psql -U moguk -d moguk`
3. [MS] LATHE 재수집·적재 → `dc exec postgres psql -U moguk -d moguk -c "SET search_path TO tenant_axis_final, public; SELECT count(*) FROM documents; SELECT count(*) FROM chunks;"` → 각 > 0
4. [BG] `.env` TENANT_SLUG=axis_final → 선통지 → `dc up -d --no-deps core-api` (TENANT_SLUG를 읽는 서비스가 core 외 있으면 함께 — `grep -n TENANT_SLUG docker-compose.yml`로 확인)
5. [BG] 스모크: `dc exec core-api printenv TENANT_SLUG` = axis_final / `curl -s -X POST localhost:8000/api/v1/ask -H "Content-Type: application/json" -d '{"question":"프레스 금형 교체 시 안전 절차는?","lang":"vi"}' | head -c 300` → sources 채워짐
6. [MS] 본선 QR 재발급(BASE_URL https 기준, 토큰 1회용 — 스캔 전 채널 게시 금지)

## 6. 장애 대응
- 로그: `dc logs -f edge-api core-api caddy --tail 5` (caddy 접근 로그 json — 요청 메타·상태·소요만, 헤더 미기록)
- 504 = 릴레이 보류 30s 초과 → 재질의 안내(장애 아님) / 5xx·Traceback → 로그 캡처 후 총괄 / activate 401 = 토큰 소진(1회용) → 예비 QR
- 컨테이너 다운: `dc up -d --no-deps <서비스>` (선통지) → §2 워밍업
- EC2 재부팅: 전 컨테이너 자동 기동(unless-stopped) → §1 점검 → §2 워밍업
- 절대 금지: caddy_data 볼륨 삭제(LE 발급 제한 주 5회) / EC2 stop(모델 언로드·재워밍 필요) / JWT_SECRET 변경(기발급 토큰 전체 무효) / gate_eval_results 삭제

## 7. 원복 (9/4 폐회 후)
1. SG moguk-sg: SSH 0.0.0.0/0 규칙 삭제 → /32 화이트리스트(BG·MS)만 복귀
2. ADMIN_ALLOW_IPS 정리 — 9/2 시연 종료 시: 본선장·핫스팟·.182·stale .191 제거(.env 편집 + `dc up -d --no-deps caddy`) / 9/4: 팀원 자택 IP 판정
3. EC2 처분 시점 총괄 판정 — stop + 스냅샷 권고(크레딧 잔액 9/3 기준 약 $35, 가동 시 하루 약 $13 소진)

## 8. 연락 — 라우팅 규칙
결정·차단 = 총괄 DM / 인프라 변동(재배포·URL·env·재기동) = 단톡 / 기술 교신 = 트랙원 DM. 형식 `[BG|주제|MMDD HH:MM]` 결론 먼저.

## 0901 실측 부기 (총괄)
- 재배포 실측: 1차 16:48~16:55(7분, 빌드 25초 캐시) 3916f7f / 2차 20:29 7427b14(TENANT_SLUG=axis_final 전환 포함). 순서: 단톡 선통지 → compose 워킹트리 정리 → pull(HEAD 대조) → build → up → 실효 env 확인(TENANT_SLUG·TENANT_CRYPTO_KEY 길이·GLOSSARY_INJECT_BACKTRANS/ANSWER·GLOSSARY_STATUS·GATE_TAU·OLLAMA_KEEP_ALIVE) → https 200 → experiments/gate_eval_results 보존 확인. ollama·postgres 무재기동.
- 테넌트 전환: bash scripts/apply_tenant.sh <slug> --compose(파일 모드 664 — bash 호출) → ingest-runner(docker run python:3.11-slim, DATABASE_URL env-file, pip psycopg[binary] httpx pyyaml, moguk_core_net 연결, ingest_seed.py --slug <slug> --sources all) → 검증 SQL(documents/chunks/glossary/vector_dims) → .env TENANT_SLUG → core 재기동. 0901 axis_final: 문서 15·청크 572·용어집 50.
- 관리자 IP: infra/scripts/admin_ip_add.sh <ip> <label>(중복 검사·caddy --no-deps 재생성 10초). 폰 LTE는 관리자 화면 불가(근로자 화면만).
- 키·env 규격: TENANT_CRYPTO_KEY urlsafe-base64 32B(43/44자 허용) — 부재·오류 시 위험보고 접수 실패(CryptoKeyError) → .env 확인 후 core 재기동. GLOSSARY_INJECT_BACKTRANS on / GLOSSARY_INJECT_ANSWER off(스모크 후 on) / GLOSSARY_STATUS approved,draft / PII_MASK on.
- 백업: 수동 pg_dump 0830·0901(~/backups/) + 일일 크론 03:00 KST(backup.sh → gzip → S3 db-backup/ SSE-S3, 로컬 3·S3 14일, 복원 검증 0902 통과).
- 시연 기기 규칙: 아이폰·카톡 인앱·아이패드 Safari만, 삼성 인터넷 미사용(폴백 #80 배포 전), 관리자 언어 토글 클릭 금지(B′).
- 원복: 9/2 시연 종료 시 본선장·핫스팟·.182·.191 IP 제거 / 9/4 SSH 22 원복·자택 IP 3개 판정·EBS 암호화 상신.
