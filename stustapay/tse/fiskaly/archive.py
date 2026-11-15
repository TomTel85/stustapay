"""Operator-triggered SIGN DE exports, with a durable retry identity."""

import contextlib
import json
import os
import tempfile
from pathlib import Path
from uuid import UUID, uuid4

from stustapay.core.config import Config
from stustapay.core.database import get_database

from .client import FiskalyClient, FiskalyError, FiskalyHTTPError
from .config import FiskalyConfig
from .onboarding import resolve_managed_config


def _sync_directory(directory: Path) -> None:
    fd = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


@contextlib.contextmanager
def new_archive_file(path: Path):
    """Publish a complete file without replacing an existing one."""
    fd, name = tempfile.mkstemp(dir=path.parent, prefix=".fiskaly-")
    try:
        with os.fdopen(fd, "wb") as file:
            yield file
            file.flush()
            os.fsync(file.fileno())
        os.link(name, path)
        _sync_directory(path.parent)
    finally:
        os.unlink(name)


async def export_archive(config: Config, tse_id: int, start: int, end: int, output: Path) -> str:
    if start < 0 or end < start:
        raise FiskalyError("Export dates must be non-negative Unix timestamps in ascending order")
    if output.exists():
        raise FiskalyError("Archive already exists; choose a new output path")
    profile: FiskalyConfig | None
    db_pool = await get_database(config.database).create_pool()
    try:
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(
                "select type, fiskaly_job_id, fiskaly_profile, fiskaly_tss_id from tse where id=$1", tse_id
            )
            if row is None or row["type"] != "fiskaly":
                raise FiskalyError("TSE is missing or is not a Fiskaly TSE")
            if row["fiskaly_job_id"] is not None:
                profile = await resolve_managed_config(conn, config, row["fiskaly_job_id"], archive=True)
            else:
                profile = config.fiskaly.profiles.get(row["fiskaly_profile"] or "")
                if profile is not None and profile.tss_id is None:
                    profile = profile.model_copy(update={"tss_id": row["fiskaly_tss_id"]})
            if profile is None or profile.tss_id is None or profile.tss_id != row["fiskaly_tss_id"]:
                raise FiskalyError("TSE credentials or TSS ID do not match the local record")
    finally:
        await db_pool.close()

    sidecar = output.with_name(output.name + ".json")
    identity = {
        "tse_id": tse_id,
        "tss_id": str(profile.tss_id),
        "organization_id": str(profile.organization_id) if profile.organization_id else None,
        "environment": profile.environment,
        "start_date": start,
        "end_date": end,
    }
    try:
        with new_archive_file(sidecar) as file:
            file.write(json.dumps({**identity, "export_id": str(uuid4())}).encode())
    except FileExistsError:
        pass
    try:
        saved = json.loads(sidecar.read_text())
        export_id = UUID(saved.pop("export_id"))
        if export_id.version != 4 or saved != identity:
            raise ValueError
    except (ValueError, AttributeError, KeyError, TypeError):
        raise FiskalyError("Export identity file is invalid or does not match the requested export") from None

    path = f"tss/{profile.tss_id}/export/{export_id}"
    async with FiskalyClient(profile) as client:
        try:
            status = await client.request("GET", path)
        except FiskalyHTTPError as exc:
            if exc.status != 404:
                raise
            status = await client.request("PUT", f"{path}?start_date={start}&end_date={end}", payload={})
        if (
            status.get("_id") != str(export_id)
            or status.get("tss_id") != str(profile.tss_id)
            or status.get("_env") != profile.environment
        ):
            raise FiskalyError("Fiskaly returned an export for a different identity")
        state = status.get("state")
        if state in {"PENDING", "WORKING"}:
            return f"Export {export_id} is {state}; run the same command again to download it"
        if state != "COMPLETED":
            raise FiskalyError("Fiskaly export did not complete")
        with new_archive_file(output) as file:
            await client.download_export(str(profile.tss_id), str(export_id), file)
            if file.tell() == 0:
                raise FiskalyError("Fiskaly returned an empty export")
    return f"Archived export {export_id} to {output}"
