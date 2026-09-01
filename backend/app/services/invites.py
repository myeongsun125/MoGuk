"""근로자 초대 발급 (M-32). [새봄]

POST /admin/workers/invite 의 저장소 계층. 발급 측만 담당하며 소비 측은
services/auth.py activate() 다 — 그쪽이 `WHERE i.token = %(token)s` 로 **원값**을
조회하므로 여기서도 토큰 원값을 그대로 적재한다(해시 저장 금지).

규칙 (M-32):
- 토큰 = secrets.token_urlsafe(32) 원값, invites.token(PK)
- expires_at = now() + 72h
- emp_no 중복: workers.emp_no 일치 행이 있고 activated_at IS NULL → 기존 워커 재초대,
  activated_at NOT NULL → 409(이미 활성). 미존재 → workers 신규 INSERT
- emp_no 당 미사용 초대 1건: 재호출 시 그 워커의 used_at IS NULL ∧ expires_at > now() 행을
  expires_at = now() 로 만료 처리한 뒤 신규 발급
- admin_events 1행: actor = risk_reports.ADMIN_ACTOR_UNAUTHENTICATED(M-15b 단일 주입 지점),
  target_type='worker', target_id=workers.id, action='worker_invited', detail=emp_no
- 전 과정 단일 트랜잭션

컬럼·값 집합은 db/migrations/001_tenant_template.sql 이 정본(R4) —
workers(name NOT NULL, emp_no UNIQUE, lang CHECK('vi','in'), invited_at, activated_at),
invites(token PK, worker_id FK, expires_at NOT NULL, used_at).
"""

from __future__ import annotations

import logging
import os
import secrets

from app.services import admin_events, tenancy
from app.services.risk_reports import ADMIN_ACTOR_UNAUTHENTICATED

log = logging.getLogger(__name__)

TOKEN_BYTES = 32                  # secrets.token_urlsafe(32)
INVITE_TTL_H = 72                 # 3일
TARGET_WORKER = "worker"
EV_WORKER_INVITED = "worker_invited"
LANG_VALUES = ("vi", "in")        # 001 workers.lang CHECK 집합

DEFAULT_BASE_URL = "http://localhost"


class WorkerAlreadyActive(Exception):
    """이미 활성화된 워커 — 라우터가 409 로 변환."""


class WorkerNotFound(Exception):
    """대상 워커 없음 — 라우터가 404 로 변환 (send-invite 파트1)."""


class InvalidInviteRequest(Exception):
    """emp_no 미지정·lang 값 이탈 등 요청 형식 위반 — 라우터가 422 로 변환."""


def base_url() -> str:
    """invite_url 접두. 값 확정은 BG — 코드는 env 참조만 한다."""
    return (os.getenv("BASE_URL") or DEFAULT_BASE_URL).rstrip("/")


def build_invite_url(token: str) -> str:
    return f"{base_url()}/activate?token={token}"


def new_token() -> str:
    return secrets.token_urlsafe(TOKEN_BYTES)


# emp_no 는 UNIQUE — 동시 재초대 경합을 막기 위해 행 잠금 후 분기한다.
_SELECT_WORKER = "SELECT id, activated_at FROM workers WHERE emp_no = %(emp_no)s FOR UPDATE"

# send-invite(파트1)는 worker id 로 특정 — 같은 이유로 행 잠금.
_SELECT_WORKER_BY_ID = (
    "SELECT id, emp_no, activated_at FROM workers WHERE id = %(id)s FOR UPDATE"
)

_INSERT_WORKER = """
INSERT INTO workers (name, emp_no, lang, phone, invited_at)
VALUES (%(name)s, %(emp_no)s, %(lang)s, %(phone)s, now())
RETURNING id
"""

# M-39 파트2: phone 은 지정된 경우에만 저장 — 미지정 재초대가 기존 값을 지우지 않는다.
_SET_PHONE = "UPDATE workers SET phone = %(phone)s WHERE id = %(id)s"

# 해석 1: "발급 시 기록" 을 매 발급으로 읽어 재초대에도 갱신한다.
_TOUCH_INVITED_AT = "UPDATE workers SET invited_at = now() WHERE id = %(id)s"

# emp_no 당 미사용 초대 1건 — 살아 있는 기존 초대를 즉시 만료시킨다(행 삭제 없음).
_EXPIRE_PENDING = """
UPDATE invites SET expires_at = now()
WHERE worker_id = %(worker_id)s AND used_at IS NULL AND expires_at > now()
"""

_INSERT_INVITE = """
INSERT INTO invites (token, worker_id, expires_at)
VALUES (%(token)s, %(worker_id)s, now() + (%(ttl_h)s || ' hours')::interval)
"""


