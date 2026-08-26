# 2026-08-26 — main 히스토리 재작성 1회 (규칙 예외 기록)

**[MS|V1|0826 15:13]** main 히스토리 재작성 1회 — 사유: 커밋 트레일러 제거(공개 전환 대비), 총괄 승인, 재발 방지 = settings.json attribution + PR 반려 규칙. **이후 main force-push는 재금지.**

| 항목 | 내용 |
|---|---|
| 위반 규칙 | Git 규칙 v1.0 "force push 금지, main에는 어떤 경우에도 금지" · WORKORDER §1 "main 직push 금지" |
| 사건 | Claude Code가 커밋 메시지에 자동 삽입한 `Co-Authored-By: Claude` 트레일러가 main·feat 브랜치 커밋 15건에 포함됨. 레포 공개 전환 시 contributor 목록에 Claude 노출 |
| 조치 (2026-08-25 저녁) | `git filter-branch --msg-filter`로 트레일러만 제거 후 main·feat/ms-docs-final·feat/skeleton-v3 force-push. 트리·작성자·author/committer 일시 동일, 커밋 메시지·해시만 변경 (main afacb96→156a188, feat/ms-docs-final 371d45a→407d8f3, feat/skeleton-v3 5f35487→003446d) |
| 승인 | 총괄(명선) 실행 · 병갑 사후 승인(PR #4 리뷰 기준 해시 407d8f3로 앵커) · 팀 공지 완료 |
| 영향 | 병갑 브랜치(feat/bg-ci, feat/bg-infra-skeleton)는 재작성 이전 분기 → 영향 없음. 8/23 이후 main pull한 로컬은 `git reset --hard origin/main` 필요 |
| 재발 방지 | ① 각자 `~/.claude/settings.json`에 `"attribution": {"commit": "", "pr": ""}` ② `Co-Authored-By: Claude` 포함 커밋은 PR 반려 (GIT_RULES.md G4 커밋 시 조항 반영) ③ main force-push 재금지 — 본 건은 선례가 아닌 기록된 1회성 조치 |
| 증거 | PR #4 코멘트 https://github.com/myeongsun125/MoGuk/pull/4#issuecomment-5421305951 |
