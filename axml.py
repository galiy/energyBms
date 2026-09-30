import struct, sys

data = open(sys.argv[1], 'rb').read()

def u16(o): return struct.unpack_from('<H', data, o)[0]
def u32(o): return struct.unpack_from('<I', data, o)[0]

# find string pool chunk
# header: type u16, headersize u16, size u32
chunk_type = u16(0)
chunk_hdr = u16(2)
chunk_size = u32(4)
print("root chunk type %04x hdr %d size %d" % (chunk_type, chunk_hdr, chunk_size))

# string pool at offset 8
sp_off = 8
sp_type = u16(sp_off)
sp_hdr = u16(sp_off+2)
sp_size = u32(sp_off+4)
string_count = u32(sp_off+8)
style_count = u32(sp_off+12)
flags = u32(sp_off+16)
strings_start = u32(sp_off+20)
styles_start = u32(sp_off+24)
is_utf8 = (flags & (1<<8)) != 0
offsets = [u32(sp_off+sp_hdr+i*4) for i in range(string_count)]
strings = []
for o in offsets:
    p = sp_off + strings_start + o
    if is_utf8:
        # u8len (ascii len), then u8 utf16len, then chars
        n = data[p]; p += 1
        # second length byte
        # utf16 length
        lo = data[p]; p += 1
        if lo & 0x80:
            p += 1
        s = data[p:p+n].decode('utf-8', 'replace')
        strings.append(s)
    else:
        n = u16(p); p += 2
        s = data[p:p+n*2].decode('utf-16-le', 'replace')
        strings.append(s)

def s(i):
    if i == 0xFFFFFFFF or i >= len(strings): return None
    return strings[i]

# walk XML chunks
off = sp_off + sp_size
while off < len(data):
    ctype = u16(off)
    chdr = u16(off+2)
    csize = u32(off+4)
    if ctype == 0x0102:  # START_ELEMENT
        line = u32(off+8)
        ns = s(u32(off+16))
        name = s(u32(off+20))
        attr_start = u16(off+24)
        attr_size = u16(off+26)
        attr_count = u16(off+28)
        attrs = []
        ap = off + 16 + attr_start
        for i in range(attr_count):
            a_ns = s(u32(ap+0))
            a_name = s(u32(ap+4))
            a_raw = s(u32(ap+8))
            a_typ = (u32(ap+12) >> 24) & 0xFF
            a_data = u32(ap+16)
            val = a_raw
            if val is None:
                if a_typ == 0x10:
                    val = a_data
                elif a_typ == 0x12:
                    val = bool(a_data)
                elif a_typ == 0x01:
                    val = s(a_data)
                else:
                    val = a_data
            attrs.append((a_name, val, a_typ))
            ap += attr_size
        print("<%s" % name)
        for n, v, t in attrs:
            print("    %s = %r (type %02x)" % (n, v, t))
        print(">")
    elif ctype == 0x0103:
        print("</>")
    off += csize
