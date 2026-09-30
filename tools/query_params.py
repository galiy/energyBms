import asyncio, struct
from bleak import BleakScanner, BleakClient
import params_table as PT

MAC="28:xx:xx:xx:xx:xx"  # замените на MAC вашего BMS
NAME="BP00"
def crc16(d):
    c=0
    for b in d:
        for _ in range(8):
            if c&0x8000: c=((c<<1)^0x1021)&0xFFFF
            else: c=(c<<1)&0xFFFF
            if b&0x80: c^=0x1021
            b=(b<<1)&0xFF
    return c&0xFFFF
def build(cmd,pl=b'',addr=0):
    body=bytes([0x10,addr,0x46,cmd])+struct.pack('>H',len(pl))+pl
    return bytes([0x7E])+body+struct.pack('>H',crc16(body))+bytes([0x0D])
def extract(buf):
    out=[]; i=0; n=len(buf)
    while i<n:
        s=buf.find(b'\x7e',i)
        if s<0 or s+7>n: break
        ln=(buf[s+5]<<8)|buf[s+6]; total=10+ln
        if s+total>n: break
        fr=buf[s:s+total]; ok=(fr[-1]==0x0d) and crc16(fr[1:-3])==((fr[-3]<<8)|fr[-2])
        out.append((fr,ok)); i=s+total
    return out

def show_params(p):
    print("  packIndex=%d IntParaCnt=%d"%(p[0],p[1]))
    off=2; IntCnt=p[1]
    def rd(o,nb): return ((p[o]<<8)|p[o+1]) if nb==2 else p[o]
    for i in range(IntCnt):
        idx,nb,name,sc,un=PT.PARAMS[i]; v=rd(off,nb); off+=nb
        val=v*float(sc)
        if un=='℃': val=v*0.1-273.1
        print("    [0x%02X] %-42s = %-10.3f %s"%(idx,name,val,un))
    ByteCnt=p[off]; off+=1; print("  ByteParaCnt=%d"%ByteCnt)
    for i in range(IntCnt,IntCnt+ByteCnt):
        idx,nb,name,sc,un=PT.PARAMS[i]; v=p[off]; off+=1
        print("    [0x%02X] %-42s = %-10.3f %s"%(idx,name,v*float(sc),un))
    BitCnt=p[off]; off+=1; print("  BitGroupCnt=%d"%BitCnt)
    for b in range(BitCnt):
        byte=p[off]; off+=1; names=PT.BITGROUPS.get(b,[])
        on=[names[bit] for bit in range(8) if (byte>>bit)&1]
        print("    [bitgrp %d] %02x -> %s"%(b,byte,", ".join(on) if on else "-"))
    mod=p[off:off+10]; off+=10
    print("  module name:", repr(mod.decode('ascii','replace')))

async def main():
    dev=None
    for a in range(4):
        found=await BleakScanner.discover(timeout=20, return_adv=True)
        for d,adv in found.values():
            if (adv.local_name or "")==NAME or d.address.upper()==MAC: dev=d; break
        if dev: break
    if not dev: print("BP00 NOT FOUND"); return
    print("device:",dev.address,dev.name)
    async with BleakClient(dev.address,timeout=30) as cl:
        wr=nf=None
        for s in cl.services:
            for c in s.characteristics:
                u=c.uuid.lower()
                if u.startswith("0000ff02"): wr=c.uuid
                if u.startswith("0000ff01"): nf=c.uuid
        buf=bytearray()
        await cl.start_notify(nf, lambda _,d: buf.extend(d))
        print("TX ReadBMSParams:", build(0x47,b'\x00').hex(' '))
        await cl.write_gatt_char(wr, build(0x47,b'\x00'), response=False)
        await asyncio.sleep(6)
        await cl.stop_notify(nf)
        print("RX bytes:", len(buf))
        for fr,ok in extract(bytes(buf)):
            print("frame len=%d crc_ok=%s cmd=0x%02x"%(len(fr),ok,fr[3]))
            if ok and fr[3]==0x47:
                show_params(fr[7:-3])
asyncio.run(main())
