"""/notifications — 범용 알림함(쪽지) (M-06) + /speaking (M-12). [새봄]"""

from fastapi import APIRouter

router = APIRouter(tags=["notifications", "speaking"])


@router.get("/notifications")
def list_notifications() -> list:
    raise NotImplementedError("[새봄] GET /notifications")


@router.post("/notifications/{notification_id}/read")
def read_notification(notification_id: int) -> dict:
    raise NotImplementedError("[새봄] POST /notifications/{id}/read")


@router.get("/speaking/phrases")
def speaking_phrases() -> list:
    raise NotImplementedError("[새봄] GET /speaking/phrases")


@router.post("/speaking/records")
def speaking_record() -> dict:
    # multipart(audio) — 녹음 저장만 (STT 미적용, M-12)
    raise NotImplementedError("[새봄] POST /speaking/records")
