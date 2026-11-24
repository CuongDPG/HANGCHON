"""k4 — sao lưu CSDL: pg_dump → gzip → storage, giữ N bản, tải về; thiếu pg_dump thì báo rõ."""

from __future__ import annotations

import gzip
import shutil
from pathlib import Path

import httpx
import pytest

from app.core.config import settings
from app.core.db import SessionLocal
from app.core.storage import get_storage
from app.modules.finance import jobs


def _script(tmp_path: Path, body: str) -> str:
    p = tmp_path / "pg_dump"
    p.write_text("#!/bin/sh\n" + body)
    p.chmod(0o755)
    return str(p)


async def test_missing_pg_dump_is_reported_clearly(
    owner_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "pg_dump_path", "/khong/co/pg_dump")
    cfg = (await owner_client.get("/api/desk/finance/backups/config")).json()
    assert cfg["pg_dump"] is None and cfg["keep"] == 14
    r = await owner_client.post("/api/desk/finance/backups")
    assert r.status_code == 201
    b = r.json()
    assert b["status"] == "failed" and "pg_dump" in b["error"] and "postgresql-client" in b["error"]
    assert (await owner_client.get(f"/api/desk/finance/backups/{b['id']}/download")).status_code == 404


async def test_backup_succeeds_prunes_and_downloads(
    owner_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # pg_dump giả: in ra tham số và mật khẩu nhận qua biến môi trường (không qua dòng lệnh)
    monkeypatch.setattr(
        settings, "pg_dump_path", _script(tmp_path, 'echo "-- dump $*"\necho "-- pw=${PGPASSWORD:+set}"\n')
    )
    await owner_client.patch("/api/desk/control/settings/finance.backup_keep", json={"value": 2})
    ids = []
    for _ in range(3):
        b = (await owner_client.post("/api/desk/finance/backups")).json()
        assert b["status"] == "succeeded", b
        assert b["storage_key"].startswith("private/backups/") and b["storage_key"].endswith(".sql.gz")
        assert b["checksum"].startswith("sha256:") and b["size_bytes"] > 0
        ids.append(b)
    listed = (await owner_client.get("/api/desk/finance/backups")).json()
    assert listed["total"] == 2 and {x["id"] for x in listed["items"]} == {ids[1]["id"], ids[2]["id"]}
    assert not await get_storage().exists(ids[0]["storage_key"])

    r = await owner_client.get(f"/api/desk/finance/backups/{ids[2]['id']}/download")
    assert r.status_code == 200 and r.headers["content-type"] == "application/gzip"
    text = gzip.decompress(r.content).decode()
    assert "--no-owner" in text and "pw=set" in text and "--username" in text
    cfg = (await owner_client.get("/api/desk/finance/backups/config")).json()
    assert cfg["keep"] == 2 and cfg["last_success_at"]


async def test_pg_dump_error_message_is_kept(
    owner_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        settings, "pg_dump_path", _script(tmp_path, 'echo "pg_dump: error: server version mismatch" >&2\nexit 1\n')
    )
    b = (await owner_client.post("/api/desk/finance/backups")).json()
    assert b["status"] == "failed" and "cùng bản" in b["error"] and "mismatch" in b["error"]


async def test_backups_owner_only(helper_client: httpx.AsyncClient) -> None:
    assert (await helper_client.get("/api/desk/finance/backups")).status_code == 403
    assert (await helper_client.post("/api/desk/finance/backups")).status_code == 403


async def test_daily_cron(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(settings, "pg_dump_path", _script(tmp_path, 'echo "-- ok"\n'))
    assert await jobs.daily_backup({"db": SessionLocal}) == "succeeded"


@pytest.mark.skipif(shutil.which("pg_dump") is None, reason="máy không có pg_dump")
async def test_real_pg_dump(owner_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "pg_dump_path", None)
    b = (await owner_client.post("/api/desk/finance/backups")).json()
    assert b["status"] in ("succeeded", "failed") and (b["status"] == "succeeded" or b["error"])


async def test_docker_fallback_when_no_local_pg_dump(
    owner_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Máy không có pg_dump nhưng có container Postgres → chạy `docker exec <container> pg_dump`."""
    from app.modules.finance import service

    fake_docker = _script(tmp_path, 'echo "-- docker $*"\necho "-- pw=${PGPASSWORD:+set}"\n')
    monkeypatch.setattr(settings, "pg_dump_path", None)
    monkeypatch.setattr(service, "_local_pg_dump", lambda: None)
    monkeypatch.setattr(service, "_docker_container", lambda: "hangchon-postgres-1")
    real_which = service.shutil.which
    monkeypatch.setattr(service.shutil, "which", lambda n: fake_docker if n == "docker" else real_which(n))
    import asyncio as _asyncio

    real_exec = _asyncio.create_subprocess_exec

    async def exec_(*args, **kw):
        return await real_exec(fake_docker if args[0] == "docker" else args[0], *args[1:], **kw)

    monkeypatch.setattr(service.asyncio, "create_subprocess_exec", exec_)
    cfg = (await owner_client.get("/api/desk/finance/backups/config")).json()
    assert cfg["pg_dump"] == "docker:hangchon-postgres-1"
    b = (await owner_client.post("/api/desk/finance/backups")).json()
    assert b["status"] == "succeeded", b
    text = gzip.decompress((await owner_client.get(f"/api/desk/finance/backups/{b['id']}/download")).content).decode()
    assert "exec -e PGPASSWORD hangchon-postgres-1 pg_dump" in text and "pw=set" in text
