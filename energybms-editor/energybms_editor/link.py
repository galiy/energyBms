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

    @staticmethod
    def _pick(frames, cid2):
        """Выбирает кадр: по CID2 (BLE) или первый валидный (PACE, где CID2 нет).
        Для BLE предпочитает кадр с совпавшим CID2 и корректной CRC."""
        for fr in frames:
            if fr["cid2"] == cid2 and fr["ok"]:
                return fr
        for fr in frames:
            if fr["cid2"] == cid2:
                return fr
        for fr in frames:
            if fr["cid2"] is None and fr["ok"]:
                return fr
        return None

    def read_block(self, cid2, wait=None):
        """Читает один блок. wait — сколько ждать ответ (сек)."""
        frame = self.codec.frame_for_read(cid2)
        timeout = wait if wait is not None else (4.0 if self.transport.kind == "ble" else 2.0)
        raw = self.transport.query(frame, timeout)
        fr = self._pick(self.codec.parse_many(raw), cid2)
        if fr is None:
            return FrameResult(cid2, None, b"", False)
        return FrameResult(cid2, fr["rtn"], fr["info"], fr["ok"])

    def read_all(self):
        """Читает все поддерживаемые блоки. Возвращает {cid2: FrameResult}."""
        out = {}
        for cid in self.capabilities():
            wait = 6.0 if cid == 0x47 and self.transport.kind == "ble" else None
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

    def label(self, cid2):
        return CID_RU.get(cid2, "0x%02X" % cid2)
