from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch
from urllib.error import URLError

import pytest
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import DBAPIError

from app.models import AuditEvent, ExchangeRate, Invoice, InvoiceIssue
from app.services.exchange_rates import ExchangeRateUnavailable, MAX_XML_BYTES, download_year, get_eur_rate, parse_eur_rate
from test_invoice_allocations import setup
from test_invoice_verification import cover, verify


def xml(day="2026-10-20", value="5.0000", namespace="https://www.bnr.ro/xsd", *, rate_extra=""):
    return (f'<DataSet xmlns="{namespace}"><Header><Publisher>National Bank of Romania</Publisher></Header>'
            f'<Body><OrigCurrency>RON</OrigCurrency><Cube date="{day}"><Rate currency="EUR" {rate_extra}>{value}</Rate>'
            '</Cube></Body></DataSet>').encode()


def test_unpublished_invoice_date_blocks_without_using_cached_other_day(setup, session, monkeypatch):
    cover(setup, session, currency="EUR")
    monkeypatch.setattr("app.services.exchange_rates.download_year", lambda year: ("https://curs.bnr.ro/test", xml()))
    assert get_eur_rate(date(2026, 10, 20)).rate == Decimal("5.000000")
    invoice = session.get(Invoice, setup["invoice"]["id"])
    invoice.invoice_date = date(2026, 10, 17)
    session.commit()
    result = verify(setup, 2).json
    assert result["invoice"]["status"] == "BLOCKED"
    assert result["invoice"]["total_ron"] is None
    assert [issue["code"] for issue in result["issues"]] == ["EXCHANGE_RATE_NOT_PUBLISHED"]
    assert "2026-10-17" in result["issues"][0]["details"]
    assert session.scalar(select(func.count()).select_from(ExchangeRate)) == 1


@pytest.mark.parametrize("namespace", ["http://www.bnr.ro/xsd", "https://www.bnr.ro/xsd"])
def test_parser_supports_historical_and_current_namespace(namespace):
    assert parse_eur_rate(xml(namespace=namespace), date(2026, 10, 20)) == Decimal("5.000000")


@pytest.mark.parametrize("value", ["0", "-1", "NaN", "Infinity", "1e2", "5,1", "1.1234567", "1000000000000", ""])
def test_invalid_rate_rejected(value):
    with pytest.raises(ExchangeRateUnavailable):
        parse_eur_rate(xml(value=value), date(2026, 10, 20))


@pytest.mark.parametrize("data", [b"<html>error</html>", b"<DataSet", b"<!DOCTYPE x><x/>", b"\xff", b"x" * (MAX_XML_BYTES + 1)],
                         ids=["html", "broken-xml", "doctype", "encoding", "oversized"])
def test_invalid_xml_rejected(data):
    with pytest.raises(ExchangeRateUnavailable):
        parse_eur_rate(data, date(2026, 10, 20))


def test_parser_requires_exact_date_and_rejects_duplicates_or_multiplier():
    with pytest.raises(ExchangeRateUnavailable):
        parse_eur_rate(xml(day="2026-10-16"), date(2026, 10, 17))
    with pytest.raises(ExchangeRateUnavailable):
        parse_eur_rate(xml(rate_extra='multiplier="100"'), date(2026, 10, 20))
    duplicated = xml().replace(b'</Cube>', b'<Rate currency="EUR">5</Rate></Cube>')
    with pytest.raises(ExchangeRateUnavailable):
        parse_eur_rate(duplicated, date(2026, 10, 20))


def test_download_uses_fixed_https_url_timeout_and_limit():
    response = MagicMock()
    response.__enter__.return_value = response
    response.status = 200
    response.read.return_value = xml()
    opener = MagicMock()
    opener.open.return_value = response
    with patch("app.services.exchange_rates.build_opener", return_value=opener):
        url, data = download_year(2026)
    assert url == "https://curs.bnr.ro/files/xml/years/nbrfxrates2026.xml"
    request = opener.open.call_args.args[0]
    assert request.full_url == url
    assert opener.open.call_args.kwargs["timeout"] == 8
    response.read.assert_called_once_with(MAX_XML_BYTES + 1)
    assert data == xml()


def test_download_network_failure_is_controlled():
    with patch("app.services.exchange_rates.build_opener") as build:
        build.return_value.open.side_effect = URLError("network failure")
        with pytest.raises(ExchangeRateUnavailable):
            download_year(2026)


