"""
this code will simulate the dn TSE webservice (more or less)
"""

# TODO should we rename Transaction to Order here as well?

import base64
import binascii
import json
import logging
import re
import time
from datetime import datetime, timedelta, timezone
from hashlib import sha256, sha384
from inspect import stack
from random import randbytes, randrange
from typing import Optional

import ecdsa
import uvicorn
from asn1crypto.core import (
    Any,
    Integer,
    ObjectIdentifier,
    OctetString,
    PrintableString,
    Sequence,
)
from fastapi import FastAPI, WebSocket

from stustapay.tse.diebold_nixdorf_usb.protocol import TseResponse, TseSuccess, dnerror


class SignatureAlgorithm_seq(Sequence):
    _fields = [
        ("signatureAlgorithm", ObjectIdentifier),
        ("parameters", OctetString, {"optional": True}),
    ]


class CertifiedData(Sequence):
    _fields = [
        ("operationType", PrintableString, {"implicit": 0}),
        ("clientId", PrintableString, {"implicit": 1}),
        ("ProcessData", OctetString, {"implicit": 2}),
        ("ProcessType", PrintableString, {"implicit": 3}),
        ("additionalExternalData", OctetString, {"implicit": 4, "optional": True}),
        ("transactionNumber", Integer, {"implicit": 5}),
        ("additionalInternalData", OctetString, {"implicit": 6, "optional": True}),
    ]


class TransactionData(Sequence):
    _fields = [
        ("Version", Integer),
        ("CertifiedDataType", ObjectIdentifier),
        ("CertifiedData", Any),
        ("SerialNumber", OctetString),
        ("signatureAlgorithm", Sequence),
        ("signatureCounter", Integer),
        ("LogTime", Integer),  # unixTime!
    ]


MAGIC_PRODUCTION_CLIENT = "DN TSEProduction ef82abcedf"


