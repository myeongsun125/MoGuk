# experiments — 예선 정량 실험 [명선+새봄]

| 파일 | 측정 | 비고 |
|---|---|---|
| `testset/sentences_30.json` | 기준 문장 30 | `{id, ko, answer_vi, terms[], source, intent, draft}` · 안전 지시문 19/30 |
| `testset/corrupted_30.json` | 오염 문장 30 | `{id, base_id, type, corrupted_vi, note}` · 유형 `term_swap \| negation \| number` × 10 |
| `mistranslation_eval.py` | 측정 #1 용어 오역률 | |
| `gate_eval.py` | 측정 #3 게이트 검출률 → τ 확정 (M-10a, 8/29) | |

검증된 로직만 `backend/app/agents/`로 이식한다.

> 두 파일의 `answer_vi`·`corrupted_vi`는 **전부 초안(draft)** 이다. 원어민 검수 전 시연 문구로 확정하지 않는다.
> 문장은 `data/seed/manuals/`의 두 매뉴얼에서 파생되며, `terms[]`는 `data/seed/glossary/glossary_50.json`의 `term_ko`를 참조한다.
