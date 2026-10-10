"""PUK escrow must succeed privately before advancing the remote lifecycle."""

import os
import stat
from uuid import uuid4

import pytest
from pydantic import SecretStr, ValidationError

from stustapay.tse.fiskaly.client import FiskalyError
from stustapay.tse.fiskaly.config import FiskalyConfig, FiskalySettings
from stustapay.tse.fiskaly.secrets import PukStore


@pytest.fixture(autouse=True)
async def setup_test_db_pool():
    yield None


def test_puk_is_private_durable_and_not_overwritten(tmp_path):
    directory = tmp_path / "escrow"
    store = PukStore(directory)
    identity = uuid4()
    assert store.load(identity) is None
    store.save(identity, "fixture-puk-123456")
    store.save(identity, "fixture-puk-123456")
    saved = store.load(identity)
    assert saved is not None and saved.get_secret_value() == "fixture-puk-123456"
    assert stat.S_IMODE(directory.stat().st_mode) == 0o700
    assert stat.S_IMODE((directory / f"{identity}.puk").stat().st_mode) == 0o600
    with pytest.raises(FiskalyError, match="different PUK"):
        store.save(identity, "replacement-puk-123456")
    unchanged = store.load(identity)
    assert unchanged is not None and unchanged.get_secret_value() == "fixture-puk-123456"
    assert not list(directory.glob("*.tmp"))


def test_puk_refuses_shared_directory_and_symlink_files(tmp_path):
    directory = tmp_path / "shared"
    directory.mkdir(mode=0o755)
    with pytest.raises(FiskalyError, match="mode 0700"):
        PukStore(directory).load(uuid4())
    directory.chmod(0o700)
    identity = uuid4()
    external = tmp_path / "other-secret"
    external.write_text("fixture-puk-123456")
    external.chmod(0o600)
    (directory / f"{identity}.puk").symlink_to(external)
    with pytest.raises(FiskalyError, match="cannot be read"):
        PukStore(directory).load(identity)
    assert external.read_text() == "fixture-puk-123456"


def test_puk_durability_failure_blocks_success(tmp_path, monkeypatch):
    def fail_sync(_descriptor):
        raise OSError("fixture failure")

    monkeypatch.setattr(os, "fsync", fail_sync)
    identity = uuid4()
    store = PukStore(tmp_path / "escrow")
    with pytest.raises(FiskalyError, match="stored durably"):
        store.save(identity, "fixture-puk-123456")
    assert store.load(identity) is None


def test_automatic_profiles_can_have_independent_generated_tss_ids(tmp_path):
    profile = FiskalyConfig(
        api_key=SecretStr("fixture-key"),
        api_secret=SecretStr("fixture-secret"),
        auto_provision_tss=True,
        auto_provision_clients=True,
        admin_pin=SecretStr("fixture-private-pin"),
        puk_directory=tmp_path,
    )
    assert "fixture-private-pin" not in profile.model_dump_json()
    assert len(FiskalySettings(profiles={"event-a": profile, "event-b": profile}).profiles) == 2
    with pytest.raises(ValidationError, match="six characters"):
        FiskalyConfig.model_validate({**profile.model_dump(), "admin_pin": "short"})
    with pytest.raises(ValidationError, match="absolute secure PUK"):
        FiskalyConfig.model_validate({**profile.model_dump(), "puk_directory": "relative"})
