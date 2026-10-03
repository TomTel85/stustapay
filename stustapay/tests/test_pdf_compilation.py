import asyncio
import importlib
import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

pdf_module = importlib.import_module("stustapay.bon.pdflatex")


@pytest.mark.parametrize("cancelled", [False, True])
async def test_compiler_is_reaped_on_timeout_or_cancellation(monkeypatch, cancelled):
    spawn = asyncio.create_subprocess_exec
    started = asyncio.Event()
    processes = []

    async def create_process(*_args, **kwargs):
        process = await spawn(sys.executable, "-c", "import time; time.sleep(30)", **kwargs)
        processes.append(process)
        started.set()
        return process

    monkeypatch.setattr(pdf_module, "_pdf_render_slots", asyncio.Semaphore(1))
    monkeypatch.setattr(pdf_module, "PDF_RENDER_TIMEOUT_SECONDS", 0.05)
    monkeypatch.setattr(pdf_module.asyncio, "create_subprocess_exec", create_process)
    task = asyncio.create_task(pdf_module.pdflatex("document"))
    await started.wait()
    if cancelled:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    else:
        result = await task
        assert not result.success
        assert result.msg == "PDF compilation timed out"
    assert processes[0].returncode is not None


async def test_report_compiler_concurrency_is_bounded(monkeypatch):
    release = asyncio.Event()
    started = asyncio.Event()
    spawn_count = 0

    async def create_process(*_args, **kwargs):
        nonlocal spawn_count
        spawn_count += 1
        Path(kwargs["cwd"], "main.pdf").write_bytes(b"pdf output")
        process = AsyncMock()
        process.returncode = 0

        async def communicate():
            started.set()
            await release.wait()
            return b"", b""

        process.communicate.side_effect = communicate
        return process

    monkeypatch.setattr(pdf_module, "_pdf_render_slots", asyncio.Semaphore(1))
    monkeypatch.setattr(pdf_module.asyncio, "create_subprocess_exec", create_process)
    first = asyncio.create_task(pdf_module.pdflatex("first"))
    await started.wait()
    second = asyncio.create_task(pdf_module.pdflatex("second"))
    await asyncio.sleep(0)
    try:
        assert spawn_count == 1
    finally:
        release.set()
        results = await asyncio.gather(first, second)
    assert spawn_count == 2
    assert all(result.success and result.bon.content == b"pdf output" for result in results)
