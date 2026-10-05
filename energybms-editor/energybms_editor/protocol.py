"""Кодеки протокола Enjie EMU110x: логика одна, wire-представлений два.

- PaceCodec — ASCII-hex PACE (RS485 напрямую или через прозрачный TCP-шлюз).
- BleCodec  — бинарный кадр BLE (BT2-мост).

Общий интерфейс: frame_for_read(cid2), frame_for_write(cid2, payload),
parse_many(raw) -> список кадров {cid2, rtn, info, ok}.
"""
import struct

CID1 = 0x46

# Логические команды (единый протокол)
CID = {
    0x42: "TeleMeter", 0x44: "TeleState", 0x4F: "ProtocolVer", 0x51: "Manufacture",
    0x47: "GetAllParas", 0x4B: "GetHistoryData", 0x4D: "GetTime",
    0xA2: "GetSN", 0xA4: "GetBatSN",
    0x61: "Battery", 0x62: "ParallelBattery",
    0xA1: "SetAllParas", 0x4E: "SetTime", 0x63: "SwitchCAN", 0x45: "TeleCtrl",
}
CID_RU = {
    0x42: "Телеметрия", 0x44: "Состояние/защиты", 0x4F: "Версия протокола",
    0x51: "Инфо производителя", 0x47: "Параметры", 0x4B: "История", 0x4D: "Время",
    0xA2: "Серийный номер устройства", 0xA4: "Серийный номер батареи",
    0x61: "Батарея (BLE)", 0x62: "Параллельные батареи",
}

RTN = {
    0x00: "Успешно", 0x01: "Ошибка версии протокола", 0x02: "Ошибка контроля данных",
    0x03: "Ошибка проверки длины", 0x04: "Команда не поддерживается",
    0x05: "Ошибка формата данных", 0x06: "Недопустимые данные", 0x07: "Ошибка адреса",
    0x08: "Ошибка Flash",
}


def rtn_text(rtn):
    if rtn == 0xE2:
        return "SETFAIL (параметр не сохранён)"
    if rtn in RTN:
        return RTN[rtn]
    if 0x80 <= rtn <= 0xEF:
        return "Пользовательская ошибка"
    return "Неопределённая ошибка"


# ---------------------------------------------------------------- PACE (RS485)
def _len_crc(lenid):
    nib = ((lenid >> 8) & 0xF) + ((lenid >> 4) & 0xF) + (lenid & 0xF)
    return ((lenid & 0x0FFF) | (((~(nib % 16) + 1) & 0xF) << 12)) & 0xFFFF


class PaceCodec:
    """ASCII-hex PACE. Чтение использует длину в байтах, запись — в hex-символах
    (см. protocol-485.md §2 и §8.3, оба варианта проверены вживую)."""

    def __init__(self, port_type="host", adr=0, ver=0x20):
        self.port_type = port_type
        self.adr = adr
        self.ver = ver

    @property
    def is_rm485(self):
        return self.port_type == "rm485"

    def capabilities(self):
        if self.is_rm485:
            return [0x42, 0x44, 0x4F, 0x51]
        return [0x42, 0x44, 0x4F, 0x51, 0x47, 0x4D, 0xA2, 0xA4]

    def _build(self, cid2, info, len_in_hex):
        lenid = len(info) * 2 if len_in_hex else len(info)
        s = "%02X%02X%02X%02X%04X" % (self.ver, self.adr, CID1, cid2, _len_crc(lenid))
        s += info.hex().upper()
        chk = (((~sum(ord(c) for c in s)) & 0xFFFF) + 1) & 0xFFFF
        return ("\x7e" + s + "%04X" % chk + "\r").encode("latin-1")

    def frame_for_read(self, cid2):
        info = b""
        if self.is_rm485 and cid2 in (0x42, 0x44):
            info = b"\x00"
        return self._build(cid2, info, len_in_hex=False)

    def frame_for_write(self, cid2, payload=b""):
        return self._build(cid2, payload, len_in_hex=True)

    def parse_many(self, raw):
        out = []
        for part in raw.split(b"\r"):
            idx = part.find(b"\x7e")
            if idx < 0:
                continue
            part = part[idx:]
            try:
                t = part[1:].decode("latin-1")
                if len(t) < 16:
                    continue
                # В PACE-ответе поля CID2 нет: ~ VER ADR 46 RTN LEN INFO CHK CR.
                rtn = int(t[6:8], 16)
                info = bytes.fromhex(t[12:-4])
                chk = ((~sum(ord(c) for c in t[:-4])) & 0xFFFF) + 1
                out.append({"cid2": None, "rtn": rtn, "info": info,
                            "ok": ("%04X" % chk) == t[-4:]})
            except (ValueError, IndexError):
                continue
        return out


# ---------------------------------------------------------------- BLE (binary)
def crc16_ccitt(data):
    crc = 0
    for b in data:
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
            if b & 0x80:
                crc ^= 0x1021
            b = (b << 1) & 0xFF
    return crc & 0xFFFF


class BleCodec:
    """Бинарный кадр BLE: 7E 10 ADR 46 CID2 LEN(2) INFO CHKSUM(2) 0D.
    Ответ: 7E 14 ADR CID2 RTN LEN(2) INFO ...; CRC считается БЕЗ ведущего 7E."""

    def __init__(self, adr=0):
        self.adr = adr

    def capabilities(self):
        return [0x51, 0x61, 0x62, 0x47]

    def _build(self, cid2, payload=b""):
        body = bytes([0x10, self.adr, CID1, cid2]) + struct.pack(">H", len(payload)) + payload
        return bytes([0x7E]) + body + struct.pack(">H", crc16_ccitt(body)) + bytes([0x0D])

    def frame_for_read(self, cid2):
        info = b"\x00" if cid2 in (0x61, 0x47) else b""
        return self._build(cid2, info)

    def frame_for_write(self, cid2, payload=b""):
        return self._build(cid2, payload)

    def parse_many(self, raw):
        out = []
        i = 0
        n = len(raw)
        while i < n:
            s = raw.find(b"\x7e", i)
            if s < 0 or s + 7 > n:
                break
            ln = (raw[s + 5] << 8) | raw[s + 6]
            total = 10 + ln
            if s + total > n:
                break
            fr = raw[s:s + total]
            ok = crc16_ccitt(fr[1:-3]) == ((fr[-3] << 8) | fr[-2]) and fr[-1] == 0x0D
            out.append({"cid2": fr[3], "rtn": fr[4], "info": fr[7:-3], "ok": ok})
            i = s + total
        return out


def make_codec(transport_kind, port_type="host", adr=0):
    if transport_kind == "ble":
        return BleCodec(adr=adr)
    return PaceCodec(port_type=port_type, adr=adr)
