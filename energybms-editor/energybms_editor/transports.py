"""Транспорты: только байты. Serial (COM/tty), TCP (прозрачный шлюз), BLE (bleak)."""
import asyncio
import socket
import time


class Transport:
    kind = "base"

    def connect(self):
        raise NotImplementedError

    def query(self, frame, timeout=2.0):
        raise NotImplementedError

    def close(self):
        pass

    def describe(self):
        return self.kind


class SerialTransport(Transport):
    kind = "serial"

    def __init__(self, port, baud=19200, timeout=2.0):
        self.port = port
        self.baud = int(baud)
        self.timeout = timeout
        self._s = None

    def connect(self):
        import serial
        self._s = serial.Serial(self.port, self.baud, timeout=self.timeout)

    def query(self, frame, timeout=2.0):
        if self._s is None:
            raise RuntimeError("порт не открыт")
        try:
            self._s.reset_input_buffer()
        except Exception:
            pass
        self._s.write(frame)
        try:
            self._s.flush()
        except Exception:
            pass
        deadline = time.time() + timeout
        got = b""
        while time.time() < deadline:
            chunk = self._s.read(256)
            if chunk:
                got += chunk
        return got

    def close(self):
        if self._s:
            try:
                self._s.close()
            finally:
                self._s = None

    def describe(self):
        return "%s @ %d" % (self.port, self.baud)


class TcpTransport(Transport):
    kind = "tcp"

    def __init__(self, host, port=502, timeout=4.0):
        self.host = host
        self.port = int(port)
        self.timeout = timeout
        self._s = None

    def connect(self):
        self._s = socket.socket()
        self._s.settimeout(self.timeout)
        self._s.connect((self.host, self.port))
        time.sleep(0.15)

    def query(self, frame, timeout=2.0):
        if self._s is None:
            raise RuntimeError("нет соединения")
        # слить возможный «хвост» от предыдущего ответа (иначе можно разобрать
        # чужой кадр — в PACE CID2 в ответе нет)
        self._s.settimeout(0.05)
        try:
            while True:
                if not self._s.recv(4096):
                    break
        except (socket.timeout, BlockingIOError, OSError):
            pass
        self._s.sendall(frame)
        self._s.settimeout(0.25)
        try:
            deadline = time.time() + timeout
            got = b""
            while time.time() < deadline:
                try:
                    d = self._s.recv(8192)
                except socket.timeout:
                    continue
                if not d:
                    break
                got += d
                if got.endswith(b"\r"):
                    break
            return got
        finally:
            self._s.settimeout(self.timeout)

    def close(self):
        if self._s:
            try:
                self._s.close()
            finally:
                self._s = None

    def describe(self):
        return "%s:%d" % (self.host, self.port)


class BleTransport(Transport):
    kind = "ble"
    SVC = "0000ff00-0000-1000-8000-00805f9b34fb"
    WRITE = "0000ff02-0000-1000-8000-00805f9b34fb"
    NOTIFY = "0000ff01-0000-1000-8000-00805f9b34fb"

    def __init__(self, name=None, address=None, scan_timeout=15.0):
        self.name = name
        self.address = address
        self.scan_timeout = scan_timeout
        self._loop = None
        self._client = None

    @staticmethod
    def scan(timeout=12.0):
        async def _scan():
            from bleak import BleakScanner
            found = await BleakScanner.discover(timeout=timeout, return_adv=True)
            out = []
            for dev, adv in found.values():
                out.append((dev.address, adv.local_name or dev.name or ""))
            return sorted(out, key=lambda x: x[1].lower())
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(_scan())
        finally:
            loop.close()

    def connect(self):
        from bleak import BleakClient, BleakScanner
        self._loop = asyncio.new_event_loop()
        try:
            self._loop.run_until_complete(self._aconnect(BleakClient, BleakScanner))
        except Exception:
            # не оставляем висеть созданный event loop при неудаче
            try:
                self._loop.close()
            finally:
                self._loop = None
            raise

    async def _aconnect(self, BleakClient, BleakScanner):
        dev = None
        if self.address:
            dev = self.address
        else:
            found = await BleakScanner.discover(timeout=self.scan_timeout, return_adv=True)
            for d, adv in found.values():
                if (adv.local_name or "") == self.name or d.address.upper() == (self.address or "").upper():
                    dev = d.address
                    break
            if dev is None and self.name:
                for d, adv in found.values():
                    if self.name.lower() in (adv.local_name or "").lower():
                        dev = d.address
                        break
        if dev is None:
            raise RuntimeError("BLE-устройство не найдено: %s" % (self.name or self.address))
        self._client = BleakClient(dev, timeout=30)
        await self._client.connect()
        if not self._client.is_connected:
            raise RuntimeError("не удалось подключиться по BLE")

    def query(self, frame, timeout=4.0):
        if self._client is None:
            raise RuntimeError("BLE не подключён")
        wr = nf = None
        for svc in self._client.services:
            for ch in svc.characteristics:
                u = ch.uuid.lower()
                if u.startswith("0000ff02"):
                    wr = ch.uuid
                if u.startswith("0000ff01"):
                    nf = ch.uuid
        wr = wr or self.WRITE
        nf = nf or self.NOTIFY
        return self._loop.run_until_complete(self._aquery(wr, nf, frame, timeout))

    async def _aquery(self, wr, nf, frame, timeout):
        buf = bytearray()

        def cb(_, data):
            buf.extend(data)

        await self._client.start_notify(nf, cb)
        try:
            await self._client.write_gatt_char(wr, frame, response=False)
            await asyncio.sleep(timeout)
        finally:
            try:
                await self._client.stop_notify(nf)
            except Exception:
                pass
        return bytes(buf)

    def close(self):
        if self._client is not None and self._loop is not None:
            try:
                self._loop.run_until_complete(self._client.disconnect())
            except Exception:
                pass
        if self._loop is not None:
            try:
                self._loop.close()
            finally:
                self._loop = None
        self._client = None

    def describe(self):
        return self.address or self.name or "BLE"


def list_serial_ports():
    try:
        from serial.tools import list_ports
        return [p.device for p in list_ports.comports()]
    except Exception:
        return []
