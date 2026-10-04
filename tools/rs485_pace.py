#!/usr/bin/env python3
"""Опрос BMS Enjie (EMU110x) по RS485 через прозрачный IP-шлюз. ТОЛЬКО ЧТЕНИЕ.

Диалект — ASCII-hex PACE:
    Запрос:  ~ VER ADR 46 CID2 LEN(4) INFO(hex) CHK(4) CR
    Ответ :  ~ VER ADR 46 RTN LEN(4) INFO(hex) CHK(4) CR
- VER=0x20, ADR=0x00, CID1=0x46.
- LEN = LCHKSUM<<12 | len(INFO);  CHK = дополнение суммы ASCII-кодов от VER до конца INFO.
- RTN: 0 ok, 3 LenCheck, 4 Command No Support (см. protocol-485.md).

Порты (руководство §10.1/§10.2):
  host  — host-RS485, 19200: read-команды уходят БЕЗ INFO (LEN=0000).
          Доступны телеметрия, состояние, параметры, время, история, SN.
  rm485 — RM485, 9600: для 0x42/0x44 нужен INFO=[00]; параметры/история недоступны.

Запись запрещена: отправляются только читающие CID2.
"""
import argparse, os, socket, select, struct, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from params_table import PARAMS, BITGROUPS
except Exception:
    PARAMS, BITGROUPS = [], {}

READ_CIDS = {
    0x42: "TeleMeter", 0x44: "TeleState", 0x4F: "ProtocolVer", 0x51: "Manufacture",
    0x47: "GetAllParas", 0x4B: "GetHistoryData", 0x4D: "GetTime", 0xA4: "GetBatSN",
}


def len_crc(lenid):
    nib = ((lenid >> 8) & 0xF) + ((lenid >> 4) & 0xF) + (lenid & 0xF)
    return ((lenid & 0x0FFF) | (((~(nib % 16) + 1) & 0xF) << 12)) & 0xFFFF


def build(ver, adr, cid2, info=b""):
    s = "%02X%02X%02X%02X%04X" % (ver, adr, 0x46, cid2, len_crc(len(info)))
    s += info.hex().upper()
    chk = ((~sum(ord(c) for c in s)) & 0xFFFF) + 1
    return ("\x7e" + s + "%04X" % chk + "\r").encode("latin-1")


def exchange(host, port, frame, wait=2.0):
    s = socket.socket(); s.settimeout(4); s.connect((host, port))
    time.sleep(0.15); s.sendall(frame)
    t0 = time.time(); got = b""
    while time.time() - t0 < wait:
        r, _, _ = select.select([s], [], [], 0.25)
        if r:
            d = s.recv(8192)
            if not d: break
            got += d
            if got.endswith(b"\r"): break
    s.close(); return got


def parse(raw):
    if not raw or raw[0] != 0x7e or not raw.endswith(b"\r"): return None
    t = raw[1:-1].decode("latin-1")
    if len(t) < 16: return None
    r = dict(ver=int(t[0:2], 16), adr=int(t[2:4], 16), cid1=int(t[4:6], 16),
             rtn=int(t[6:8], 16), len_field=int(t[8:12], 16))
    r["info"] = bytes.fromhex(t[12:-4])
    chk = ((~sum(ord(c) for c in t[:-4])) & 0xFFFF) + 1
    r["chk_ok"] = ("%04X" % chk) == t[-4:]
    return r


def u16(b, o): return (b[o] << 8) | b[o + 1]
def s16(b, o):
    v = (b[o] << 8) | b[o + 1]
    return v - 0x10000 if v & 0x8000 else v


def decode_telemetry(p):
    n = p[2]; o = 3
    cells = [u16(p, o + 2 * i) * 0.001 for i in range(n)]; o += 2 * n
    tn = p[o]; o += 1
    temps = [round(u16(p, o + 2 * i) * 0.1 - 273.1, 1) for i in range(tn)]; o += 2 * tn
    d = {"cells_V": cells, "temps_C": temps}
    d["current_A"] = s16(p, o) * 0.01; o += 2
    d["total_V"] = u16(p, o) * 0.01; o += 2
    d["remain_Ah"] = u16(p, o) * 0.01; o += 2
    d["field_count"] = p[o]; o += 1
    d["totalCap_Ah"] = u16(p, o) * 0.01; o += 2
    d["soc_%"] = u16(p, o) * 0.1; o += 2
    d["ratedCap_Ah"] = u16(p, o) * 0.01; o += 2
    d["cycles"] = u16(p, o); o += 2
    d["soh_%"] = u16(p, o) * 0.1; o += 2
    d["bus_V"] = u16(p, o) * 0.01; o += 2
    d["tempdrift_A"] = u16(p, o) * 0.001; o += 2
    d["zeroCurrent_A"] = u16(p, o) * 0.001; o += 2
    d["chargeEnergy_kWh"] = u16(p, o) * 0.1; o += 2
    d["dischargeEnergy_kWh"] = u16(p, o) * 0.1; o += 2
    d["rest"] = p[o:]
    return d


