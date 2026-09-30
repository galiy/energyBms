import asyncio, struct
from bleak import BleakScanner, BleakClient

MAC="28:xx:xx:xx:xx:xx"  # замените на MAC вашего BMS
NAME="BP00"

def crc16(data):
    crc=0
    for b in data:
        for _ in range(8):
            if crc & 0x8000: crc=((crc<<1)^0x1021)&0xFFFF
            else: crc=(crc<<1)&0xFFFF
            if b & 0x80: crc ^= 0x1021
            b=(b<<1)&0xFF
    return crc&0xFFFF

def build(cmd1, payload=b'', addr=0):
    body=bytes([0x10,addr,0x46,cmd1])+struct.pack('>H',len(payload))+payload
    return bytes([0x7E])+body+struct.pack('>H',crc16(body))+bytes([0x0D])

def frames(buf):
    out=[]; i=0
    while True:
        s=buf.find(b'\x7e',i)
        if s<0: break
        e=buf.find(b'\x0d',s+1)
        if e<0: break
        fr=buf[s:e+1]
        if len(fr)>=9:
            out.append((fr, crc16(fr[1:-3])==((fr[-3]<<8)|fr[-2])))
        i=e+1
    return out

def u16(b,o): return (b[o]<<8)|b[o+1]

def decode_battery(p):
    if len(p)<4: return
    print("   dataflag=%d slaveNo=%d batterynum=%d"%(p[0],p[1],p[2]))
    n=p[2]; o=3; cells=[]
    for _ in range(n):
        if o+1>=len(p): break
        cells.append(u16(p,o)); o+=2
    print("   cells(mV):", cells)
    if o<len(p):
        tn=p[o]; o+=1; print("   tempnum=%d"%tn); temps=[]
        for _ in range(tn):
            if o+1>=len(p): break
            v=u16(p,o); o+=2
            temps.append(round(v*0.1-273.1,1))
        print("   temps(C):", temps)
    print("   rest[%d..]:"%(o), p[o:].hex(' '))

async def main():
    dev=None
    for attempt in range(4):
        print("scan #%d ..."%(attempt+1))
        found=await BleakScanner.discover(timeout=20, return_adv=True)
        for d,adv in found.values():
            if (adv.local_name or "")==NAME or d.address.upper()==MAC:
                dev=d; break
        if dev: break
    if not dev:
        print("BP00 NOT FOUND"); return
    print("device:", dev.address, dev.name)
    async with BleakClient(dev.address, timeout=30) as cl:
        print("connected:", cl.is_connected)
        chars={}
        for s in cl.services:
            for c in s.characteristics:
                chars[c.uuid.lower()]=c.uuid
        print("chars:", list(chars.keys()))
        wr=None; nf=None
        for u in chars:
            if u.startswith("0000ff02"): wr=chars[u]
            if u.startswith("0000ff01"): nf=chars[u]
        print("write=",wr,"notify=",nf)
        for name,cmd,pl in [("BasicInfo",0x51,b''),("ProtocolVer",0x4F,b''),
                            ("Battery",0x61,b'\x00'),("ReadBMSParams",0x47,b'\x00'),
                            ("PacksNum",0x90,b'')]:
            buf=bytearray()
            def cb(_,data): buf.extend(data)
            await cl.start_notify(nf, cb)
            fr=build(cmd,pl,0)
            print("\n== %s cmd=0x%02x  TX %s"%(name,cmd,fr.hex(' ')))
            await cl.write_gatt_char(wr, fr, response=False)
            await asyncio.sleep(4)
            await cl.stop_notify(nf)
            res=frames(bytes(buf))
            if not res:
                print("   RX raw:", bytes(buf).hex(' '))
            for f,ok in res:
                print("   RX",f.hex(' '),"crc_ok=",ok,"len_info=",((f[5]<<8)|f[6]))
                if cmd==0x61 and ok:
                    decode_battery(f[7:7+((f[5]<<8)|f[6])])
asyncio.run(main())
