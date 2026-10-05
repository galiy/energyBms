"""BmsLink — связка транспорт + кодек. Чтение блоков и запись параметров 0xA1."""
from . import params as P
from .protocol import CID_RU, make_codec


class FrameResult:
    def __init__(self, cid2, rtn, info, ok):
        self.cid2 = cid2
        self.rtn = rtn
        self.info = info
        self.ok = ok

    @property
    def success(self):
        return self.ok and self.rtn == 0x00


class BmsLink:
    def __init__(self, transport, codec):
        self.transport = transport
        self.codec = codec

    @classmethod
    def create(cls, cfg):
        kind = cfg.get("transport", "tcp")
        adr = int(cfg.get("adr", 0))
        if kind == "serial":
            from .transports import SerialTransport
            tr = SerialTransport(cfg.get("serial_port", ""), cfg.get("baud", 19200))
            codec = make_codec("serial", cfg.get("port_type", "host"), adr)
        elif kind == "ble":
            from .transports import BleTransport
            tr = BleTransport(cfg.get("ble_name", ""), cfg.get("ble_address", ""))
            codec = make_codec("ble", adr=adr)
        else:
            from .transports import TcpTransport
            tr = TcpTransport(cfg.get("tcp_host", "192.0.2.77"), cfg.get("tcp_port", 502))
            codec = make_codec("tcp", cfg.get("port_type", "host"), adr)
        return cls(tr, codec)

    def connect(self):
        self.transport.connect()

    def close(self):
        self.transport.close()

    def capabilities(self):
        return self.codec.capabilities()

    # ожидаемая длина INFO ответа по CID2 (для надёжного выбора кадра в PACE,
    # где в ответе нет CID2); None — не проверять
    EXPECTED_LEN = {0x42: 75, 0x44: 49, 0x4F: 0, 0x51: 32, 0x47: 169,
                    0x4D: 7, 0xA2: 30, 0xA4: 30}

    @staticmethod
    def _pick(frames, cid2, exp=None):
        """Выбор кадра. Для BLE — по CID2 и CRC; для PACE (нет CID2) — по
        ожидаемой длине INFO, затем по ненулевому RTN (короткий ответ-ошибка)."""
        def good(f):
            if not f["ok"]:
                return False
            if f["cid2"] is not None and f["cid2"] != cid2:
                return False
            return True

        if exp is not None:
            for f in frames:
                if good(f) and len(f["info"]) == exp:
                    return f
            for f in frames:
                if good(f) and f["rtn"] != 0:
                    return f
            return None  # кадр не той длины — не подставляем чужой ответ
        for f in frames:
            if good(f) and f["rtn"] != 0:
                return f
        for f in frames:
            if good(f):
                return f
        return None

    def read_block(self, cid2, wait=None, retries=1):
        """Читает один блок. wait — сколько ждать ответ (сек); при молчании — retry."""
        frame = self.codec.frame_for_read(cid2)
        exp = self.EXPECTED_LEN.get(cid2)
        timeout = wait if wait is not None else (4.0 if self.transport.kind == "ble" else 3.0)
        fr = None
        for _ in range(retries + 1):
            raw = self.transport.query(frame, timeout)
            fr = self._pick(self.codec.parse_many(raw), cid2, exp)
            if fr is not None:
                break
        if fr is None:
            return FrameResult(cid2, None, b"", False)
        return FrameResult(cid2, fr["rtn"], fr["info"], fr["ok"])

    def read_all(self):
        """Читает все поддерживаемые блоки. Возвращает {cid2: FrameResult}."""
        out = {}
        for cid in self.capabilities():
            # блок параметров (169 Б) приходит дольше — даём больше времени
            if cid == 0x47:
                wait = 6.0 if self.transport.kind == "ble" else 5.0
            else:
                wait = None
            out[cid] = self.read_block(cid, wait)
        return out

    def write_params(self, model):
        """Записывает весь блок 169 Б командой 0xA1. model — dict decode_params."""
        payload = P.encode_params(model)
        frame = self.codec.frame_for_write(0xA1, payload)
        timeout = 4.0 if self.transport.kind == "ble" else 2.0
        raw = self.transport.query(frame, timeout)
        fr = self._pick(self.codec.parse_many(raw), 0xA1)
        if fr is None:
            # молчание/невалидный ответ трактуем как неуспех
            return FrameResult(0xA1, None, b"", False)
        return FrameResult(0xA1, fr["rtn"], fr["info"], fr["ok"])

    # ---------------------------------------------------------- команды управления
    def _send_write(self, cid2, payload=b""):
        """Пишущая команда (payload): отправка, разбор ответа."""
        frame = self.codec.frame_for_write(cid2, payload)
        timeout = 4.0 if self.transport.kind == "ble" else 3.0
        raw = self.transport.query(frame, timeout)
        fr = self._pick(self.codec.parse_many(raw), cid2)
        if fr is None:
            return FrameResult(cid2, None, b"", False)
        return FrameResult(cid2, fr["rtn"], fr["info"], fr["ok"])

    def send_control(self, bit_no, action, pack_index=0):
        """0x45 TeleCtrl: [packIndex][bitNo][action]."""
        return self._send_write(0x45, bytes([pack_index & 0xFF, bit_no & 0xFF, action & 0xFF]))

    def set_can_protocol(self, type_code):
        """Выбор CAN-протокола инвертора: BLE 0x63 / RS485 0xA6."""
        cid = 0x63 if self.transport.kind == "ble" else 0xA6
        return self._send_write(cid, bytes([type_code & 0xFF]))

    def set_485_protocol(self, type_code):
        """Выбор 485-протокола: BLE 0x64 / RS485 0xA7."""
        cid = 0x64 if self.transport.kind == "ble" else 0xA7
        return self._send_write(cid, bytes([type_code & 0xFF]))

    @staticmethod
    def _sn_payload(text):
        b = (text or "").encode("latin-1", "replace")[:30]
        return b + b" " * (30 - len(b))

    def set_bat_sn(self, text):
        """0xA5 SetBatSN: 30 ASCII-символов (дополняются пробелами)."""
        return self._send_write(0xA5, self._sn_payload(text))

    def set_dev_sn(self, text):
        """0xA3 SetSN: 30 ASCII-символов."""
        return self._send_write(0xA3, self._sn_payload(text))

    def set_time(self, dt):
        """0x4E SetTime: [год u16 BE][мес][день][час][мин][сек]."""
        payload = (dt.year.to_bytes(2, "big")
                   + bytes([dt.month, dt.day, dt.hour, dt.minute, dt.second]))
        return self._send_write(0x4E, payload)

    def label(self, cid2):
        return CID_RU.get(cid2, "0x%02X" % cid2)
