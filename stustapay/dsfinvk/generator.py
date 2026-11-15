import contextlib
import logging
import time
from datetime import datetime, timezone
from decimal import Decimal

from dateutil import parser
from sftkit.database import Connection

from stustapay.core.config import Config
from stustapay.core.schema.tree import Node, RestrictedEventSettings
from stustapay.core.service.tree.common import (
    fetch_node,
    fetch_restricted_event_settings_for_node,
)
from stustapay.tse.signature_request import PAYMENT_METHOD_TO_ZAHLUNGSART

from ..core.database import get_database
from .dsfinvk.collection import Collection
from .dsfinvk.models import (
    Bonkopf,
    Bonkopf_USt,
    Bonkopf_Zahlarten,
    Bonpos,
    Bonpos_USt,
    Stamm_Abschluss,
    Stamm_Kassen,
    Stamm_Orte,
    Stamm_TSE,
    Stamm_USt,
    TSE_Transaktionen,
    Z_GV_Typ,
    Z_Waehrungen,
    Z_Zahlart,
)

LOGGER = logging.getLogger(__name__)

TAXNAME_TO_SCHLUESSELNUMMER = {"ust": 1, "eust": 2, "none": 5, "transparent": 1337}
ORDERTYPE_TO_KUNDETYP = {
    "top_up": "Kunde",
    "sale": "Kunde",
    "cancel_sale": "Kunde",
    "pay_out": "Kunde",
    "ticket": "Kunde",
    "money_transfer": "intern",
    "money_transfer_imbalance": "intern",
}


def _split_tse_certificate(certificate: str) -> list[str]:
    if len(certificate) > 5000:
        raise ValueError(f"TSE certificate is too long: {len(certificate)} characters (maximum 5000)")
    return [certificate[start : start + 1000] for start in range(0, len(certificate), 1000)]


class BNU:
    Brutto = Decimal(0)
    Netto = Decimal(0)
    USt = Decimal(0)


