"""M-33 — jobs 러너 기동·종료 (core-api lifespan). [새봄]

검증 대상 계약:
- 기동: core 역할 lifespan 이 run_jobs 를 백그라운드 태스크 1건으로 띄운다
       (BLUEPRINT "jobs 워커: core-api 내장"). edge 는 띄우지 않는다(M-22 — DB 자격 없음).
- 종료: stop 이벤트 set 시 루프가 빠져나온다. asyncio.to_thread 로 도는 동기 루프라
       신호는 스레드 안전한 threading.Event(릴레이 폴러의 asyncio.Event 는 코루틴 전용).
- 호환: stop 기본값 None — 기존 호출부 시그니처를 깨지 않는다.
- poll_s: env JOBS_POLL_S, 기본값은 기존 run_jobs 기본값(2.0) 그대로.
"""

import asyncio
import inspect
import threading
import time

import pytest

from app.main import build_app
from app.workers import job_runner


@pytest.fixture(autouse=True)
def _base_env(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://test:test@127.0.0.1:1/test")
    monkeypatch.delenv("JOBS_POLL_S", raising=False)
    monkeypatch.delenv("API_ROLE", raising=False)


# ── 시그니처 호환 ─────────────────────────────────────────

def test_run_jobs_signature_keeps_existing_callers():
    sig = inspect.signature(job_runner.run_jobs)
    assert list(sig.parameters) == ["poll_s", "stop"]
    assert sig.parameters["poll_s"].default == 2.0          # 기존 기본값 무변경
    assert sig.parameters["stop"].default is None           # 인자 없이 호출 가능


def test_default_poll_s_unchanged():
    assert job_runner.DEFAULT_POLL_S == 2.0
    assert job_runner.poll_s() == 2.0


@pytest.mark.parametrize(
    "raw,expected",
    [("5", 5.0), ("0.5", 0.5), ("", 2.0), ("abc", 2.0), ("0", 2.0), ("-3", 2.0)],
)
def test_poll_s_env_override(monkeypatch, raw, expected):
    if raw == "":
        monkeypatch.delenv("JOBS_POLL_S", raising=False)
    else:
        monkeypatch.setenv("JOBS_POLL_S", raw)
    assert job_runner.poll_s() == expected


# ── 종료 신호 ─────────────────────────────────────────────

def test_run_jobs_exits_when_stop_is_set(monkeypatch):
    """stop.set() 이면 루프가 끝난다 — 태스크가 매달리지 않는다."""
    calls = {"n": 0}

    def _once():
        calls["n"] += 1
        return False          # 큐가 비었다 → _idle 로 들어간다

    monkeypatch.setattr(job_runner, "process_once", _once)
    stop = threading.Event()

    done = threading.Event()

    def _run():
        job_runner.run_jobs(0.01, stop=stop)
        done.set()

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    time.sleep(0.05)
    stop.set()

    assert done.wait(2.0), "stop.set() 후에도 run_jobs 가 종료되지 않았다"
    t.join(1.0)
    assert not t.is_alive()
    assert calls["n"] >= 1


def test_stop_set_before_start_runs_zero_iterations(monkeypatch):
    """이미 set 된 stop 으로 들어오면 한 바퀴도 돌지 않는다."""
    monkeypatch.setattr(job_runner, "process_once", lambda: pytest.fail("루프가 돌았다"))
    stop = threading.Event()
    stop.set()
    job_runner.run_jobs(0.01, stop=stop)      # 즉시 반환


def test_idle_wakes_immediately_on_stop():
    """_idle 은 stop 신호에 즉시 깨어난다 — 종료가 poll_s 만큼 지연되지 않는다."""
    stop = threading.Event()
    threading.Timer(0.02, stop.set).start()
    t0 = time.perf_counter()
    job_runner._idle(stop, 5.0)
    assert time.perf_counter() - t0 < 1.0


def test_loop_error_path_also_honors_stop(monkeypatch):
    """예외 경로에서도 stop 을 존중한다 — DB 단절 중 종료가 막히지 않는다."""
    def _boom():
        raise RuntimeError("db down")

    monkeypatch.setattr(job_runner, "process_once", _boom)
    stop = threading.Event()
    done = threading.Event()

    def _run():
        job_runner.run_jobs(0.01, stop=stop)
        done.set()

    threading.Thread(target=_run, daemon=True).start()
    time.sleep(0.05)
    stop.set()
    assert done.wait(2.0), "예외 루프가 stop 에 반응하지 않았다"


# ── lifespan 기동 ─────────────────────────────────────────

def _patch_workers(monkeypatch, started: dict):
    async def _noop(stop):
        await stop.wait()

    def _run_jobs(poll_s=2.0, stop=None):
        started["run_jobs"] = {"poll_s": poll_s, "stop": stop}
        if stop is not None:
            stop.wait()

    monkeypatch.setattr("app.workers.relay_poller.run_poller", _noop)
    monkeypatch.setattr("app.workers.heartbeat.run_heartbeat", _noop)
    monkeypatch.setattr("app.workers.job_runner.run_jobs", _run_jobs)


@pytest.mark.asyncio
async def test_core_lifespan_starts_job_runner(monkeypatch):
    started: dict = {}
    _patch_workers(monkeypatch, started)
    monkeypatch.setenv("API_ROLE", "core")

    app = build_app("core")
    async with app.router.lifespan_context(app):
        await asyncio.sleep(0.05)
        assert "run_jobs" in started, "core lifespan 이 run_jobs 를 띄우지 않았다"
        assert started["run_jobs"]["poll_s"] == job_runner.DEFAULT_POLL_S
        assert isinstance(started["run_jobs"]["stop"], threading.Event)
        assert not started["run_jobs"]["stop"].is_set()

    # 종료 후 stop 이 set 되어 스레드가 빠져나온다
    assert started["run_jobs"]["stop"].is_set()


@pytest.mark.asyncio
async def test_edge_lifespan_does_not_start_job_runner(monkeypatch):
    """edge 는 DB 자격이 없다(M-22) — 러너를 띄우지 않는다."""
    started: dict = {}
    _patch_workers(monkeypatch, started)
    monkeypatch.setenv("API_ROLE", "edge")

    app = build_app("edge")
    async with app.router.lifespan_context(app):
        await asyncio.sleep(0.05)
    assert "run_jobs" not in started


@pytest.mark.asyncio
async def test_core_lifespan_passes_env_poll_s(monkeypatch):
    started: dict = {}
    _patch_workers(monkeypatch, started)
    monkeypatch.setenv("API_ROLE", "core")
    monkeypatch.setenv("JOBS_POLL_S", "0.25")

    app = build_app("core")
    async with app.router.lifespan_context(app):
        await asyncio.sleep(0.05)
        assert started["run_jobs"]["poll_s"] == 0.25
