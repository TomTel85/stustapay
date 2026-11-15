import json
from uuid import uuid4

import pytest
from pydantic import SecretStr

from stustapay.tse.fiskaly import archive
from stustapay.tse.fiskaly.client import FiskalyError, FiskalyHTTPError
from stustapay.tse.fiskaly.config import FiskalyConfig, FiskalySettings


@pytest.mark.asyncio
async def test_export_retry_and_no_overwrite(config, tmp_path, monkeypatch):
    tss_id = uuid4()
    profile = FiskalyConfig(api_key=SecretStr("key"), api_secret=SecretStr("secret"), tss_id=tss_id)
    row = {"type": "fiskaly", "fiskaly_job_id": None, "fiskaly_profile": "site", "fiskaly_tss_id": tss_id}

    class Connection:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            pass

        async def fetchrow(self, *_):
            return row

    class Pool:
        def acquire(self):
            return Connection()

        async def close(self):
            pass

    class Database:
        async def create_pool(self):
            return Pool()

    calls = []

    class Client:
        def __init__(self, _):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            pass

        async def request(self, method, path, *, payload=None):
            calls.append((method, path, payload))
            if len(calls) == 1:
                raise FiskalyHTTPError(404)
            identity = path.split("?")[0].split("/")[-1]
            return {
                "_id": identity,
                "tss_id": str(tss_id),
                "_env": "TEST",
                "state": "PENDING" if method == "PUT" else "COMPLETED",
            }

        async def download_export(self, _, __, destination):
            destination.write(b"tar-data")

    monkeypatch.setattr(archive, "get_database", lambda _: Database())
    monkeypatch.setattr(archive, "FiskalyClient", Client)
    config = config.model_copy(update={"fiskaly": FiskalySettings(profiles={"site": profile})})
    output = tmp_path / "export.tar"
    assert "PENDING" in await archive.export_archive(config, 1, 10, 20, output)
    identity = json.loads((tmp_path / "export.tar.json").read_text())["export_id"]
    assert calls[1] == ("PUT", f"tss/{tss_id}/export/{identity}?start_date=10&end_date=20", {})
    await archive.export_archive(config, 1, 10, 20, output)
    assert calls[2] == ("GET", f"tss/{tss_id}/export/{identity}", None)
    assert output.read_bytes() == b"tar-data"
    with pytest.raises(FiskalyError, match="already exists"):
        await archive.export_archive(config, 1, 10, 20, output)


def test_atomic_write_does_not_replace(tmp_path):
    path = tmp_path / "archive"
    with archive.new_archive_file(path) as file:
        file.write(b"first")
    with pytest.raises(FileExistsError), archive.new_archive_file(path) as file:
        file.write(b"second")
    assert path.read_bytes() == b"first"


def test_incomplete_export_is_not_published(tmp_path):
    path = tmp_path / "archive"
    with pytest.raises(RuntimeError), archive.new_archive_file(path) as file:
        file.write(b"partial")
        raise RuntimeError("interrupted")
    assert not list(tmp_path.iterdir())
