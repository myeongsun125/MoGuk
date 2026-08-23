"""알림함(notifications) 적재 — type: admin_answer|report_reply|learning_reminder|system (M-06). [새봄]"""


def notify(worker_id: int, type_: str, title: str, body: str) -> int:
    # 시그니처는 §4 동결 대상 아님 — 구현 시 확정 (워크로그 근거)
    raise NotImplementedError("[새봄] services.notify.notify")
