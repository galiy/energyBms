#!/usr/bin/env python3
"""
Универсальный TCP-опрос BMS/моста (Enjie, Modbus, Solarman, raw).

Read-only: только отправка запросов и чтение ответов, ничего не пишет.

Примеры:
  # всё подряд на 8899
  python3 tcp_probe.py 192.0.2.75

  # конкретные порты и режимы
  python3 tcp_probe.py 192.0.2.75 --ports 8899,8889,502,23 --modes enjie,modbus

  # только Enjie-кадры, повтор 3 раза, удержание соединения
  python3 tcp_probe.py 192.0.2.75 --modes enjie --repeat 3 --keep-open

  # сырой кадр
  python3 tcp_probe.py 192.0.2.75 --raw-send "7e 10 00 46 51 00 00 3a 7f 0d"

  # если мост сам подключается к нам (TCP client): слушать входящее
  python3 tcp_probe.py 192.0.2.75 --listen --listen-port 8899 --listen-time 30
"""

import argparse
import socket
import struct
import sys
import time

# ---------- контрольные суммы ----------

def crc16_enjie(data: bytes) -> int:
    crc = 0
    for b in data:
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if (crc & 0x8000) else (crc << 1) & 0xFFFF
            if b & 0x80:
                crc ^= 0x1021
            b = (b << 1) & 0xFF
    return crc & 0xFFFF


def crc16_modbus(data: bytes) -> int:
    crc = 0xFFFF
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if (crc & 1) else (crc >> 1)
    return crc


# ---------- построение кадров ----------

def build_enjie(cmd1: int, payload: bytes = b"", addr: int = 0, eoi: int = 0x0D) -> bytes:
    body = bytes([0x10, addr, 0x46, cmd1]) + struct.pack(">H", len(payload)) + payload
    return bytes([0x7E]) + body + struct.pack(">H", crc16_enjie(body)) + bytes([eoi])


def enjie_frames() -> list:
    """Рабочие команды из живого BLE-дампа + варианты хвоста."""
    cmds = [
        ("BasicInfo", 0x51, b""),
        ("Battery", 0x61, b"\x00"),
        ("ParallelBattery", 0x62, b""),
        ("ReadBMSParams", 0x47, b"\x00"),
        ("ProtocolVer", 0x4F, b""),
        ("PacksNum", 0x90, b""),
        ("GetTime", 0x4D, b""),
        ("GetSN", 0xA2, b""),
        ("TeleMeter", 0x42, b""),
        ("TeleState", 0x44, b""),
    ]
    out = []
    for name, cmd, pl in cmds:
        out.append((f"enjie/{name}/eoi0d", build_enjie(cmd, pl, 0, 0x0D)))
        out.append((f"enjie/{name}/eoi1a", build_enjie(cmd, pl, 0, 0x1A)))
    for addr in (1, 0x14, 0x10):
        out.append((f"enjie/BasicInfo/addr0x{addr:02x}", build_enjie(0x51, b"", addr, 0x0D)))
    return out


def mbap(uid: int, fc: int, data: bytes, tid: int = 1) -> bytes:
    pdu = bytes([fc]) + data
    return struct.pack(">HHHB", tid, 0, len(pdu) + 1, uid) + pdu


def rtu(uid: int, fc: int, data: bytes) -> bytes:
    body = bytes([uid, fc]) + data
    return body + struct.pack("<H", crc16_modbus(body))


def modbus_frames() -> list:
    out = []
    units = [1, 2, 3, 16, 20, 0, 0xFF, 0x14]
    for u in units:
        for fc in (3, 4):
            out.append((f"modbus-tcp/fc{fc}/uid{u}", mbap(u, fc, struct.pack(">HH", 0, 10))))
        out.append((f"modbus-rtu/fc3/uid{u}", rtu(u, 3, struct.pack(">HH", 0, 10))))
        out.append((f"modbus-rtu/fc4/uid{u}", rtu(u, 4, struct.pack(">HH", 0, 10))))
    out.append(("modbus-tcp/fc1/uid1", mbap(1, 1, struct.pack(">HH", 0, 16))))
    out.append(("modbus-tcp/DevID/uid1", mbap(1, 0x2B, bytes([0x0E, 0x01, 0x00]))))
    out.append(("modbus-rtu/reportid/uid1", rtu(1, 0x11, b"")))
    return out


