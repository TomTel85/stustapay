from datetime import datetime
from decimal import Decimal

import asyncpg
from pydantic import BaseModel
from sftkit.database import Connection
from sftkit.error import InvalidArgument, NotFound

from stustapay.bon.pdflatex import PdfRenderResult, pdflatex, render_template
from stustapay.bon.report_time import REPORT_TIMEZONE
from stustapay.core.currency import get_currency_symbol
from stustapay.core.schema.tree import Node

ZERO = Decimal("0")


class PayoutReportPosition(BaseModel):
    reference: int
    amount: Decimal


class PayoutReportRun(BaseModel):
    id: int
    created_at: datetime
    set_done_at: datetime
    payouts: list[PayoutReportPosition]
    donations: list[PayoutReportPosition]
    total_payout_amount: Decimal
    total_donation_amount: Decimal
    total_amount: Decimal


class PayoutReportContext(BaseModel):
    event_name: str
    generated_at: datetime
    currency_symbol: str
    is_complete_history: bool
    runs: list[PayoutReportRun]
    n_runs: int
    n_payouts: int
    n_donations: int
    total_payout_amount: Decimal
    total_donation_amount: Decimal
    total_amount: Decimal


async def build_payout_report_context(
    conn: Connection, node: Node, payout_run_id: int | None = None
) -> PayoutReportContext:
    event_node_id = node.event_node_id
    if event_node_id is None or node.event is None:
        raise InvalidArgument("Payout reports can only be generated for events")

    params: tuple[int, ...]
    where = "pr.node_id = $1 and pr.done and not pr.revoked"
    params = (event_node_id,)
    if payout_run_id is not None:
        existing = await conn.fetchrow(
            "select done, revoked from payout_run where id = $1 and node_id = $2",
            payout_run_id,
            event_node_id,
        )
        if existing is None:
            raise NotFound(element_type="payout_run", element_id=payout_run_id)
        if not existing["done"] or existing["revoked"]:
            raise InvalidArgument("Payout reports are only available for completed payout runs")
        where += " and pr.id = $2"
        params = (event_node_id, payout_run_id)

    run_rows = await conn.fetch(
        f"select pr.id, pr.created_at, pr.set_done_at from payout_run pr where {where} "
        "order by pr.set_done_at asc, pr.id asc",
        *params,
    )
    run_ids = [row["id"] for row in run_rows]
    positions_by_run: dict[int, list[asyncpg.Record]] = {run_id: [] for run_id in run_ids}
    if run_ids:
        position_rows = await conn.fetch(
            "select id, payout_run_id, amount, donation from payout "
            "where payout_run_id = any($1::bigint[]) order by payout_run_id, id",
            run_ids,
        )
        for position in position_rows:
            positions_by_run[position["payout_run_id"]].append(position)

    runs: list[PayoutReportRun] = []
    for row in run_rows:
        payouts = [
            PayoutReportPosition(reference=position["id"], amount=round(position["amount"], 2))
            for position in positions_by_run[row["id"]]
            if round(position["amount"], 2) > 0
        ]
        donations = [
            PayoutReportPosition(reference=position["id"], amount=round(position["donation"], 2))
            for position in positions_by_run[row["id"]]
            if round(position["donation"], 2) > 0
        ]
        payout_total = sum((position.amount for position in payouts), ZERO)
        donation_total = sum((position.amount for position in donations), ZERO)
        runs.append(
            PayoutReportRun(
                id=row["id"],
                created_at=row["created_at"].astimezone(REPORT_TIMEZONE),
                set_done_at=row["set_done_at"].astimezone(REPORT_TIMEZONE),
                payouts=payouts,
                donations=donations,
                total_payout_amount=payout_total,
                total_donation_amount=donation_total,
                total_amount=payout_total + donation_total,
            )
        )

    total_payout_amount = sum((run.total_payout_amount for run in runs), ZERO)
    total_donation_amount = sum((run.total_donation_amount for run in runs), ZERO)
    return PayoutReportContext(
        event_name=node.name,
        generated_at=datetime.now(tz=REPORT_TIMEZONE),
        currency_symbol=get_currency_symbol(node.event.currency_identifier),
        is_complete_history=payout_run_id is None,
        runs=runs,
        n_runs=len(runs),
        n_payouts=sum(len(run.payouts) for run in runs),
        n_donations=sum(len(run.donations) for run in runs),
        total_payout_amount=total_payout_amount,
        total_donation_amount=total_donation_amount,
        total_amount=total_payout_amount + total_donation_amount,
    )


async def generate_payout_report(conn: Connection, node: Node, payout_run_id: int | None = None) -> PdfRenderResult:
    context = await build_payout_report_context(conn=conn, node=node, payout_run_id=payout_run_id)
    rendered = await render_template("payout_report.tex", context, context.currency_symbol)
    return await pdflatex(file_content=rendered)
