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


# ---- chép ra ngoài máy chủ + kiểm khôi phục ----------------------------------------------------------------------

DUMP = """--
-- PostgreSQL database dump
--
CREATE TABLE public.users (
    id uuid NOT NULL
);
CREATE TABLE public.approval_items (
    id uuid NOT NULL
);
CREATE TABLE public.orders (
    id uuid NOT NULL
);
CREATE TABLE public.products (
    id uuid NOT NULL
);
CREATE TABLE public.ledger_entries (
    id uuid NOT NULL
);
COPY public.users (id) FROM stdin;
\\.
--
-- PostgreSQL database dump complete
--
"""


def fake_pg_dump(tmp_path: Path, body: str = DUMP) -> str:
    """pg_dump giả in ra một bản dump SQL thuần có đủ đầu/cuối tệp và các bảng cốt lõi."""
    (tmp_path / "dump.sql").write_text(body)
    return _script(tmp_path, f'cat "{tmp_path / "dump.sql"}"\n')


class FakeRemote:
    """Kho ngoài máy chủ giả (thay driver `s3`): giữ tệp trong bộ nhớ, `fail=True` thì báo lỗi mạng."""

    name = "s3"

    def __init__(self, fail: bool = False) -> None:
        self.files: dict[str, bytes] = {}
        self.fail = fail

    async def put(self, key: str, data: bytes, content_type: str = "application/octet-stream"):
        if self.fail:
            raise ConnectionError("mất mạng tới kho")
        self.files[key] = data

    async def get(self, key: str) -> bytes:
        return self.files[key]

    async def delete(self, key: str) -> None:
        self.files.pop(key, None)

    async def exists(self, key: str) -> bool:
        return key in self.files


@pytest.fixture
def remote(monkeypatch: pytest.MonkeyPatch):
    from app.integrations import base

    fake = FakeRemote()
    monkeypatch.setitem(base._instances, ("storage", "s3"), fake)
    monkeypatch.setattr(settings, "backup_offsite_driver", "s3")
    return fake


