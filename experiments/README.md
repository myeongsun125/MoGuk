# experiments — 예선 정량 실험 [명선+새봄]

| 파일 | 측정 | 비고 |
|---|---|---|
| `testset/sentences_30.json` | 기준 문장 30 | `{ko, answer_vi, terms[]}` |
| `testset/corrupted_30.json` | 오염 문장 30 | 유형 `term_swap \| negation \| number` × 10 |
| `mistranslation_eval.py` | 측정 #1 용어 오역률 | |
| `gate_eval.py` | 측정 #3 게이트 검출률 → τ 확정 (M-10a, 8/29) | |

검증된 로직만 `backend/app/agents/`로 이식한다.