class Generator:
    def __init__(
        self,
        config: Config,
        event_node_id: int,
        filename: str,
        xml: str,
        dtd: str,
        simulate: bool,
        *,
        taxpayer_id: int | None = None,
        till_id: int | None = None,
    ):
        self.node_id = event_node_id
        self.taxpayer_id = taxpayer_id
        self.till_id = till_id
        self.config = config
        self.filename = filename
        self.xml = xml  # path to index.xml file
        self.dtd = dtd  # path to *.dtd file
        self.c = Collection()
        self.simulate = simulate
        self.starttime = time.monotonic()
        self.GV_SUMME: dict = dict()  # aufsummierte Geschäftsvorfalltypen
        self.PLZ = ""
        self.Street = ""
        self.City = ""

    async def run(self):
        async with contextlib.AsyncExitStack() as es:
            db = get_database(self.config.database)
            db_pool = await db.create_pool(n_connections=2)
            es.push_async_callback(db_pool.close)
            conn: Connection = await es.enter_async_context(db_pool.acquire())
            node = await fetch_node(conn=conn, node_id=self.node_id)
            if node is None:
                raise ValueError("Unknown DSFinV-K export node")

            rows = await conn.fetch(
                "select distinct t.id as till_id,n.event_node_id,s.id as site_id,s.operator_name,"
                "s.address_line1,s.zip,s.town,s.vat_id "
                "from till t join node n on n.id=t.node_id join ordr o on o.till_id=t.id "
                "join tse_signature sig on sig.id=o.id left join fiskaly_site s on s.id=sig.fiskaly_site_id "
                "where (n.id=$1 or $1=any(n.parent_ids)) "
                "and ($2::bigint is null or t.id=$2) "
                "order by t.id",
                node.id,
                self.till_id,
            )
            if len({row["till_id"] for row in rows}) != len(rows):
                raise ValueError(
                    "A till contains records from multiple fiscal owners; reconcile its history before export"
                )
            taxpayers = {row["site_id"] for row in rows}
            if self.taxpayer_id is None and len(taxpayers) > 1:
                raise ValueError("The export spans multiple fiscal owners; select a taxpayer or till")
            if self.taxpayer_id is not None:
                rows = [row for row in rows if row["site_id"] == self.taxpayer_id]
                if not rows:
                    raise ValueError("No transactions for this taxpayer in the requested scope")
            if self.till_id is not None and not rows:
                raise ValueError("No transactions for this till in the requested scope")

            for row in rows:
                event_node_id = row["event_node_id"]
                if event_node_id is None:
                    raise ValueError(f"Till {row['till_id']} is not assigned to an event")
                event_settings = await fetch_restricted_event_settings_for_node(conn=conn, node_id=event_node_id)
                event_node = await fetch_node(conn=conn, node_id=event_node_id)
                assert event_node is not None
                till_settings = event_settings
                if row["site_id"] is not None:
                    self.Street, self.PLZ, self.City = row["address_line1"], row["zip"], row["town"]
                    till_settings = event_settings.model_copy(
                        update={"bon_issuer": row["operator_name"], "ust_id": row["vat_id"] or ""}
                    )
                else:
                    address = event_settings.bon_address
                    if "\n" in address:
                        self.Street, postal_address = address.split("\n", 1)
                    else:
                        self.Street, postcode, city = address.rsplit(maxsplit=2)
                        postal_address = f"{postcode} {city}"
                    self.PLZ, self.City = postal_address.split(maxsplit=1)
                Z_KASSE_ID: int = row["till_id"]

                # iteriere über Kassenabschlüsse Z_NR dieser Kassen
                for inner_row in await conn.fetch(
                    "select z_nr from ordr where till_id = $1 group by z_nr order by z_nr", Z_KASSE_ID
                ):  # alle Kassenabschlussids
                    Z_NR: int = inner_row["z_nr"]

                    # hole alle order dieser Kasse und Kassenabschluss und nimm den Zeitpunkt der letzten für den Kassenabschluss
                    last_order_time = await conn.fetchval(
                        "select booked_at from ordr where till_id = $1 and z_nr = $2 order by id desc", Z_KASSE_ID, Z_NR
                    )
                    Z_ERSTELLUNG: datetime = last_order_time

                    # sammle Einzelaufzeichnungsmodul
                    await self.einzelaufzeichnungsmodul(
                        conn, Z_NR, Z_ERSTELLUNG, Z_KASSE_ID, event_settings=till_settings
                    )
                    # sammle Stammdatenmodul
                    await self.stammdatenmodul(
                        conn, Z_NR, Z_ERSTELLUNG, Z_KASSE_ID, node=event_node, event_settings=till_settings
                    )
                    # sammle Kassenabschlussmodul
                    await self.kassenabschlussmodul(conn, Z_NR, Z_ERSTELLUNG, Z_KASSE_ID, event_settings=till_settings)

            self.finalize()  # schreibe die Datei
            LOGGER.info(f"Duration: {time.monotonic() - self.starttime:.3f}s")
            return

    async def einzelaufzeichnungsmodul(
        self, conn, Z_NR: int, Z_ERSTELLUNG: datetime, Z_KASSE_ID: int, event_settings: RestrictedEventSettings
    ):
        self.GV_SUMME = {
            "MehrzweckgutscheinKauf": {1: BNU(), 2: BNU(), 5: BNU(), 1337: BNU()},
            "Geldtransit": {1: BNU(), 2: BNU(), 5: BNU(), 1337: BNU()},
            "DifferenzSollIst": {1: BNU(), 2: BNU(), 5: BNU(), 1337: BNU()},
            "Pfand": {1: BNU(), 2: BNU(), 5: BNU(), 1337: BNU()},
            "PfandRueckzahlung": {1: BNU(), 2: BNU(), 5: BNU(), 1337: BNU()},
            "MehrzweckgutscheinEinloesung": {1: BNU(), 2: BNU(), 5: BNU(), 1337: BNU()},
            "Umsatz": {1: BNU(), 2: BNU(), 5: BNU(), 1337: BNU()},
        }  # leeren

        ### a transactions.csv ###
        ### b transactions_tse.csv ###
        ### c transactions_vat.csv ###
        ### d datapayment.csv ###
        # alle orders für diese Kasse und Abschluss abfragen:
        for row in await conn.fetch(
            """
            select
                ordr.id,
                ordr.payment_method,
                ordr.cash_register_id,
                ordr.booked_at,
                ordr.cancels_order,
                tse_signature.tse_start,
                tse_signature.tse_end,
                tse_signature.tse_id,
                tse_signature.tse_transaction,
                tse_signature.transaction_process_type,
                tse_signature.tse_signaturenr,
                tse_signature.transaction_process_data,
                tse_signature.tse_signature,
                ordr.cashier_id,
                ordr.customer_account_id,
                ordr.order_type,
                ordr.item_count,
                tse_signature.signature_status,
                tse_signature.result_message,
                order_value.total_price,
                order_value.line_items
            from
                ordr
            join
                tse_signature on ordr.id=tse_signature.id
            join
                order_value on ordr.id=order_value.id
            where
                ordr.till_id = $1
                and ordr.z_nr = $2
            order by
                ordr.id
            """,
            Z_KASSE_ID,
            Z_NR,
        ):
            if row["signature_status"] == "new" or row["signature_status"] == "pending":
                raise RuntimeError(
                    "DSFinV-K export requires all signing requests to be settled; "
                    f"open signatures remain (order {row['id']})"
                )

            a = Bonkopf()
            b = TSE_Transaktionen()

            a.Z_KASSE_ID = Z_KASSE_ID
            a.Z_ERSTELLUNG = Z_ERSTELLUNG
            a.Z_NR = Z_NR
            b.Z_KASSE_ID = Z_KASSE_ID
            b.Z_ERSTELLUNG = Z_ERSTELLUNG
            b.Z_NR = Z_NR

            a.BON_ID = row["id"]  # bon_id und Bon_nr sind gleich
            a.BON_NR = row["id"]
            b.BON_ID = row["id"]

            if row["signature_status"] == "failure":
                b.TSE_TA_FEHLER = f"TSE Fehler: {row['result_message']}"
                a.BON_START = a.BON_ENDE = row["booked_at"].astimezone()
            else:
                b.TSE_ID = int(row["tse_id"])
                b.TSE_TANR = int(row["tse_transaction"])
                start = parser.isoparse(row["tse_start"])
                end = parser.isoparse(row["tse_end"])
                # The Diebold adapter stores UTC timestamps without a timezone suffix.
                if start.tzinfo is None:
                    start = start.replace(tzinfo=timezone.utc)
                if end.tzinfo is None:
                    end = end.replace(tzinfo=timezone.utc)
                a.BON_START = start.astimezone()
                a.BON_ENDE = end.astimezone()
                b.TSE_TA_START = start
                b.TSE_TA_ENDE = end
                b.TSE_TA_VORGANGSART = row["transaction_process_type"]
                b.TSE_TA_SIGZ = int(row["tse_signaturenr"])
                b.TSE_TA_SIG = row["tse_signature"]
                b.TSE_TA_VORGANGSDATEN = row["transaction_process_data"]

            a.BON_TYP = "Beleg"
            a.BON_NAME = row["order_type"]

            a.BEDIENER_ID = row["cashier_id"]  # Kassierer NR

            a.UMS_BRUTTO = Decimal(row["total_price"])
            a.KUNDE_ID = row["customer_account_id"]
            a.KUNDE_TYP = ORDERTYPE_TO_KUNDETYP[row["order_type"]]

            # Storno
            if row["cancels_order"] is not None:
                a.BON_NOTIZ = f"Storno von BON_ID {row['cancels_order']}"
                a.BON_STORNO = True
            else:
                pass

            # einmal über alle Umsatzsteuersätze je Order iterieren
            # leider müssen wir da wieder eine db abfrage machen....
            if row["item_count"] != 0:
                for line in await conn.fetch(
                    "select tax_name, total_price, total_tax, total_no_tax from order_tax_rates where id = $1",
                    row["id"],
                ):
                    c = Bonkopf_USt()
                    c.Z_KASSE_ID = Z_KASSE_ID
                    c.Z_ERSTELLUNG = Z_ERSTELLUNG
                    c.Z_NR = Z_NR

                    c.BON_ID = row["id"]
                    c.UST_SCHLUESSEL = TAXNAME_TO_SCHLUESSELNUMMER[line["tax_name"]]
                    c.BON_BRUTTO = Decimal(line["total_price"])
                    c.BON_NETTO = Decimal(line["total_no_tax"])
                    c.BON_UST = Decimal(line["total_tax"])

                    self.c.add(c)
            else:
                LOGGER.warning(f"Order {row['id']} has no line_items...")

            d = Bonkopf_Zahlarten()  # eigentlich nur eine Zahlart pro Order, AUßER es wird ein Gutschein eingesetzt
            d.Z_KASSE_ID = Z_KASSE_ID
            d.Z_ERSTELLUNG = Z_ERSTELLUNG
            d.Z_NR = Z_NR
            # TODO Gutscheinfall? vielleicht auch in die Datei Bonpos_Preisfindung, Zahlart ist eh immer 'tag'?
            d.BON_ID = row["id"]
            d.ZAHLART_TYP = PAYMENT_METHOD_TO_ZAHLUNGSART[row["payment_method"]]  # 'Bar'/'Unbar'
            d.ZAHLART_NAME = row["payment_method"]
            d.ZAHLWAEH_CODE = event_settings.currency_identifier
            d.ZAHLWAEH_BETRAG = Decimal(0)  # Fremdwährung, bei uns immer 0
            d.BASISWAEH_BETRAG = Decimal(row["total_price"])  # Bezahlter betrag in Grundwährung
            d.KASSENSCHUBLADENNR = row[
                "cash_register_id"
            ]  # Nummer der Kassenschublade (nur bei Kassen, die Bargeld annehmen), Eigenkreation in Anlehnung an FAQ vom Bundesfinanzministerium zum Kassengesetz
            self.c.add(d)

            self.c.add(a)
            self.c.add(b)
            ### /datapayment.csv ###
            ### /transactions_vat.csv ###
            ### /transactions_tse.csv ###
            ### /transactions.csv ###

            # so, und jetzt noch für jede dieser Transaktionen noch die einzelnen Zeilen
            ### lines.csv ###
            for item in row["line_items"]:
                e = Bonpos()
                e.Z_KASSE_ID = Z_KASSE_ID
                e.Z_ERSTELLUNG = Z_ERSTELLUNG
                e.Z_NR = Z_NR
                e.BON_ID = row["id"]
                e.POS_ZEILE = item["item_id"] + 1  # weiß nicht, ob das Finanzamt bei 0 anfängt zu zählen
                e.ARTIKELTEXT = item["product"]["name"]
                e.ART_NR = item["product"]["id"]
                e.MENGE = Decimal(item["quantity"])
                e.INHAUS = False  # TODO nachgucken, ob wichtig. jetzt erstmal alles als Außerhausverkauf
                e.P_STORNO = False  # nicht vorgesehen
                e.AGENTUR_ID = 0  # Agenturen noch nicht implementiert

                # finde den Geschäftsvorfalltyp dieses "Artikels" heraus...
                gvtyp = "Umsatz"
                if row["order_type"] == "top_up" or row["order_type"] == "pay_out":
                    gvtyp = "MehrzweckgutscheinKauf"
                elif row["order_type"] == "money_transfer":
                    gvtyp = "Geldtransit"

                elif row["order_type"] == "money_transfer_imbalance":
                    gvtyp = "DifferenzSollIst"

                elif row["order_type"] == "sale":
                    if item["product"]["is_returnable"] and item["total_price"] > 0:
                        gvtyp = "Pfand"

                    elif item["product"]["is_returnable"] and item["total_price"] < 0:
                        gvtyp = "PfandRueckzahlung"

                    else:
                        gvtyp = "MehrzweckgutscheinEinloesung"
                elif row["order_type"] == "ticket":
                    if item["product"]["name"].startswith(
                        "Eintritt"
                    ):  # TODO Eintritt kann nicht anders benannt werden, muss evtl noch spezielles Flag bekommen
                        gvtyp = "Umsatz"  # Eintritt
                    elif (
                        item["product"]["name"] == "Aufladen"
                    ):  # TODO besser noch, alle Aufladeoperationen bekommen ein bestimmtes Flag
                        gvtyp = "MehrzweckgutscheinKauf"

                else:
                    gvtyp = "Umsatz"  # alles andere

                self.GV_SUMME[gvtyp][int(TAXNAME_TO_SCHLUESSELNUMMER[item["tax_name"]])].Brutto += Decimal(
                    item["total_price"]
                )
                self.GV_SUMME[gvtyp][int(TAXNAME_TO_SCHLUESSELNUMMER[item["tax_name"]])].USt += Decimal(
                    item["total_tax"]
                )
                self.GV_SUMME[gvtyp][int(TAXNAME_TO_SCHLUESSELNUMMER[item["tax_name"]])].Netto += Decimal(
                    item["total_price"]
                ) - Decimal(item["total_tax"])
                e.GV_TYP = gvtyp

                e.GV_NAME = ""

                f = Bonpos_USt()
                f.Z_KASSE_ID = Z_KASSE_ID
                f.Z_ERSTELLUNG = Z_ERSTELLUNG
                f.Z_NR = Z_NR
                f.BON_ID = row["id"]
                f.POS_ZEILE = int(item["item_id"]) + 1
                f.UST_SCHLUESSEL = TAXNAME_TO_SCHLUESSELNUMMER[item["tax_name"]]
                f.POS_BRUTTO = Decimal(item["total_price"])
                f.POS_UST = Decimal(item["total_tax"])
                f.POS_NETTO = Decimal(item["total_price"]) - Decimal(item["total_tax"])

                self.c.add(e)
                self.c.add(f)

            ### /lines.csv ###

            ### itemamounts.csv ### ##brauchen wir nicht, weil Gutscheine in den Lineitems als Rabatprodukt auftauchen
            # a=Bonpos_Preisfindung()
            # a.Z_KASSE_ID = Z_KASSE_ID
            # a.Z_ERSTELLUNG = Z_ERSTELLUNG
            # a.Z_NR = Z_NR
            ### /itemamounts.csv ###

        return

    async def stammdatenmodul(
        self,
        conn: Connection,
        Z_NR: int,
        Z_ERSTELLUNG: datetime,
        Z_KASSE_ID: int,
        node: Node,
        event_settings: RestrictedEventSettings,
    ):
        ### cashpointclosing.csv ###
        a = Stamm_Abschluss()
        # wir haben für jeden Kassenabschluss und Kasse immer die gleichen Stammdaten (pro Festival)
        a.Z_KASSE_ID = Z_KASSE_ID
        a.Z_ERSTELLUNG = Z_ERSTELLUNG
        a.Z_NR = Z_NR
        a.TAXONOMIE_VERSION = "2.3"  # aktuelle version der DSFinV-K
        a.NAME = event_settings.bon_issuer
        a.STRASSE = self.Street
        a.PLZ = self.PLZ
        a.ORT = self.City
        a.LAND = "DEU"  # sorry, not in db -> hardcoded
        a.STNR = ""
        a.USTID = event_settings.ust_id

        a.Z_START_ID = await conn.fetchval(
            "select id from ordr where ordr.till_id = $1 and ordr.z_nr = $2 order by ordr.id asc", Z_KASSE_ID, Z_NR
        )  # erste BON_ID in diesem Abschluss
        a.Z_ENDE_ID = await conn.fetchval(
            "select id from ordr where ordr.till_id = $1 and ordr.z_nr = $2 order by ordr.id desc", Z_KASSE_ID, Z_NR
        )  # letzte BON_ID in diesem Abschluss

        Z_SE_ZAHLUNGEN = Decimal()
        Z_SE_BARZAHLUNGEN = Decimal()
        for row in await conn.fetch(
            "select total_price, payment_method from line_item join ordr on line_item.order_id = ordr.id "
            "where ordr.till_id = $1 and ordr.z_nr = $2",
            Z_KASSE_ID,
            Z_NR,
        ):
            Z_SE_ZAHLUNGEN += Decimal(row["total_price"])
            if PAYMENT_METHOD_TO_ZAHLUNGSART[row["payment_method"]] == "Bar":
                Z_SE_BARZAHLUNGEN += Decimal(row["total_price"])

        a.Z_SE_ZAHLUNGEN = Z_SE_ZAHLUNGEN  # Summe alle Zahlungen dieser Kasse für diesen Kassenabschluss
        a.Z_SE_BARZAHLUNGEN = Z_SE_BARZAHLUNGEN  # Summe alle Barzahlungen dieser Kasse für diesen Kassenabschluss

        self.c.add(a)
        ### \cashpointclosing.csv ###

        ### locations.csv ###
        LOGGER.debug("Stamm_Orte start")
        a = Stamm_Orte()
        a.Z_KASSE_ID = Z_KASSE_ID
        a.Z_ERSTELLUNG = Z_ERSTELLUNG
        a.Z_NR = Z_NR

        a.LOC_NAME = event_settings.bon_issuer
        a.LOC_STRASSE = self.Street
        a.LOC_PLZ = self.PLZ
        a.LOC_ORT = self.City
        a.LOC_LAND = "DEU"  # sorry, not in db -> hardcoded
        a.USTID = event_settings.ust_id

        self.c.add(a)
        ### \locations.csv ###

        ### cashregister.csv ###
        a = Stamm_Kassen()
        a.Z_KASSE_ID = Z_KASSE_ID
        a.Z_ERSTELLUNG = Z_ERSTELLUNG
        a.Z_NR = Z_NR
        a.KASSE_BRAND = "TeamFestlichPay"
        a.KASSE_MODELL = "v0"  # TODO version?
        history_tse_id = await conn.fetchval(
            "select tse_id from till_tse_history where till_id=$1 and what='register' and z_nr<=$2 "
            "order by z_nr desc, date desc limit 1",
            str(Z_KASSE_ID),
            Z_NR,
        )
        fiscal_serial = await conn.fetchval(
            "select c.serial from fiskaly_client_binding b join fiskaly_client c on c.id=b.client_id "
            "where b.till_id=$1 and b.tse_id=$2",
            Z_KASSE_ID,
            history_tse_id,
        )
        a.KASSE_SERIENNR = fiscal_serial or str(Z_KASSE_ID)
        a.KASSE_SW_BRAND = "TeamFestlichPay Enterprise Payment Solutions Festival Edition Pro"
        a.KASSE_SW_VERSION = "v0"  # TODO version?
        a.KASSE_BASISWAEH_CODE = event_settings.currency_identifier
        a.KASSE_UST_ZUORDNUNG = ""  # puh?

        self.c.add(a)
        ### \cashregister.csv ###

        ### vat.csv ###
        for row in await conn.fetch("select name, rate, description from tax_rate where node_id = $1", node.id):
            a = Stamm_USt()
            a.Z_KASSE_ID = Z_KASSE_ID
            a.Z_ERSTELLUNG = Z_ERSTELLUNG
            a.Z_NR = Z_NR

            a.UST_SCHLUESSEL = TAXNAME_TO_SCHLUESSELNUMMER[row["name"]]
            a.UST_SATZ = Decimal(row["rate"] * 100)
            a.UST_BESCHR = row["description"]
            self.c.add(a)

        ### \vat.csv ###

        ### tse.csv ###
        signed_tse_rows = await conn.fetch(
            "select distinct s.tse_id from tse_signature s join ordr o on o.id=s.id "
            "where o.till_id=$1 and o.z_nr=$2 and s.signature_status='done' order by s.tse_id",
            Z_KASSE_ID,
            Z_NR,
        )
        tse_ids = [row["tse_id"] for row in signed_tse_rows]
        if not tse_ids and history_tse_id is not None:
            tse_ids.append(history_tse_id)
        for tse_id in tse_ids:
            row = await conn.fetchrow(
                "select id,serial,hashalgo,time_format,process_data_encoding,public_key,certificate from tse where id=$1",
                tse_id,
            )
            assert row is not None
            self.add_tse_master_data(Z_KASSE_ID, Z_ERSTELLUNG, Z_NR, row)

    def add_tse_master_data(self, till_id: int, closing_time: datetime, closing_number: int, row):
        a = Stamm_TSE()
        a.Z_KASSE_ID = till_id
        a.Z_ERSTELLUNG = closing_time
        a.Z_NR = closing_number
        a.TSE_ID = int(row["id"])
        a.TSE_SERIAL = row["serial"]
        a.TSE_SIG_ALGO = row["hashalgo"]
        a.TSE_ZEITFORMAT = row["time_format"]
        a.TSE_PD_ENCODING = row["process_data_encoding"]
        a.TSE_PUBLIC_KEY = row["public_key"]
        certificate_fields = ("I", "II", "III", "IV", "V")
        for suffix, part in zip(certificate_fields, _split_tse_certificate(row["certificate"])):
            setattr(a, f"TSE_ZERTIFIKAT_{suffix}", part)

        self.c.add(a)
        ### \tse.csv ###

        return

    async def kassenabschlussmodul(
        self,
        conn: Connection,
        Z_NR: int,
        Z_ERSTELLUNG: datetime,
        Z_KASSE_ID: int,
        event_settings: RestrictedEventSettings,
    ):
        paymentmethods = await conn.fetch(
            "select payment_method from line_item join ordr on line_item.order_id = ordr.id "
            "where ordr.till_id = $1 and ordr.z_nr = $2 group by payment_method",
            Z_KASSE_ID,
            Z_NR,
        )
        barzahlungen = Decimal(0)
        summe_je_zahlart = dict()
        for method in paymentmethods:
            summe_je_zahlart[str(method["payment_method"])] = Decimal(0)

        for row in await conn.fetch(
            "select total_price, payment_method from line_item join ordr on line_item.order_id = ordr.id "
            "where ordr.till_id = $1 and ordr.z_nr = $2",
            Z_KASSE_ID,
            Z_NR,
        ):
            summe_je_zahlart[row["payment_method"]] += Decimal(row["total_price"])
            if PAYMENT_METHOD_TO_ZAHLUNGSART[row["payment_method"]] == "Bar":
                barzahlungen += Decimal(row["total_price"])

        ### businesscases.csv###
        # wir iterieren über die daten die wir in im einzelaufzeichnungsmodul aggregiert haben
        for gvtyp, summe in self.GV_SUMME.items():
            for schluessel, betrag in summe.items():
                a = Z_GV_Typ()
                a.Z_KASSE_ID = Z_KASSE_ID
                a.Z_ERSTELLUNG = Z_ERSTELLUNG
                a.Z_NR = Z_NR
                a.GV_TYP = gvtyp
                a.GV_NAME = ""
                a.AGENTUR_ID = 0  # TODO: Agentur hart auf 0, andere Agenturen not implemented
                a.UST_SCHLUESSEL = int(schluessel)
                a.Z_UMS_BRUTTO = betrag.Brutto
                a.Z_UMS_NETTO = betrag.Netto
                a.Z_UST = betrag.USt
                if betrag.Brutto != 0:
                    self.c.add(a)
        ### \businesscases.csv###

        ### payment.csv###
        for typ in paymentmethods:
            a = Z_Zahlart()
            a.Z_KASSE_ID = Z_KASSE_ID
            a.Z_ERSTELLUNG = Z_ERSTELLUNG
            a.Z_NR = Z_NR
            a.ZAHLART_TYP = PAYMENT_METHOD_TO_ZAHLUNGSART[typ["payment_method"]]
            a.ZAHLART_NAME = typ["payment_method"]
            a.Z_ZAHLART_BETRAG = summe_je_zahlart[typ["payment_method"]]
            self.c.add(a)
        ### \payment.csv###

        ### cash_per_currency.csv###
        a = Z_Waehrungen()
        a.Z_KASSE_ID = Z_KASSE_ID
        a.Z_ERSTELLUNG = Z_ERSTELLUNG
        a.Z_NR = Z_NR
        a.ZAHLART_WAEH = event_settings.currency_identifier
        a.ZAHLART_BETRAG_WAEH = barzahlungen  # Gesamtsumme der Barzahlungen je Währung (... wir nehmen nur eine!)
        self.c.add(a)
        ### \cash_per_currency.csv###

        return

    ################################################################################################################

    def finalize(self):
        if not self.simulate:
            LOGGER.info("write file")
            self.c.write(self.filename, self.xml, self.dtd)
        else:
            print(self.c)
            LOGGER.info("Simulation; No file written.")
        return
