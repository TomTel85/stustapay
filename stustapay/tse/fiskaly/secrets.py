"""Local PUK escrow; never advance TSS creation before durable storage succeeds."""

import json
import os
import stat
from pathlib import Path
from uuid import UUID, uuid4

from cryptography.fernet import Fernet, InvalidToken
from pydantic import SecretStr

from .client import FiskalyError


class CredentialVault:
    """Authenticated encryption with a separate deployment key and record binding."""

    def __init__(self, key: SecretStr):
        self._cipher = Fernet(key.get_secret_value().encode())

    def encrypt(self, scope: str, value: dict[str, str]) -> str:
        return self._cipher.encrypt(json.dumps({"scope": scope, "value": value}).encode()).decode()

    def decrypt(self, scope: str, ciphertext: str) -> dict[str, str]:
        try:
            data = json.loads(self._cipher.decrypt(ciphertext.encode()))
            if data["scope"] != scope or not isinstance(data["value"], dict):
                raise ValueError()
            if any(not isinstance(v, str) for v in data["value"].values()):
                raise ValueError()
            return data["value"]
        except (InvalidToken, ValueError, KeyError, TypeError):
            raise FiskalyError("Fiskaly encrypted credentials are unavailable or belong to another resource") from None


class PukStore:
    def __init__(self, directory: Path):
        self.directory = directory

    def _open_directory(self) -> int:
        try:
            self.directory.mkdir(mode=0o700, exist_ok=True)
            descriptor = os.open(self.directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            info = os.fstat(descriptor)
            if info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) & 0o077:
                os.close(descriptor)
                raise FiskalyError("Fiskaly PUK directory must be owned by the service user with mode 0700")
            return descriptor
        except OSError:
            raise FiskalyError("Fiskaly PUK directory is unavailable") from None

    @staticmethod
    def _load(directory: int, name: str) -> SecretStr | None:
        try:
            descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory)
        except FileNotFoundError:
            return None
        try:
            with os.fdopen(descriptor, "rb") as stream:
                info = os.fstat(stream.fileno())
                if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) & 0o077:
                    raise FiskalyError("Fiskaly PUK file must be private and owned by the service user")
                raw = stream.read(4097)
            if not 10 <= len(raw) <= 4096:
                raise FiskalyError("Fiskaly stored PUK is invalid")
            return SecretStr(raw.decode("utf-8"))
        except UnicodeError:
            raise FiskalyError("Fiskaly stored PUK is invalid") from None

    def load(self, tss_id: UUID) -> SecretStr | None:
        directory = self._open_directory()
        try:
            return self._load(directory, f"{tss_id}.puk")
        except OSError:
            raise FiskalyError("Fiskaly PUK file cannot be read") from None
        finally:
            os.close(directory)

    def save(self, tss_id: UUID, puk: str):
        if not isinstance(puk, str) or not 10 <= len(puk.encode()) <= 4096:
            raise FiskalyError("Fiskaly returned an invalid admin PUK")
        directory = self._open_directory()
        temporary = f".{tss_id}.{uuid4()}.tmp"
        name = f"{tss_id}.puk"
        try:
            descriptor = os.open(
                temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory
            )
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(puk.encode())
                stream.flush()
                os.fsync(stream.fileno())
            try:
                os.link(temporary, name, src_dir_fd=directory, dst_dir_fd=directory, follow_symlinks=False)
            except FileExistsError:
                existing = self._load(directory, name)
                if existing is None or existing.get_secret_value() != puk:
                    raise FiskalyError("Fiskaly returned a different PUK for the persisted TSS") from None
            os.unlink(temporary, dir_fd=directory)
            os.fsync(directory)
        except OSError:
            raise FiskalyError("Fiskaly PUK could not be stored durably") from None
        finally:
            try:
                os.unlink(temporary, dir_fd=directory)
            except FileNotFoundError:
                pass
            os.close(directory)