def _validate(name: str | None, emp_no: str | None, lang: str | None) -> tuple[str, str, str]:
    """해석 2: emp_no 미지정·빈값 → 422("emp_no 당 1건" 규칙이 emp_no 존재를 전제).

    lang 은 001 CHECK 집합 밖이면 422. name 은 001 NOT NULL 이라 빈값을 막는다.
    """
    if not (emp_no or "").strip():
        raise InvalidInviteRequest("emp_no 는 필수입니다")
    if not (name or "").strip():
        raise InvalidInviteRequest("name 은 필수입니다")
    if lang not in LANG_VALUES:
        raise InvalidInviteRequest(f"lang 은 {list(LANG_VALUES)} 중 하나여야 합니다")
    return name.strip(), emp_no.strip(), lang


def create_invite(
    name: str | None, emp_no: str | None, lang: str | None, phone: str | None = None
) -> dict:
    """초대 발급 → {"invite_url", "worker_id"} (§3:236, M-39 파트2).

    워커 생성·기존 초대 만료·발급·감사를 한 트랜잭션으로. phone 은 선택 — 계약상 형식
    검증 없음, 문자열 그대로 저장(+84·+62 국제표기 무변형). 미지정이면 NULL(신규) /
    기존 값 유지(재초대).
    """
    name, emp_no, lang = _validate(name, emp_no, lang)
    token = new_token()

    with tenancy.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(_SELECT_WORKER, {"emp_no": emp_no})
            row = cur.fetchone()
            if row is None:
                cur.execute(
                    _INSERT_WORKER,
                    {"name": name, "emp_no": emp_no, "lang": lang, "phone": phone},
                )
                worker_id = cur.fetchone()[0]
                reinvite = False
            else:
                worker_id, activated_at = row
                if activated_at is not None:
                    raise WorkerAlreadyActive(f"emp_no={emp_no} 는 이미 활성화된 워커입니다")
                cur.execute(_EXPIRE_PENDING, {"worker_id": worker_id})
                cur.execute(_TOUCH_INVITED_AT, {"id": worker_id})   # 해석 1
                if phone is not None:
                    cur.execute(_SET_PHONE, {"id": worker_id, "phone": phone})
                reinvite = True

            cur.execute(_INSERT_INVITE, {"token": token, "worker_id": worker_id, "ttl_h": INVITE_TTL_H})

            admin_events.record(
                cur,
                actor=ADMIN_ACTOR_UNAUTHENTICATED,
                target_type=TARGET_WORKER,
                target_id=worker_id,
                action=EV_WORKER_INVITED,
                detail=emp_no,
            )
        conn.commit()

    log.info("invite: 발급 worker_id=%s emp_no=%s 재초대=%s ttl_h=%s",
             worker_id, emp_no, reinvite, INVITE_TTL_H)
    return {"invite_url": build_invite_url(token), "worker_id": worker_id}


def send_invite(worker_id: int) -> dict:
    """기존 워커 초대 재발급 → {"share_url": …} (send-invite 파트1 — channel 검증은 라우터).

    발급 규칙은 create_invite 재초대 분기와 동일: 미사용 초대 즉시 만료 → invited_at 갱신
    (해석 1) → 신규 1건(TTL 72h) → admin_events 1행. URL 은 build_invite_url 그대로 —
    invite_url 과 동일한 형태다. 활성 워커는 기존 규칙대로 409 소재(WorkerAlreadyActive).
    """
    token = new_token()

    with tenancy.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(_SELECT_WORKER_BY_ID, {"id": worker_id})
            row = cur.fetchone()
            if row is None:
                raise WorkerNotFound(f"worker_id={worker_id} 는 존재하지 않습니다")
            _, emp_no, activated_at = row
            if activated_at is not None:
                raise WorkerAlreadyActive(f"worker_id={worker_id} 는 이미 활성화된 워커입니다")

            cur.execute(_EXPIRE_PENDING, {"worker_id": worker_id})
            cur.execute(_TOUCH_INVITED_AT, {"id": worker_id})       # 해석 1
            cur.execute(_INSERT_INVITE, {"token": token, "worker_id": worker_id, "ttl_h": INVITE_TTL_H})

            admin_events.record(
                cur,
                actor=ADMIN_ACTOR_UNAUTHENTICATED,
                target_type=TARGET_WORKER,
                target_id=worker_id,
                action=EV_WORKER_INVITED,
                detail=emp_no,
            )
        conn.commit()

    log.info("invite: send-invite 재발급 worker_id=%s emp_no=%s ttl_h=%s",
             worker_id, emp_no, INVITE_TTL_H)
    return {"share_url": build_invite_url(token)}
