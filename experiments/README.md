# experiments — 예선 정량 실험 [명선+새봄]

| 측정 | 스크립트 | 상태 |
|---|---|---|
| 측정 #1 — 용어 오역률 (glossary 주입 전/후) | `mistranslation_eval.py` | 스텁 — 입력 대기 |
| 측정 #3 — 백트랜슬레이션 게이트 검출률 → τ 확정 (M-10a) | `gate_eval.py` | 구현 완료 — 실행 가능 |

검증된 로직만 `backend/app/agents/`로 이식한다.
산출물 형식 검증은 `scripts/seed_check.py`가 담당한다.

## 테스트셋 (07 재생성)

| 파일 | 구성 |
|---|---|
| `testset/sentences_30.json` | 기준셋 30건(S01~S30). `ko` · `answer_vi`(draft) · `terms` · `src` · `safety`. safety:true 20건 |
| `testset/corrupted_30.json` | 오염셋 60건 — `term_swap` 30(C01~C30) · `negation` 20(N01~N20) · `number` 10(M01~M10) |

gate_eval 채점 행은 **정상 30 + 오염 60 = 90행**이다. 배분 근거는 `corrupted_30.json`의 `_meta`가 단일 출처이며, `seed_check.py`는 이 `_meta.counts` 선언과 실배분이 같은지만 본다(건수 하드코딩 없음).

- **number 10건이 상한** — `_meta.number_limit`. `rules.number`("숫자만 변경")를 지키려면 base의 `answer_vi`에 숫자 토큰이 있어야 하는데 그런 문장이 S06·S07·S20~S23·S27·S29·S30의 9개뿐이고 M01~M10이 이미 전부 소진했다(M10은 S06 재사용). 유형별 검출률은 표본 불균형(30/20/10)을 밝히고 읽는다.
- **negation base 풀 소진** — `_meta.negation_base_pool`. safety:true 20문장을 N01~N10(S01·S02·S04·S05·S16·S17·S18·S19·S24·S25)과 N11~N20(S03·S10·S11·S12·S13·S14·S15·S26·S27·S28)이 전량 사용해 추가 배정 여지가 없다.
- **S30 term_swap 대체** — `_meta.term_swap_exception`. S30은 `answer_vi`에 `terms[]`의 term_vi(프레스=`máy dập`)가 나타나지 않아 `rules.term_swap` 대조를 통과할 수 없다. 20건째는 S23의 두 번째 용어축으로 대체했다(C26 프레스축 / C30 금형축).

## 07 재생성 시 확정 사항

- 모든 문장은 `data/sources/`의 근거 문서에서 파생하며 근거 ID를 갖는다. 근거 없는 안전 서술을 만들지 않는다(M-29).
- 오염셋의 `negation` 유형은 **원문 대비 오염문의 부정어 개수 변화 절댓값이 1일 때만 유효**하다(D13-A).
  개수가 같으면 반의어·양태 치환이므로 `negation`이 아니며, 2개 이상 동시 변경도 배제한다.
  vi 부정어 사전은 `scripts/seed_check.py`의 `VI_NEG_LEXICON`이 단일 출처다.
- 번역문의 검수 상태는 항목별 플래그로 표기한다. 원어민 검수 전 시연 문구로 확정하지 않는다.

## gate_eval 실행

```
python experiments/gate_eval.py [--dry-run] [--online-chunks] [--limit N] [--out PATH]
```

| 플래그 | 동작 |
|---|---|
| `--dry-run` | LLM·임베딩을 결정적 mock 으로 대체. 점수는 해시 기반 더미라 **검출률 수치에 의미가 없다**(형식 확인 전용). `--online-chunks`의 근거 조회도 함께 mock 되어 DB 없이 형식을 볼 수 있다 |
| `--online-chunks` | ko 원문으로 `retrieve(k=4)` 한 근거 청크를 `graph`와 같은 `build_context()`로 묶어 `aux_src`로 함께 채점한다. **DB·임베딩이 필요**하다. 게이트 판정축은 질문축 그대로이며(`gate_on` 미변경, M-34 c ②) 근거축은 측정만 한다 |
| `--limit N` | 선두 N 행만 채점(정상 30행이 앞, 이어서 오염 60행) |
| `--out PATH` | CSV 경로. 기본 `out/gate_eval_<ts>.csv`, 요약은 같은 경로의 `.summary.json` |

τ 스윕은 0.50~0.95(step 0.05)이며 요약에 검출률·오탐률·유형별 검출률(`by_type`)과 유형별 표본수(`n_by_type`)를 함께 낸다. `--online-chunks` 실행에서만 근거축 스윕(`by_tau_chunks`·`n_chunks_scored`)이 붙는다.

집계 제외 규칙: `error_class ∈ {local_failed, retrieve_error}`인 행은 되번역이 성립하지 않은 행이라 검출률·오탐률 분모에서 뺀다. 제외 후 표본 수(`n_usable`)를 요약에 함께 적는다.

### CSV 헤더

```
id,base_id,variant_type,safety,src_kind,ko_src,vi_text,back_text,score_question,score_chunks,n_chunks,back_ms,timed_out,error,error_class,chunks_error
```

`score_chunks`·`n_chunks`는 `--online-chunks` 없이는 각각 빈 값·0이다. 근거 조회가 실패해도 그 행의 질문축 점수는 그대로 남고 `chunks_error`에만 사유가 기록된다(근거축 집계에서만 빠진다).