def decode_params(p):
    meta = {pt[0]: pt for pt in PARAMS}
    pack = p[0]; iCnt = p[1]; o = 2
    print("   packIndex=%d IntParaCnt=%d" % (pack, iCnt))
    for k in range(iCnt):
        raw = u16(p, o); o += 2
        m = meta.get(k); name = m[2] if m else "?"; sc = float(m[3]) if m else 1.0; un = m[4] if m else ""
        val = raw * 0.1 - 273.1 if un == "℃" else raw * sc
        print("   [0x%02X] %-46s %10.3f %s" % (k, name, val, un))
    bCnt = p[o]; o += 1
    for j in range(bCnt):
        raw = p[o]; o += 1
        pi = 0x3C + j
        m = meta.get(pi); name = m[2] if m else "?"; sc = float(m[3]) if m else 1.0; un = m[4] if m else ""
        print("   [0x%02X] %-46s %10.3f %s" % (pi, name, raw * sc, un))
    gCnt = p[o]; o += 1
    for g in range(gCnt):
        b = p[o]; o += 1
        names = BITGROUPS.get(g, [])
        bits = [names[i] for i in range(8) if i < len(names) and (b >> i) & 1]
        print("   bitgroup%d=0x%02X: %s" % (g, b, ", ".join(bits) if bits else "(выкл)"))
    print("   module_name = %r" % p[o:o + 10].decode("latin-1", "replace"))


def main():
    ap = argparse.ArgumentParser(description="RS485 PACE-опрос BMS Enjie (только чтение)")
    # Хост обязателен: дефолт на конкретный шлюз запрещён правилами проекта
    # (сетевое взаимодействие с ним — только по отдельному разрешению).
    ap.add_argument("--host", required=True, help="адрес TCP-RS485-шлюза (задавать явно)")
    ap.add_argument("--port", type=int, default=502)
    ap.add_argument("--adr", type=lambda x: int(x, 0), default=0)
    ap.add_argument("--ver", type=lambda x: int(x, 0), default=0x20)
    ap.add_argument("--port-type", choices=["host", "rm485"], default="host",
                    help="host (10.2, 19200, без INFO) или rm485 (10.1, 9600, INFO=[00] для 0x42/0x44)")
    ap.add_argument("--cid", type=lambda x: int(x, 0), default=None)
    ap.add_argument("--wait", type=float, default=2.0)
    a = ap.parse_args()

    cids = [a.cid] if a.cid else list(READ_CIDS)
    for cid in cids:
        if cid not in READ_CIDS:
            print("CID2 0x%02X не входит в список читающих — пропуск (запись запрещена)" % cid)
            continue
        if a.port_type == "rm485" and cid in (0x42, 0x44):
            info = b"\x00"
        else:
            info = b""
        fr = build(a.ver, a.adr, cid, info)
        raw = exchange(a.host, a.port, fr, a.wait)
        r = parse(raw)
        print("\n== %s CID2=0x%02X [%s]" % (READ_CIDS[cid], cid, a.port_type))
        print("   TX %s" % fr.decode("latin-1").strip())
        if not r:
            print("   RX SILENCE (нет/невалидный ответ)"); continue
        print("   RX %s" % raw.decode("latin-1").strip())
        print("   RTN=%02X chk_ok=%s info=%dB" % (r["rtn"], r["chk_ok"], len(r["info"])))
        if r["rtn"] != 0:
            continue
        if cid == 0x42 and len(r["info"]) >= 67:
            d = decode_telemetry(r["info"])
            print("   cells:", ", ".join("%.3f" % x for x in d["cells_V"]))
            print("   temps:", ", ".join("%.1f" % x for x in d["temps_C"]))
            for k in ("current_A", "total_V", "remain_Ah", "totalCap_Ah", "soc_%",
                      "ratedCap_Ah", "cycles", "soh_%", "bus_V", "tempdrift_A",
                      "zeroCurrent_A", "chargeEnergy_kWh", "dischargeEnergy_kWh"):
                print("   %-18s %s" % (k, d[k]))
        elif cid == 0x47 and len(r["info"]) >= 4:
            decode_params(r["info"])
        elif cid == 0x4D and len(r["info"]) == 7:
            y, mo, d_, hh, mm, ss = (r["info"][0] << 8) | r["info"][1], *r["info"][2:]
            print("   time: %04d-%02d-%02d %02d:%02d:%02d" % (y, mo, d_, hh, mm, ss))
        elif cid == 0xA4:
            print("   SN:", r["info"].decode("latin-1", "replace"))
        else:
            print("   INFO %s" % r["info"].hex(" "))


if __name__ == "__main__":
    main()
