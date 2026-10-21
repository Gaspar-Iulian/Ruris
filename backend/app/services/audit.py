from app.extensions import db
from app.models import AuditEvent, Role


USER_FIELDS = {"name": str, "email": str, "role": str, "is_active": bool}
USER_ACTIONS = {"CREATE", "UPDATE", "ROLE_CHANGE", "PASSWORD_CHANGE", "ACTIVATE", "DEACTIVATE", "LOGIN", "LOGOUT"}
ENTITY_FIELDS = {"users": USER_FIELDS, "authentication": {"email": str, "remote_address": str}}
ENTITY_ACTIONS = {"users": USER_ACTIONS, "authentication": {"LOGIN_FAILED"}}
ENTITY_FIELDS["suppliers"] = {
    "name": str, "tax_country": str, "tax_id": str, "email": (str, type(None)), "is_active": bool,
}
ENTITY_ACTIONS["suppliers"] = {"CREATE", "UPDATE", "ACTIVATE", "DEACTIVATE"}
ENTITY_FIELDS["products"] = {"sku": str, "name": str, "unit": str, "is_active": bool}
ENTITY_ACTIONS["products"] = {"CREATE", "UPDATE", "ACTIVATE", "DEACTIVATE"}
ENTITY_FIELDS["purchase_orders"] = {
    "number": str, "supplier_id": int, "currency": str, "status": str,
    "owner_id": int, "created_by_id": int, "version": int,
    "confirmed_at": (str, type(None)),
}
ENTITY_FIELDS["purchase_order_items"] = {
    "purchase_order_id": int, "line_number": int, "product_id": int, "description": str,
    "unit": str, "quantity": str, "unit_price": str, "vat_rate": str, "expected_date": str,
}
ENTITY_ACTIONS["purchase_orders"] = {"CREATE", "UPDATE", "CONFIRM"}
ENTITY_ACTIONS["purchase_order_items"] = {"CREATE", "UPDATE", "DELETE"}
ENTITY_FIELDS["receipts"] = {
    "number": str, "supplier_id": int, "delivery_reference": str, "received_at": str,
    "status": str, "created_by_id": int, "confirmed_by_id": (int, type(None)),
    "confirmed_at": (str, type(None)), "version": int,
}
ENTITY_FIELDS["receipt_items"] = {
    "receipt_id": int, "line_number": int, "product_id": (int, type(None)), "purchase_order_item_id": (int, type(None)),
    "pending_order_item_id": (int, type(None)), "origin_item_id": (int, type(None)), "resolved_quantity": str,
    "description": str, "unit": str, "received_quantity": str, "accepted_quantity": str,
    "rejected_quantity": str, "pending_quantity": str,
}
ENTITY_ACTIONS["receipts"] = {"CREATE", "UPDATE", "CONFIRM"}
ENTITY_ACTIONS["receipt_items"] = {"CREATE", "UPDATE", "CLARIFY", "ACCEPT", "REJECT"}
ENTITY_FIELDS["stock_movements"] = {
    "product_id": int, "receipt_item_id": int, "kind": str, "quantity_delta": str,
    "reason": str, "created_by_id": int, "operation_key": str,
}
ENTITY_ACTIONS["stock_movements"] = {"CREATE"}
ENTITY_FIELDS["email_outbox"] = {
    "kind": str, "transport": str, "as_of": str, "recipient_user_id": int,
    "status": str, "attempt_count": int, "last_error": (str, type(None)),
    "next_attempt_at": (str, type(None)),
}
ENTITY_ACTIONS["email_outbox"] = {"ENQUEUE", "START", "SENT", "FAILED", "UNKNOWN", "SKIP"}
ENTITY_FIELDS["invoices"] = {
    "supplier_id": int, "series": str, "number": str, "invoice_date": str, "due_date": str,
    "currency": str, "net_amount": str, "vat_amount": str, "total_amount": str,
    "status": str, "created_by_id": int, "version": int,
}
ENTITY_FIELDS["invoice_items"] = {
    "purchase_order_item_id": (int, type(None)),
    "invoice_id": int, "line_number": int, "product_id": int, "description": str, "unit": str,
    "quantity": str, "unit_price": str, "vat_rate": str,
    "net_amount": str, "vat_amount": str, "total_amount": str,
}
ENTITY_ACTIONS["invoices"] = {"CREATE", "UPDATE", "VERIFY", "APPROVE", "PAY"}
ENTITY_ACTIONS["invoice_items"] = {"CREATE", "UPDATE", "DELETE"}
ENTITY_FIELDS["invoice_allocations"] = {
    "invoice_item_id": int, "receipt_item_id": int, "quantity": str, "status": str,
    "released_at": (str, type(None)),
}
ENTITY_ACTIONS["invoice_allocations"] = {"CREATE", "RELEASE"}
ENTITY_FIELDS["invoice_issues"] = {
    "invoice_id": int, "invoice_item_id": (int, type(None)), "code": str, "details": str,
    "responsible_role": str, "opened_at": str, "resolved_at": (str, type(None)), "resolution": (str, type(None)),
}
ENTITY_ACTIONS["invoice_issues"] = {"OPEN", "UPDATE", "RESOLVE", "SUPERSEDE"}
ENTITY_FIELDS["invoices"].update({
    "declared_totals": (dict, type(None)), "totals_difference": (dict, type(None)),
    "approved_by_id": (int, type(None)), "approved_at": (str, type(None)),
    "paid_by_id": (int, type(None)), "paid_at": (str, type(None)), "payment_reference": (str, type(None)),
    "exchange_rate_id": (int, type(None)), "exchange_rate_source": (str, type(None)),
    "exchange_rate_date": (str, type(None)), "exchange_rate_value": (str, type(None)), "total_ron": (str, type(None)),
})
ENTITY_FIELDS["exchange_rates"] = {"currency": str, "rate_date": str, "rate": str,
                                    "source": str, "source_url": str, "content_sha256": str}