class VirtualTSE:
    def __init__(
        self, delay: float, fast: bool, real: bool, private_key_hex: Optional[str], gen_key: bool, broken: bool
    ):
        self._fast: bool = fast
        self._real: bool = real
        self._delay: float = delay
        self._broken: bool = broken

        self.password_block_counter = 0
        self.puk_block_counter = 0
        self.transnr = 0
        self.signctr = 0
        # map from "client id" -> set of transactions
        self.current_transactions = dict[str, set[int]]()
        self.current_transactions["POS001"] = set()
        self.current_transactions[MAGIC_PRODUCTION_CLIENT] = set()
        self.current_transactions["DummyDefaultClientId"] = set()

        if private_key_hex is not None:
            self.sk = ecdsa.SigningKey.from_string(
                bytes.fromhex(private_key_hex), curve=ecdsa.BRAINPOOLP384r1, hashfunc=sha384
            )
            if gen_key:
                print("Secret key supplied, therefore NOT generating a new one.")
        else:
            if gen_key:
                self.sk = ecdsa.SigningKey.generate(curve=ecdsa.BRAINPOOLP384r1, hashfunc=sha384)
                print(f"new generated secret key: {self.sk.to_string().hex()}")
            else:
                self.sk = ecdsa.SigningKey.from_string(
                    bytes.fromhex(
                        "65a194772ded349bf0bf915a4f47f0a33fdc3078399c83530c2e91548119c9705f242056ad91f41ada94bf4954d08228"
                    ),
                    curve=ecdsa.BRAINPOOLP384r1,
                    hashfunc=sha384,
                )

        vk = self.sk.get_verifying_key()
        self.public_key = Sequence.load(vk.to_der())[1].dump()[3:]
        self.serial = sha256(self.public_key).hexdigest()

        print(f"Serial Number: {self.serial}")
        self.certificate = b"THIS IS A VERY LONG CERTIFICATE!!!!"
        self.password_admin = "12345"
        self.password_timeadmin = self.password_admin
        self.puk = "000000"

        # just return ok
        self.ignored_commands = [
            "Initialize",
            "Deinitialize",
            "PerformSelfTest",
            "SetDefaultClientID",
            "GetServiceInfo",
            "Export",
            "ExportRemove",
            "ExportAbort",
            "UpdateTime",
            "ChangePuk",
            "GetLimits",
            "SetLimits",
        ]

    def parse_input(self, msgdata):
        msg = json.loads(msgdata.strip("\x02").strip("\n").strip("\x03"))

        # extract command
        if "Command" not in msg:
            response = {"Status": "error"}
        else:
            response = self.act_on_command(msg)

        if "PingPong" in msg:
            response["PingPong"] = msg["PingPong"]

        return f"\x02{json.dumps(response)}\x03\n"

    def act_on_command(self, msg):
        response = {"Command": msg["Command"]}
        if msg["Command"] == "PingPong":
            response["Status"] = "ok"

        elif msg["Command"] == "StartTransaction":
            response.update(self.starttrans(msg))
        elif msg["Command"] == "UpdateTransaction":
            response.update(self.updatetrans(msg))
        elif msg["Command"] == "FinishTransaction":
            response.update(self.finishtrans(msg))
        elif msg["Command"] == "ChangePassword":
            response.update(self.changepassword(msg))
        elif msg["Command"] == "UnblockUser":
            response.update(self.unblockuser(msg))
        elif msg["Command"] == "RegisterClientID":
            response.update(self.registerclientid(msg))
        elif msg["Command"] == "DeregisterClientID":
            response.update(self.deregisterclientid(msg))
        elif msg["Command"] == "GetDeviceStatus":
            response.update(self.getdevicestatus(msg))
        elif msg["Command"] == "GetDeviceInfo":
            response.update(self.getdeviceinfo(msg))
        elif msg["Command"] == "GetDeviceData":
            response.update(self.getdevicedata(msg))
        elif msg["Command"] in self.ignored_commands:
            response["Status"] = "ok"
        else:
            response.update(dnerror(2))  # command unsuported

        return response

    # transactions
    def starttrans(self, msg) -> TseResponse:
        # check if all Parameters are here
        if "ClientID" not in msg or "Password" not in msg:
            return dnerror(3)  # param missing

        # check if blocked
        if self.password_block_counter >= 3:
            return dnerror(32)  # user blocked

        # check password_timeadmin == 12345
        try:
            if base64.b64decode(msg["Password"]).decode("utf8") != self.password_timeadmin:
                self.password_block_counter += 1
                return dnerror(30)  # password wrong
        except binascii.Error:
            return dnerror(9)  # base64

        self.password_block_counter = 0

        if msg["ClientID"] not in self.current_transactions:
            return dnerror(19)

        # count number of open transactions
        number_of_open_transactions = 0
        for t in self.current_transactions:
            number_of_open_transactions += len(self.current_transactions[t])

        if number_of_open_transactions > 512:  # max number of open transactions is 512 for Dn TSE
            return dnerror(21)

        if self._broken:
            if self.transnr >= 30:
                print("TIIIIIIIME TOOOOOOOOO SAY GOODBYE........")
                return dnerror(33)

        # generate transaction
        self.signctr += 1
        self.transnr += 1
        self.current_transactions[msg["ClientID"]].add(self.transnr)

        log_time = datetime.now(timezone(timedelta(hours=2)))
        response: TseResponse = {
            "Status": "ok",
            "TransactionNumber": self.transnr,
            "SerialNumber": self.serial,
            "SignatureCounter": self.signctr,
            "Signature": self.generate_signature(msg, str(self.transnr), log_time),
            "LogTime": log_time.isoformat(timespec="seconds"),
        }

        return response

    def updatetrans(self, msg) -> TseResponse:
        # check if all Parameters are here
        if "ClientID" not in msg or "Password" not in msg or "TransactionNumber" not in msg:
            return dnerror(3)  # param missing

        # check if blocked
        if self.password_block_counter >= 3:
            return dnerror(32)  # user blocked

        # check password_timeadmin == 12345
        try:
            if base64.b64decode(msg["Password"]).decode("utf8") != self.password_timeadmin:
                self.password_block_counter += 1
                return dnerror(30)  # password wrong
        except binascii.Error:
            return dnerror(9)  # base64

        if msg["ClientID"] not in self.current_transactions:
            return dnerror(19)

        self.password_block_counter = 0

        # check transaction number
        if msg["TransactionNumber"] not in self.current_transactions[msg["ClientID"]]:
            # error this transaction was not started
            return dnerror(5017)

        response: TseSuccess = {"Status": "ok"}
        if "Unsigned" in msg:
            if msg["Unsigned"] == "true":
                return response  # do not create a signature

        self.signctr += 1
        response["SignatureCounter"] = self.signctr
        log_time = datetime.now(timezone(timedelta(hours=1)))
        response["Signature"] = self.generate_signature(msg, str(self.transnr), log_time)
        response["LogTime"] = log_time.isoformat(timespec="seconds")

        return response

    def finishtrans(self, msg) -> TseResponse:
        # check if all Parameters are here
        if "ClientID" not in msg or "Password" not in msg or "TransactionNumber" not in msg:
            return dnerror(3)  # param missing

        # check if blocked
        if self.password_block_counter >= 3:
            return dnerror(32)  # user blocked

        # check password_timeadmin == 12345
        try:
            if base64.b64decode(msg["Password"]).decode("utf8") != self.password_timeadmin:
                self.password_block_counter += 1
                return dnerror(30)  # password wrong
        except binascii.Error:
            return dnerror(9)  # base64

        if msg["ClientID"] not in self.current_transactions:
            return dnerror(19)

        self.password_block_counter = 0

        # check transaction number
        if msg["TransactionNumber"] not in self.current_transactions[msg["ClientID"]]:
            # error this transaction was not started
            return dnerror(5017)
        self.current_transactions[msg["ClientID"]].remove(msg["TransactionNumber"])

        if self._broken:
            if self.transnr >= 20:
                self.transnr = 40
                print("TIIIIIIIME TOOOOOOOOO SAY GOODBYE........")
                while True:
                    time.sleep(1)

        self.signctr += 1
        log_time = datetime.now(timezone(timedelta(hours=1)))
        response: TseResponse = {
            "Status": "ok",
            "SignatureCounter": self.signctr,
            "Signature": self.generate_signature(msg, msg["TransactionNumber"], log_time),
            "LogTime": log_time.isoformat(timespec="seconds"),
        }

        return response

    # management
    def changepassword(self, msg) -> TseResponse:
        # check if all Parameters are here
        if "UserID" not in msg or "NewPassword" not in msg or "OldPassword" not in msg:
            return dnerror(3)  # param missing

        try:
            oldpw = base64.b64decode(msg["OldPassword"]).decode("utf8")
            user = base64.b64decode(msg["UserID"]).decode("utf8")
            newpw = base64.b64decode(msg["NewPasswd"]).decode("utf8")
        except binascii.Error:
            return dnerror(9)  # base64

        if self.password_block_counter >= 3:
            return dnerror(32)  # user blocked

        if user == "01":
            password = self.password_admin
        elif user == "02":
            password = self.password_timeadmin
        else:
            return dnerror(29)  # wrong user

        # check old pw
        if oldpw != password:
            self.password_block_counter += 1
            return dnerror(30)  # password wrong

        if len(newpw) != 5:
            return dnerror(27)  # password invalid

        if user == "01":
            self.password_admin = newpw
        elif user == "02":
            self.password_timeadmin = newpw

        self.password_block_counter = 0
        return {"Status": "ok"}

    def unblockuser(self, msg) -> TseResponse:
        # check if all Parameters are here
        if "UserID" not in msg or "NewPassword" not in msg or "Puk" not in msg:
            return dnerror(3)  # param missing

        try:
            puk = base64.b64decode(msg["Puk"]).decode("utf8")
            user = base64.b64decode(msg["UserID"]).decode("utf8")
            newpw = base64.b64decode(msg["NewPasswd"]).decode("utf8")
        except binascii.Error:
            return dnerror(9)  # base64

        if self.puk_block_counter >= 3:
            self.password_block_counter = 4
            return dnerror(33)  # puk blocked

        if user == "01":
            pass
        elif user == "02":
            pass
        else:
            return dnerror(29)  # wrong user

        # check Puk == 000000
        if puk != self.puk:
            self.puk_block_counter += 1
            return dnerror(31)  # puk wrong

        if len(newpw) != 5:
            return dnerror(27)  # password invalid

        if user == "01":
            self.password_admin = newpw
        elif user == "02":
            self.password_timeadmin = newpw
        self.password_block_counter = 0
        self.puk_block_counter = 0
        return {"Status": "ok"}

    def registerclientid(self, msg) -> TseResponse:
        # check if all Parameters are here
        if "ClientID" not in msg or "Password" not in msg:
            return dnerror(3)  # param missing
        # check if blocked
        if self.password_block_counter >= 3:
            return dnerror(32)  # user blocked
        # check password_admin == 12345
        try:
            if base64.b64decode(msg["Password"]).decode("utf8") != self.password_admin:
                self.password_block_counter += 1
                return dnerror(30)  # password wrong
        except binascii.Error:
            return dnerror(9)  # base64

        if len(msg["ClientID"]) > 30:  # Dn TSE allows only 30 characters
            return dnerror(4)

        regex = re.compile("^[a-zA-Z0-9()+,-.:? ]*$")  # check for illegal characters
        if not regex.match(msg["ClientID"]):
            return dnerror(4)

        if len(self.current_transactions) > 100:  # Dn TSE only allows 100 registered clients
            return dnerror(21)

        if msg["ClientID"] in self.current_transactions:
            return {"Status": "error", "Code": 1337, "Desc": "Client already registered"}

        self.current_transactions[msg["ClientID"]] = set()

        self.password_block_counter = 0
        return {"Status": "ok"}

    def deregisterclientid(self, msg) -> TseResponse:
        # check if all Parameters are here
        if "ClientID" not in msg or "Password" not in msg:
            return dnerror(3)  # param missing
        # check if blocked
        if self.password_block_counter >= 3:
            return dnerror(32)  # user blocked
        # check password_admin == 12345
        try:
            if base64.b64decode(msg["Password"]).decode("utf8") != self.password_admin:
                self.password_block_counter += 1
                return dnerror(30)  # password wrong
        except binascii.Error:
            return dnerror(9)  # base64

        if len(msg["ClientID"]) > 30:
            return dnerror(4)

        if msg["ClientID"] == MAGIC_PRODUCTION_CLIENT:
            return dnerror(1337)

        if msg["ClientID"] in self.current_transactions:
            if not self.current_transactions[msg["ClientID"]]:
                del self.current_transactions[msg["ClientID"]]
            else:
                return dnerror(24)
        else:
            return dnerror(5)

        self.password_block_counter = 0
        return {"Status": "ok"}

    def getdevicestatus(self, msg) -> TseResponse:
        response: TseSuccess = {"Status": "ok", "Parameters": {"SignatureAlgorithm": "ecdsa-plain-SHA384"}}
        password = msg.get("Password")
        if password is not None:
            # check if blocked
            if self.password_block_counter >= 3:
                return dnerror(32)  # user blocked
            try:
                if base64.b64decode(msg["Password"]).decode("utf8") != self.password_admin:
                    self.password_block_counter += 1
                    return dnerror(30)  # password wrong
            except binascii.Error:
                return dnerror(9)  # base64
            response["ClientIDs"] = sorted(self.current_transactions)
        return response

    def getdeviceinfo(self, msg) -> TseResponse:
        del msg
        return {"Status": "ok", "DeviceInfo": {"SerialNumber": self.serial, "TimeFormat": "UnixTime"}}

    def getdevicedata(self, msg) -> TseResponse:
        name = msg["Name"]
        encoding_format = msg.get("Format", "Hex")

        if name == "PublicKey":
            value = self.public_key
        elif name == "Certificates":
            value = self.certificate
        else:
            return dnerror(4)

        if encoding_format == "Hex":
            value_enc = binascii.hexlify(value).decode("ascii")
        elif encoding_format == "Base64":
            value_enc = base64.b64encode(value).decode("ascii")
        else:
            return dnerror(4)

        return {"Status": "ok", "Name": name, "Value": value_enc, "Length": len(value)}

    def generate_signature(self, msg, transaction_nr, log_time):
        signature: str = ""

        # simulate time required for signing process
        if not self._fast:
            time.sleep(self._delay)

        # generate bs signature
        if not self._real:
            if randrange(5) == 0:
                signature = (
                    "1c82c513e64e2cbfbefa189eafe8629ed7abce27a1b7e8de99a9ddf92b5eb9eae7fbefbe" + randbytes(60).hex()
                )
            else:
                signature = "ca8968b306a0" + randbytes(90).hex()
            return signature

        # now for the real deal

        # check from where we are called
        transaction_type = stack()[1].function
        if transaction_type == "updatetrans":
            signature = "1c82c513e64e2cbfbefa189eafe8629ed7abce27a1b7e8de99a9ddf92b5eb9eae7fbefbe" + randbytes(60).hex()
            return signature
        elif transaction_type == "starttrans":
            signature = "ca8968b306a0" + randbytes(90).hex()
            return signature
        elif transaction_type == "finishtrans":
            pass
        else:
            signature = "1c82c513e64e2cbfbefa189eafe8629ed7abce27a1b7e8de99a9ddf92b5eb9eae7fbefbe" + randbytes(60).hex()
            return signature

        signaturealgorithm = SignatureAlgorithm_seq()
        signaturealgorithm["signatureAlgorithm"] = "0.4.0.127.0.7.1.1.4.1.4"

        certidata = CertifiedData()
        certidata["operationType"] = "FinishTransaction"
        certidata["clientId"] = msg["ClientID"]
        try:
            certidata["ProcessData"] = bytes(msg["Data"].encode("utf-8"))  # optional field
        except KeyError:
            certidata["ProcessData"] = b""
        try:
            certidata["ProcessType"] = msg["Typ"]  # optional field
        except KeyError:
            certidata["ProcessType"] = ""

        certidata["transactionNumber"] = self.transnr

        data = TransactionData()
        data["Version"] = 2
        data["CertifiedDataType"] = "0.4.0.127.0.7.3.7.1.1"
        data["CertifiedData"] = certidata
        data["SerialNumber"] = sha256(self.public_key).digest()
        data["signatureAlgorithm"] = signaturealgorithm
        data["signatureCounter"] = self.signctr
        data["LogTime"] = int(log_time.timestamp())

        # why use a propper ASN.1 SEQUENCE, when you can make it much more complicated?
        message = (
            data["Version"].dump()
            + data["CertifiedDataType"].dump()
            + certidata["operationType"].dump()
            + certidata["clientId"].dump()
            + certidata["ProcessData"].dump()
            + certidata["ProcessType"].dump()
            + certidata["transactionNumber"].dump()
            + data["SerialNumber"].dump()
            + data["signatureAlgorithm"].dump()
            + data["signatureCounter"].dump()
            + data["LogTime"].dump()
        )

        signature = self.sk.sign(message).hex()
        return signature