def solarman_v5(serial: int, seq: int, mb: bytes, control: int = 0x45) -> bytes:
    length = 15 + len(mb)
    header = (bytes([0xA5]) + struct.pack("<H", length) + bytes([0x10, control])
              + struct.pack("<H", seq) + struct.pack("<I", serial))
    payload = bytes([0x02, 0x00]) + b"\x00" * 12 + mb
    frame = header + payload
    return frame + bytes([sum(frame[1:]) & 0xFF, 0x15])


def solarman_frames() -> list:
    out = []
    for serial in (0, 1, 2, 0x01020304):
        req = rtu(1, 3, struct.pack(">HH", 0, 10))
        out.append((f"solarman/fc3/serial{serial}", solarman_v5(serial, 1, req)))
    # handshake/info control codes
    for ctrl in (0x41, 0x43, 0x47):
        req = rtu(1, 3, struct.pack(">HH", 0, 2))
        out.append((f"solarman/ctrl0x{ctrl:02x}", solarman_v5(1, 1, req, ctrl)))
    return out


def raw_frames(hexstr: str) -> list:
    return [("raw", bytes.fromhex(hexstr.replace(",", " ").replace("0x", " ")))]


# ---------- разбор ----------

def parse_enjie(buf: bytes) -> list:
    res = []
    i = 0
    while True:
        s = buf.find(b"\x7e", i)
        if s < 0:
            break
        e = buf.find(b"\x0d", s + 1)
        if e < 0:
            break
        fr = buf[s:e + 1]
        ok = crc16_enjie(fr[1:-3]) == ((fr[-3] << 8) | fr[-2]) if len(fr) >= 4 else False
        res.append((fr, ok))
        i = e + 1
    return res


# ---------- сеть ----------

def exchange(host, port, frame, read_timeout, connect_timeout=3.0):
    s = socket.socket()
    s.settimeout(connect_timeout)
    try:
        s.connect((host, port))
    except Exception as e:
        return None, f"connect error: {e}"
    try:
        s.sendall(frame)
        s.settimeout(0.4)
        chunks = []
        deadline = time.time() + read_timeout
        while time.time() < deadline:
            try:
                d = s.recv(4096)
                if not d:
                    break
                chunks.append(d)
            except socket.timeout:
                continue
        return b"".join(chunks), None
    finally:
        s.close()


def run(host, ports, modes, read_timeout, repeat, gap, keep_open, log):
    if "enjie" in modes:
        frames = enjie_frames()
    else:
        frames = []
    if "modbus" in modes:
        frames += modbus_frames()
    if "solarman" in modes:
        frames += solarman_frames()
    if "raw" in modes:
        frames += raw_frames(modes["raw"])

    hits = []
    for port in ports:
        log(f"\n================ {host}:{port} ================")
        s = None
        if keep_open:
            s = socket.socket()
            s.settimeout(3.0)
            try:
                s.connect((host, port))
                log(f"[{port}] keep-open connection established")
            except Exception as e:
                log(f"[{port}] connect error: {e}")
                s = None
        for name, frame in frames:
            for r in range(repeat):
                tag = f"{port}/{name}" + (f"#{r+1}" if repeat > 1 else "")
                if keep_open and s:
                    try:
                        s.sendall(frame)
                        s.settimeout(0.4)
                        chunks = []
                        deadline = time.time() + read_timeout
                        while time.time() < deadline:
                            try:
                                d = s.recv(4096)
                                if not d:
                                    break
                                chunks.append(d)
                            except socket.timeout:
                                continue
                        raw = b"".join(chunks)
                        err = None
                    except Exception as e:
                        raw, err = b"", str(e)
                else:
                    raw, err = exchange(host, port, frame, read_timeout)
                if err:
                    log(f"[{tag}] TX {frame.hex(' ')}  -> {err}")
                    continue
                if raw:
                    hits.append((tag, raw))
                    log(f"[{tag}] TX {frame.hex(' ')}")
                    log(f"           RX {raw.hex(' ')}")
                    for fr, ok in parse_enjie(raw):
                        log(f"           enjie-frame {fr.hex(' ')} crc_ok={ok}")
                else:
                    log(f"[{tag}] TX {frame.hex(' ')}  -> (timeout, none)")
                if gap:
                    time.sleep(gap)
        if s:
            s.close()

    log("\n================ ИТОГ ================")
    if not hits:
        log("Ответов НЕТ ни на один запрос.")
    else:
        log(f"Ответы получены ({len(hits)}):")
        for tag, raw in hits:
            log(f"  {tag}: {raw.hex(' ')}")
    return hits