async def test_no_offsite_by_default(owner_client: httpx.AsyncClient, monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(settings, "pg_dump_path", fake_pg_dump(tmp_path))
    b = (await owner_client.post("/api/desk/finance/backups")).json()
    assert b["status"] == "succeeded" and b["offsite_key"] is None and b["offsite_driver"] is None
    cfg = (await owner_client.get("/api/desk/finance/backups/config")).json()
    assert cfg["offsite_driver"] is None and cfg["storage_driver"] == "local" and cfg["last_success_id"] == b["id"]


async def test_backup_copied_offsite_and_pruned(
    owner_client: httpx.AsyncClient, monkeypatch, tmp_path: Path, remote: FakeRemote
) -> None:
    monkeypatch.setattr(settings, "pg_dump_path", fake_pg_dump(tmp_path))
    await owner_client.patch("/api/desk/control/settings/finance.backup_keep", json={"value": 1})
    first = (await owner_client.post("/api/desk/finance/backups")).json()
    assert first["offsite_driver"] == "s3" and first["offsite_at"] and first["offsite_key"] == first["storage_key"]
    assert remote.files[first["storage_key"]] == await get_storage().get(first["storage_key"])
    second = (await owner_client.post("/api/desk/finance/backups")).json()
    assert list(remote.files) == [second["storage_key"]]  # bản cũ bị dọn ở cả hai nơi
    cfg = (await owner_client.get("/api/desk/finance/backups/config")).json()
    assert cfg["offsite_driver"] == "s3" and cfg["last_offsite_at"] and cfg["offsite_error"] is None


async def test_offsite_failure_keeps_local_backup(
    owner_client: httpx.AsyncClient, monkeypatch, tmp_path: Path, remote: FakeRemote
) -> None:
    remote.fail = True
    monkeypatch.setattr(settings, "pg_dump_path", fake_pg_dump(tmp_path))
    b = (await owner_client.post("/api/desk/finance/backups")).json()
    assert b["status"] == "succeeded" and b["offsite_at"] is None and "mất mạng" in b["offsite_error"]
    cfg = (await owner_client.get("/api/desk/finance/backups/config")).json()
    assert "mất mạng" in cfg["offsite_error"]


async def test_storage_s3_means_backup_already_offsite(
    owner_client: httpx.AsyncClient, monkeypatch, tmp_path: Path
) -> None:
    from app.integrations import base

    fake = FakeRemote()
    monkeypatch.setitem(base._instances, ("storage", "s3"), fake)
    monkeypatch.setattr(settings, "storage_driver", "s3")
    monkeypatch.setattr(settings, "pg_dump_path", fake_pg_dump(tmp_path))
    b = (await owner_client.post("/api/desk/finance/backups")).json()
    assert (
        b["offsite_driver"] == "s3" and b["offsite_key"] == b["storage_key"] and list(fake.files) == [b["storage_key"]]
    )


async def test_verify_backup_ok_and_detects_damage(
    owner_client: httpx.AsyncClient, helper_client: httpx.AsyncClient, monkeypatch, tmp_path: Path, remote
) -> None:
    monkeypatch.setattr(settings, "pg_dump_path", fake_pg_dump(tmp_path))
    b = (await owner_client.post("/api/desk/finance/backups")).json()
    assert (await helper_client.post(f"/api/desk/finance/backups/{b['id']}/verify")).status_code == 403
    r = await owner_client.post(f"/api/desk/finance/backups/{b['id']}/verify")
    v = r.json()
    assert r.status_code == 200 and v["verify_ok"] is True and v["verified_at"], v
    assert (
        "checksum khớp" in v["verify_note"]
        and "5 bảng" in v["verify_note"]
        and "ngoài máy chủ khớp" in v["verify_note"]
    )

    # bản trên máy chủ bị sửa → checksum lệch
    await get_storage().put(b["storage_key"], gzip.compress(b"-- khac"), "application/gzip")
    v = (await owner_client.post(f"/api/desk/finance/backups/{b['id']}/verify")).json()
    assert v["verify_ok"] is False and "KHÔNG khớp" in v["verify_note"]
    # dữ liệu không bị khôi phục đè: chỉ ghi kết quả kiểm
    assert (await owner_client.get("/api/desk/finance/backups")).json()["total"] == 1


async def test_verify_detects_truncated_dump(owner_client: httpx.AsyncClient, monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(settings, "pg_dump_path", fake_pg_dump(tmp_path, DUMP.split("COPY")[0]))
    b = (await owner_client.post("/api/desk/finance/backups")).json()
    v = (await owner_client.post(f"/api/desk/finance/backups/{b['id']}/verify")).json()
    assert v["verify_ok"] is False and "cắt dở" in v["verify_note"]
    missing = await owner_client.post("/api/desk/finance/backups/00000000-0000-0000-0000-000000000000/verify")
    assert missing.status_code == 404


async def test_last_error_shown_until_next_success(
    owner_client: httpx.AsyncClient, monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(settings, "pg_dump_path", "/khong/co/pg_dump")
    await owner_client.post("/api/desk/finance/backups")
    cfg = (await owner_client.get("/api/desk/finance/backups/config")).json()
    assert "pg_dump" in cfg["last_error"] and cfg["last_error_at"] and cfg["last_success_at"] is None
    monkeypatch.setattr(settings, "pg_dump_path", fake_pg_dump(tmp_path))
    await owner_client.post("/api/desk/finance/backups")
    cfg = (await owner_client.get("/api/desk/finance/backups/config")).json()
    assert cfg["last_error"] is None and cfg["last_success_at"]


@pytest.mark.skipif(shutil.which("docker") is None, reason="máy không có docker")
async def test_real_dump_via_docker_verifies(owner_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Máy dev: pg_dump thật (trên máy hoặc trong container Postgres) cho bản dump kiểm khôi phục được."""
    from app.modules.finance import service

    monkeypatch.setattr(settings, "pg_dump_path", None)
    if service.pg_dump_path() is None:
        pytest.skip("không có pg_dump trên máy và không có container Postgres")
    b = (await owner_client.post("/api/desk/finance/backups")).json()
    assert b["status"] == "succeeded", b
    v = (await owner_client.post(f"/api/desk/finance/backups/{b['id']}/verify")).json()
    assert v["verify_ok"] is True, v["verify_note"]


async def test_s3_credentials_enable_offsite_even_with_local_storage(
    owner_client: httpx.AsyncClient, monkeypatch, tmp_path: Path
) -> None:
    """STORAGE_DRIVER=local (ảnh trên máy chủ) nhưng đã điền S3_* → bản sao lưu tự chép lên S3/R2."""
    from app.integrations import base

    fake = FakeRemote()
    monkeypatch.setitem(base._instances, ("storage", "s3"), fake)
    for k, v in (("s3_bucket", "sao-luu"), ("s3_access_key", "k"), ("s3_secret_key", "s")):
        monkeypatch.setattr(settings, k, v)
    monkeypatch.setattr(settings, "pg_dump_path", fake_pg_dump(tmp_path))
    b = (await owner_client.post("/api/desk/finance/backups")).json()
    assert b["offsite_driver"] == "s3" and b["offsite_at"] and list(fake.files) == [b["storage_key"]]