def test_cached_rate_is_reused_and_audited_once(session, monkeypatch):
    calls = []

    def download(year):
        calls.append(year)
        return f"https://curs.bnr.ro/files/xml/years/nbrfxrates{year}.xml", xml()

    monkeypatch.setattr("app.services.exchange_rates.download_year", download)
    first = get_eur_rate(date(2026, 10, 20))
    session.commit()
    second = get_eur_rate(date(2026, 10, 20))
    assert first.id == second.id
    assert calls == [2026]
    event = session.scalar(select(AuditEvent).where(AuditEvent.entity_type == "exchange_rates"))
    assert event.actor_process == "bnr_import"
    assert event.after_data["rate"] == "5.000000"
    assert len(first.content_sha256) == 64
    assert session.scalar(select(func.count()).select_from(ExchangeRate)) == 1


def test_eur_verification_saves_snapshot_and_works_offline_afterwards(setup, session, monkeypatch):
    cover(setup, session, currency="EUR")
    monkeypatch.setattr("app.services.exchange_rates.download_year", lambda year: (f"https://curs.bnr.ro/files/xml/years/nbrfxrates{year}.xml", xml()))
    response = verify(setup, 2)
    assert response.status_code == 200
    result = response.json["invoice"]
    assert result["status"] == "VERIFIED"
    assert result["exchange_rate_value"] == "5.000000"
    assert result["exchange_rate_date"] == "2026-10-20"
    assert result["exchange_rate_source"] == "BNR"
    assert result["total_ron"] == "71.40"
    assert result["exchange_rate_id"] is not None
    with patch("app.services.exchange_rates.download_year", side_effect=AssertionError("Nu trebuie accesata reteaua")):
        again = verify(setup, 3)
    assert again.json["invoice"]["total_ron"] == "71.40"


def test_missing_rate_recovers_on_reverification(setup, session, monkeypatch):
    cover(setup, session, currency="EUR")
    with patch("app.services.exchange_rates.download_year", side_effect=ExchangeRateUnavailable("BNR indisponibil")):
        result = verify(setup, 2).json
    assert result["invoice"]["status"] == "BLOCKED"
    assert result["invoice"]["total_ron"] is None
    monkeypatch.setattr("app.services.exchange_rates.download_year", lambda year: ("https://curs.bnr.ro/files/xml/years/nbrfxrates2026.xml", xml()))
    result = verify(setup, 3).json
    assert result["invoice"]["status"] == "VERIFIED"
    assert result["issues"] == []
    assert session.scalar(select(InvoiceIssue)).resolution == "RESOLVED"


def test_ron_uses_one_without_network_and_edit_clears_conversion(setup, session):
    cover(setup, session)
    with patch("app.services.exchange_rates.download_year", side_effect=AssertionError("RON nu necesita retea")):
        result = verify(setup, 2).json["invoice"]
    assert result["exchange_rate_value"] == "1.000000"
    assert result["exchange_rate_source"] == "IDENTITY"
    assert result["total_ron"] == "14.28"
    allocation_id = setup["client"].get(f'/api/invoices/{result["id"]}/allocations').json["allocations"][0]["id"]
    response = setup["client"].post(f'/api/invoices/{result["id"]}/allocations/release',
        json={"version": 3, "reason": "Corectie", "allocation_ids": [allocation_id]}, headers=setup["headers"])
    assert response.status_code == 200
    body = {**setup["data"], "currency": "RON", "invoice_date": "2026-10-19", "version": 4, "reason": "Data corecta",
            "items": [{**setup["data"]["items"][0], "id": result["items"][0]["id"]}]}
    edited = setup["client"].patch(f'/api/invoices/{result["id"]}', json=body, headers=setup["headers"])
    assert edited.status_code == 200
    assert edited.json["invoice"]["exchange_rate_value"] is None
    assert edited.json["invoice"]["total_ron"] is None


def test_database_preserves_historical_rate(session, monkeypatch):
    monkeypatch.setattr("app.services.exchange_rates.download_year", lambda year: ("https://curs.bnr.ro/files/xml/years/nbrfxrates2026.xml", xml()))
    rate = get_eur_rate(date(2026, 10, 20))
    session.commit()
    for statement in (update(ExchangeRate).where(ExchangeRate.id == rate.id).values(rate=6), delete(ExchangeRate).where(ExchangeRate.id == rate.id)):
        with pytest.raises(DBAPIError):
            with session.begin_nested():
                session.execute(statement)


def test_audit_failure_rolls_back_import_and_conversion(setup, session, monkeypatch):
    cover(setup, session, currency="EUR")
    monkeypatch.setattr("app.services.exchange_rates.download_year", lambda year: ("https://curs.bnr.ro/files/xml/years/nbrfxrates2026.xml", xml()))
    with patch("app.services.invoice_verification.record_audit", side_effect=ValueError("Audit indisponibil")):
        assert verify(setup, 2).status_code == 400
    assert session.scalar(select(func.count()).select_from(ExchangeRate)) == 0
    invoice = session.get(Invoice, setup["invoice"]["id"])
    assert invoice.version == 2
    assert invoice.exchange_rate_value is None
