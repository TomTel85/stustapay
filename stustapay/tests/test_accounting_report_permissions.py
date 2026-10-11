from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from sftkit.error import AccessDenied

from stustapay.bon.accounting_report import AccountingReportQuery, render_accounting_report
from stustapay.bon.pdflatex import PdfRenderResult, RenderedPdf
from stustapay.core.schema.tree import NewNode
from stustapay.core.schema.user import NewUser, NewUserRole, Privilege, RoleToNode


async def test_subnode_stats_report_omits_event_wide_ledger(
    db_connection, tree_service, user_service, global_admin_token, global_admin_user, event_node, monkeypatch
):
    subnode = await tree_service.create_node(
        token=global_admin_token,
        node_id=event_node.id,
        new_node=NewNode(name="Review restricted vendor", description=""),
    )
    role = await user_service.create_user_role(
        token=global_admin_token,
        node_id=event_node.id,
        new_role=NewUserRole(name="Review vendor stats", privileges=[Privilege.view_node_stats]),
    )
    user = await user_service.create_user_no_auth(
        node_id=event_node.id,
        new_user=NewUser(login="review-" + uuid4().hex, description="", display_name="Review vendor"),
        roles=[RoleToNode(node_id=subnode.id, role_id=role.id)],
        password="review-password",
    )
    token = (await user_service.login_user(username=user.login, password="review-password")).success.token
    account = await db_connection.fetchval(
        "insert into account(node_id,type) values($1,'private') returning id", event_node.id
    )
    source = await db_connection.fetchval(
        "select id from account where node_id=$1 and type='cash_topup_source'", event_node.id
    )
    await db_connection.fetchval(
        "select book_transaction(null,null,$1,$2,123.45,0,$3,$4)",
        source,
        account,
        datetime.now(timezone.utc),
        global_admin_user[0].id,
    )
    contexts = []

    async def capture_report(context):
        contexts.append(context)
        return PdfRenderResult(success=True, bon=RenderedPdf(mime_type="application/pdf", content=b"probe"))

    monkeypatch.setattr("stustapay.bon.accounting_report.render_accounting_report", capture_report)
    with pytest.raises(AccessDenied):
        await tree_service.generate_accounting_report(token=token, node_id=event_node.id, query=AccountingReportQuery())
    await tree_service.generate_accounting_report(token=token, node_id=subnode.id, query=AccountingReportQuery())
    assert contexts[0].total_revenue == 0
    assert contexts[0].monthly_rows == []
    assert contexts[0].includes_event_monthly_accounting is False
    await tree_service.generate_accounting_report(
        token=global_admin_token, node_id=event_node.id, query=AccountingReportQuery()
    )
    assert contexts[1].monthly_rows[-1].remaining_credit >= Decimal("123.45")
    assert contexts[1].includes_event_monthly_accounting is True

    rendered = []

    async def capture_pdf(file_content):
        rendered.append(file_content)
        return PdfRenderResult(success=True)

    monkeypatch.setattr("stustapay.bon.accounting_report.pdflatex", capture_pdf)
    await render_accounting_report(contexts[0])
    assert "Monatliche Pfand-" not in rendered[0]
    await render_accounting_report(contexts[1])
    assert "Monatliche Pfand-" in rendered[1]