class WebsocketInterface:
    def __init__(
        self,
        host: str = "localhost",
        port: int = 10001,
        delay: float = 0.25,
        fast: bool = False,
        real: bool = False,
        private_key_hex: Optional[str] = None,
        gen_key: bool = False,
        broken: bool = False,
    ):
        self.host: str = host
        self.port: int = port

        self.tse = VirtualTSE(delay, fast, real, private_key_hex, gen_key, broken)

    async def websocket_handler(self, websocket: WebSocket):
        print("Websocket connection starting")
        await websocket.accept()
        print("Websocket connection ready")

        while True:
            data = await websocket.receive_text()
            print(f" >>: {str(data).strip()}")
            # check for STX ETX
            if data[:1] == "\x02" and data[-2:] == "\x03\n":
                resp = self.tse.parse_input(data)

                print(f"<< : {str(resp).strip()}")
                await websocket.send_text(resp)
            else:
                print("ERROR: missing STX and/or ETX framing")

        print("Websocket connection closed")

    async def run(self):
        app = FastAPI(
            title="TSE Simulator",
            license_info={"name": "AGPL-3.0"},
        )
        app.add_websocket_route("/", self.websocket_handler)

        uvicorn_config = uvicorn.Config(
            app,
            host=self.host,
            port=self.port,
            log_level=logging.root.level,
        )
        webserver = uvicorn.Server(uvicorn_config)
        await webserver.serve()
