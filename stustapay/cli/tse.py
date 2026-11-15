import asyncio
from pathlib import Path
from typing import Annotated, Optional
from uuid import UUID, uuid4

import typer

from stustapay.tse.fiskaly.archive import export_archive
from stustapay.tse.fiskaly.client import FiskalyClient, FiskalyError
from stustapay.tse.fiskaly.config import FiskalyConfig
from stustapay.tse.fiskaly.signing import FiskalySigner, FiskalySigningRequest
from stustapay.tse.handler import TSESignatureRequest
from stustapay.tse.kassenbeleg_v1 import Kassenbeleg_V1
from stustapay.tse.signature_processor import SignatureProcessor
from stustapay.tse.simulator import Simulator
from stustapay.tse.tse_switchover import TseSwitchover

tse_cli = typer.Typer()


@tse_cli.command()
def signature_processor(ctx: typer.Context):
    processor = SignatureProcessor(config=ctx.obj.config)
    asyncio.run(processor.run())


@tse_cli.command()
def simulator(
    host: Annotated[str, typer.Option(help="local bind address")] = "localhost",
    port: Annotated[int, typer.Option("--port", "-p", help="port for websocket to listen, default 10001")] = 10001,
    delay: Annotated[
        float, typer.Option("--delay", "-d", help="artificial delay for signature to mimic real TSE, default 0.25s")
    ] = 0.25,
    fast: Annotated[bool, typer.Option("--fast", "-f", help="no artificial delay for signature")] = False,
    even_more_realistic: Annotated[
        bool, typer.Option("--even_more_realistic", "-r", help="might be a bit to realistic, be careful")
    ] = False,
    secret_key: Annotated[
        Optional[str], typer.Option("--secret_key", "-s", help="ECDSA BRAINPOOLP384r1 sha384 in hex")
    ] = None,
    gen_key: Annotated[bool, typer.Option("--gen_key", "-g", help="generate new secret key")] = False,
    broken: Annotated[bool, typer.Option("--broken", "-b", help="simulator with error")] = False,
):
    sim = Simulator(
        host,
        port,
        delay,
        fast,
        even_more_realistic,
        secret_key,
        gen_key,
        broken,
    )
    asyncio.run(sim.run())


@tse_cli.command()
def tse_switchover(
    ctx: typer.Context,
    show: Annotated[bool, typer.Option("--show", "-s", help="only show status")] = False,
    nc: Annotated[bool, typer.Option("--nc", "-n", help="curses interface")] = False,
    disable: Annotated[bool, typer.Option(help="disable a failed TSE")] = False,
    tse: Annotated[Optional[str], typer.Option(help="TSE name to disable")] = None,
):
    switch = TseSwitchover(config=ctx.obj.config, show=show, nc=nc, disable=disable, tse=tse)
    asyncio.run(switch.run())


@tse_cli.command()
def fiskaly_export(
    ctx: typer.Context,
    tse_id: Annotated[int, typer.Option(help="Local Fiskaly TSE ID")],
    start: Annotated[int, typer.Option(help="Inclusive start as Unix seconds")],
    end: Annotated[int, typer.Option(help="Inclusive end as Unix seconds")],
    output: Annotated[Path, typer.Option(help="New TAR archive path")],
):
    """Archive a SIGN DE export; repeat the same command while it is pending.

    Exports can interfere with signing; run when the TSE is not in use.
    """
    typer.echo(asyncio.run(export_archive(ctx.obj.config, tse_id, start, end, output)))


async def run_fiskaly_smoke(
    profile: FiskalyConfig, till_serial: str, transaction_id: UUID, *, recover: bool, abort: bool = False
):
    if profile.environment != "TEST" or profile.tss_id is None or profile.organization_id is None:
        raise FiskalyError("The smoke test requires a TEST profile with an explicit organization and TSS ID")
    client_id = profile.clients.get(till_serial)
    if client_id is None:
        raise FiskalyError("The smoke test requires a configured client for this register")
    receipt = Kassenbeleg_V1()
    receipt.add_line_item(1, "ust")
    receipt.add_zahlung(1, "Unbar")
    request = FiskalySigningRequest(
        transaction_id,
        client_id,
        TSESignatureRequest(0, till_serial, receipt.get_process_type(), receipt.get_process_data()),
    )
    async with FiskalyClient(profile) as client:
        signer = FiskalySigner(client)
        master = await signer.initialize()
        await signer.verify_client(client_id, till_serial)
        if not recover:
            await signer.begin_sale(transaction_id, client_id, till_serial)
        if abort:
            signed = await signer.abort_sale(transaction_id, client_id, till_serial)
            recovered = await signer.abort_sale(transaction_id, client_id, till_serial)
        else:
            signed = await signer.sign(request, checkout=True)
            recovered = await signer.sign(request, checkout=True)
        if recovered != signed:
            raise FiskalyError("The retrieved result differs from the original signature")
    return master, recovered


@tse_cli.command()
def fiskaly_smoke(
    ctx: typer.Context,
    profile: Annotated[str, typer.Option(help="Name of a configured SIGN DE TEST profile")],
    till_serial: Annotated[str, typer.Option(help="Configured TEST register serial number")],
    recover: Annotated[
        Optional[UUID], typer.Option(help="Recover this TEST transaction without creating a new one")
    ] = None,
    abort: Annotated[bool, typer.Option(help="Cancel the synthetic checkout instead of finishing it")] = False,
):
    """Sign a synthetic receipt and verify it can be retrieved from SIGN DE TEST."""
    selected = ctx.obj.config.fiskaly.profiles.get(profile)
    if selected is None:
        typer.echo("Configured fiskaly TEST profile not found", err=True)
        raise typer.Exit(1)
    transaction_id = recover or uuid4()
    typer.echo(f"SIGN DE TEST transaction ID {transaction_id}")
    try:
        master, signature = asyncio.run(
            run_fiskaly_smoke(selected, till_serial, transaction_id, recover=recover is not None, abort=abort)
        )
    except (FiskalyError, ValueError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from None
    typer.echo(
        f"TEST {'CANCELLED' if abort else 'FINISHED'}, TSE {master.tse_serial}, "
        f"register {till_serial}, transaction {signature.tse_transaction}, "
        f"signature counter {signature.tse_signaturenr}, {signature.tse_start} to {signature.tse_end}."
    )