def listen(host, port, duration, log):
    srv = socket.socket()
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((host if host != "" else "0.0.0.0", port))
    srv.listen(1)
    srv.settimeout(duration)
    log(f"[listen] Жду входящее TCP-подключение на {host or '0.0.0.0'}:{port} ({duration}s)...")
    try:
        conn, peer = srv.accept()
        log(f"[listen] Подключился {peer}")
        conn.settimeout(duration)
        deadline = time.time() + duration
        while time.time() < deadline:
            try:
                d = conn.recv(4096)
                if not d:
                    log("[listen] peer closed")
                    break
                log(f"[listen] RX {d.hex(' ')}")
            except socket.timeout:
                continue
        conn.close()
    except socket.timeout:
        log("[listen] Входящих подключений не было")
    finally:
        srv.close()


def main():
    p = argparse.ArgumentParser(description="Универсальный TCP-опрос BMS/моста")
    p.add_argument("host")
    p.add_argument("--ports", default="8899",
                   help="список портов через запятую (по умолчанию 8899)")
    p.add_argument("--modes", default="enjie,modbus,solarman",
                   help="enjie,modbus,solarman,raw (через запятую)")
    p.add_argument("--raw-send", default=None,
                   help="hex-строка для raw-режима, напр. '7e 10 00 46 51 00 00 3a 7f 0d'")
    p.add_argument("--read-timeout", type=float, default=3.0,
                   help="сколько ждать ответ после запроса, сек (по умолчанию 3)")
    p.add_argument("--repeat", type=int, default=1)
    p.add_argument("--gap", type=float, default=0.2)
    p.add_argument("--keep-open", action="store_true",
                   help="не переподключаться на каждый кадр")
    p.add_argument("--listen", action="store_true",
                   help="слушать входящее соединение (мост в режиме TCP client)")
    p.add_argument("--listen-port", type=int, default=8899)
    p.add_argument("--listen-time", type=float, default=30.0)
    args = p.parse_args()

    # ВНИМАНИЕ: это активный сетевой свип (порты/протоколы). Запускать только
    # по явному разрешению и только по согласованным адресам (см. AGENTS.md).
    print("!! Активный сетевой опрос: запускайте только с явного разрешения.", flush=True)

    lines = []

    def log(msg=""):
        print(msg, flush=True)
        lines.append(msg)

    ports = [int(x) for x in args.ports.split(",") if x.strip()]
    if args.raw_send:
        modes = {"raw": args.raw_send}
    else:
        modes = {m.strip(): None for m in args.modes.split(",") if m.strip()}

    if args.listen:
        listen("", args.listen_port, args.listen_time, log)
    else:
        run(args.host, ports, modes, args.read_timeout, args.repeat, args.gap,
            args.keep_open, log)

    out = f"/tmp/kilo/tcp_probe_{int(time.time())}.log"
    try:
        with open(out, "w") as f:
            f.write("\n".join(lines) + "\n")
        print(f"\n[лог сохранён: {out}]")
    except Exception:
        pass


if __name__ == "__main__":
    main()
