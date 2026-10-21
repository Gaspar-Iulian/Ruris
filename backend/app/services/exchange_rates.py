from datetime import date
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import os
import re
import ssl
from urllib.error import URLError
from urllib.request import HTTPRedirectHandler, HTTPSHandler, Request, build_opener
from xml.etree import ElementTree

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.extensions import db
from app.models import ExchangeRate
from app.services.audit import record_audit


MAX_XML_BYTES = 2_000_000


class ExchangeRateUnavailable(ValueError):
    pass


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, newurl):
        raise ExchangeRateUnavailable("Sursa BNR a redirectionat cererea.")


def download_year(year):
    if type(year) is not int or not 2005 <= year <= 9999:
        raise ExchangeRateUnavailable("Anul nu este disponibil in arhiva acceptata.")
    url = f"https://curs.bnr.ro/files/xml/years/nbrfxrates{year}.xml"
    context = ssl.create_default_context()
    if os.name == "nt":
        import truststore
        context = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    opener = build_opener(NoRedirects(), HTTPSHandler(context=context))
    try:
        request = Request(url, headers={"User-Agent": "Ruris/1.0", "Accept": "application/xml, text/xml"})
        with opener.open(request, timeout=8) as response:
            if response.status != 200:
                raise ExchangeRateUnavailable("Sursa BNR nu este disponibila.")
            data = response.read(MAX_XML_BYTES + 1)
        if len(data) > MAX_XML_BYTES:
            raise ExchangeRateUnavailable("Fisierul BNR depaseste limita acceptata.")
        return url, data
    except (OSError, URLError) as error:
        raise ExchangeRateUnavailable("Cursul nu a putut fi preluat prin HTTPS de la BNR.") from error


def parse_eur_rate(data, requested_date):
    try:
        if not isinstance(data, bytes) or len(data) > MAX_XML_BYTES:
            raise ValueError()
        xml = data.decode("utf-8-sig")
        if "\x00" in xml or "<!DOCTYPE" in xml.upper() or "<!ENTITY" in xml.upper():
            raise ValueError()
        root = ElementTree.fromstring(xml)
        namespaces = ("http://www.bnr.ro/xsd", "https://www.bnr.ro/xsd")
        namespace = next((ns for ns in namespaces if root.tag == f"{{{ns}}}DataSet"), None)
        if namespace is None:
            raise ValueError()
        ns = {"b": namespace}
        if root.findtext("b:Header/b:Publisher", namespaces=ns) != "National Bank of Romania" or root.findtext("b:Body/b:OrigCurrency", namespaces=ns) != "RON":
            raise ValueError()
        cubes = [cube for cube in root.findall("b:Body/b:Cube", ns) if cube.get("date") == requested_date.isoformat()]
        if not cubes:
            raise ExchangeRateUnavailable("BNR nu are curs publicat pentru data exacta a facturii.")
        if len(cubes) != 1:
            raise ValueError()
        rates = [item for item in cubes[0].findall("b:Rate", ns) if item.get("currency") == "EUR"]
        if len(rates) != 1 or rates[0].get("multiplier", "1") != "1":
            raise ValueError()
        value = (rates[0].text or "").strip()
        if not re.fullmatch(r"[0-9]{1,12}(?:\.[0-9]{1,6})?", value):
            raise ValueError()
        rate = Decimal(value)
        if rate <= 0:
            raise ValueError()
        return rate.quantize(Decimal("0.000001"))
    except (ElementTree.ParseError, UnicodeError, ValueError, InvalidOperation) as error:
        if isinstance(error, ExchangeRateUnavailable):
            raise
        raise ExchangeRateUnavailable("Raspunsul BNR nu contine un curs EUR valid.") from error


def get_eur_rate(requested_date):
    if type(requested_date) is not date or requested_date.year < 2005:
        raise ExchangeRateUnavailable("Data nu este disponibila in arhiva acceptata.")
    existing = db.session.scalar(select(ExchangeRate).where(ExchangeRate.source == "BNR", ExchangeRate.currency == "EUR", ExchangeRate.rate_date == requested_date))
    if existing is not None:
        return existing
    url, data = download_year(requested_date.year)
    rate = parse_eur_rate(data, requested_date)
    new_id = db.session.scalar(insert(ExchangeRate).values(currency="EUR", rate_date=requested_date, rate=rate,
        source="BNR", source_url=url, content_sha256=sha256(data).hexdigest())
        .on_conflict_do_nothing(constraint="uq_exchange_rates_source_date").returning(ExchangeRate.id))
    result = db.session.scalar(select(ExchangeRate).where(ExchangeRate.source == "BNR", ExchangeRate.currency == "EUR", ExchangeRate.rate_date == requested_date))
    if result.rate != rate:
        raise ExchangeRateUnavailable("Sursa difera de cursul istoric deja pastrat; este necesara clarificare.")
    if new_id is not None:
        record_audit(action="FETCH", entity_type="exchange_rates", entity_id=new_id, actor_process="bnr_import",
                     after={"currency": "EUR", "rate_date": requested_date.isoformat(), "rate": format(rate, ".6f"),
                            "source": "BNR", "source_url": url, "content_sha256": result.content_sha256})
    return result