ENTITY_ACTIONS["exchange_rates"] = {"FETCH"}
ENTITY_FIELDS["attachments"] = {
    "purchase_order_id": (int, type(None)), "receipt_id": (int, type(None)), "invoice_id": (int, type(None)),
    "original_name": str, "media_type": str, "size_bytes": int, "content_sha256": str,
    "upload_reason": str, "uploaded_by_id": int, "created_at": str, "status": str,
    "withdrawn_by_id": (int, type(None)), "withdrawn_at": (str, type(None)), "withdrawal_reason": (str, type(None)),
}
ENTITY_ACTIONS["attachments"] = {"UPLOAD", "DOWNLOAD", "WITHDRAW"}


def user_snapshot(user):
    return {
        "name": user.name,
        "email": user.email,
        "role": Role(user.role).value,
        "is_active": user.is_active,
    }


def validate_snapshot(data, fields=USER_FIELDS):
    if data is None:
        return None
    if not isinstance(data, dict) or data.keys() - fields.keys():
        raise ValueError("Auditul contine campuri nepermise.")
    result = {}
    for key, value in data.items():
        allowed_types = fields[key] if isinstance(fields[key], tuple) else (fields[key],)
        if type(value) not in allowed_types:
            raise ValueError("Valoarea unui camp de audit nu este valida.")
        if key == "role":
            value = Role(value).value
        if key in {"declared_totals", "totals_difference"} and value is not None:
            amount_fields = {"net_amount": str, "vat_amount": str, "total_amount": str}
            if value.keys() != amount_fields.keys():
                raise ValueError("Totalurile de audit necesita toate cele trei sume.")
            value = validate_snapshot(value, amount_fields)
        result[key] = value
    return result


def record_audit(*, action, entity_type, entity_id, actor_user_id=None,
                 actor_process=None, before=None, after=None, reason=None):
    if action not in ENTITY_ACTIONS.get(entity_type, set()):
        raise ValueError("Operatia de audit nu este configurata.")
    if type(entity_id) is not int or entity_id <= 0:
        raise ValueError("Documentul de audit trebuie sa aiba un identificator valid.")
    if (actor_user_id is None) == (actor_process is None):
        raise ValueError("Auditul necesita exact un autor: utilizator sau proces.")
    if actor_user_id is not None and (type(actor_user_id) is not int or actor_user_id <= 0):
        raise ValueError("Utilizatorul autor nu este valid.")
    if actor_process is not None:
        if not isinstance(actor_process, str) or not 1 <= len(actor_process.strip()) <= 80:
            raise ValueError("Procesul autor nu este valid.")
        actor_process = actor_process.strip()
    if reason is not None:
        if not isinstance(reason, str) or not reason.strip() or len(reason) > 1000:
            raise ValueError("Motivul trebuie sa aiba intre 1 si 1000 de caractere.")
        reason = reason.strip()

    audit_event = AuditEvent(
        actor_user_id=actor_user_id,
        actor_process=actor_process,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        before_data=validate_snapshot(before, ENTITY_FIELDS[entity_type]),
        after_data=validate_snapshot(after, ENTITY_FIELDS[entity_type]),
        reason=reason,
    )
    db.session.add(audit_event)
    return audit_event
