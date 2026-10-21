from sqlalchemy import func, select

from app.extensions import db
from app.models import InvoiceIssue
from app.services.audit import record_audit


def issue_data(issue):
    return {"id": issue.id, "invoice_id": issue.invoice_id, "invoice_item_id": issue.invoice_item_id,
            "code": issue.code, "details": issue.details, "responsible_role": issue.responsible_role,
            "opened_at": issue.opened_at.isoformat(),
            "resolved_at": issue.resolved_at.isoformat() if issue.resolved_at else None, "resolution": issue.resolution}


def audit_issue(issue, *, actor_user_id, action, before=None, reason=None):
    record_audit(action=action, entity_type="invoice_issues", entity_id=issue.id, actor_user_id=actor_user_id,
                 before=before, after={key: value for key, value in issue_data(issue).items() if key != "id"}, reason=reason)


def invalidate_verification(invoice, *, actor_user_id, reason):
    for key in ("exchange_rate_id", "exchange_rate_value", "exchange_rate_date", "exchange_rate_source", "total_ron"):
        setattr(invoice, key, None)
    if invoice.status == "DRAFT":
        return
    now = db.session.scalar(select(func.clock_timestamp()))
    issues = db.session.scalars(select(InvoiceIssue).where(InvoiceIssue.invoice_id == invoice.id, InvoiceIssue.resolved_at.is_(None))).all()
    for issue in issues:
        before = {key: value for key, value in issue_data(issue).items() if key != "id"}
        issue.resolved_at, issue.resolution = now, "SUPERSEDED"
        audit_issue(issue, actor_user_id=actor_user_id, action="SUPERSEDE", before=before, reason=reason)
    invoice.status = "DRAFT"
