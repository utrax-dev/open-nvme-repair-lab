"""Read-only query of the empty original controller's configuration table.
No SSD commands, flash writes or bridge RAM writes are implemented here.
"""
import ctypes as C
import hashlib, json, pathlib, struct, sys

matches = []
for p in pathlib.Path('/sys/bus/usb/devices').iterdir():
    try:
        if (p/'idVendor').read_text().strip() == '0781' and (p/'idProduct').read_text().strip() == '55af':
            matches.append(p)
    except (FileNotFoundError, NotADirectoryError):
        pass
if len(matches) != 1 or (matches[0]/'serial').read_text().strip() != sys.argv[1]:
    raise RuntimeError('Expected exactly one matching, explicitly identified empty original SanDisk bridge')
p = matches[0]
raw = (p/'descriptors').read_bytes()
interfaces = []
current = None
off = 0
while off + 2 <= len(raw):
    length, kind = raw[off:off+2]
    if length < 2 or off + length > len(raw):
        raise RuntimeError('Malformed USB descriptor')
    d = raw[off:off+length]
    if kind == 4:
        current = {'number':d[2], 'alt':d[3], 'class':d[5], 'subclass':d[6], 'protocol':d[7], 'endpoints':[]}
        interfaces.append(current)
    if kind == 5 and current is not None and d[3] & 3 == 2:
        current['endpoints'].append(d[2])
    off += length
bot = [i for i in interfaces if (i['class'],i['subclass'],i['protocol']) == (8,6,80)]
if len(bot) != 1:
    raise RuntimeError('Exactly one Bulk-Only Transport interface required')
i = bot[0]
incoming = [e for e in i['endpoints'] if e & 128]
outgoing = [e for e in i['endpoints'] if not e & 128]
if len(incoming) != 1 or len(outgoing) != 1:
    raise RuntimeError('Unexpected endpoint layout')
print(json.dumps({'transport':'BOT', 'interface':i['number'], 'alternate':i['alt'], 'in_endpoint':incoming[0], 'out_endpoint':outgoing[0]}),flush=True)
lib = C.CDLL('libusb-1.0.so.0')
def bind(name, args, rest=C.c_int):
    fn = getattr(lib, name); fn.argtypes = args; fn.restype = rest; return fn
init = bind('libusb_init',[C.POINTER(C.c_void_p)])
open_device = bind('libusb_open_device_with_vid_pid',[C.c_void_p,C.c_uint16,C.c_uint16],C.c_void_p)
claim = bind('libusb_claim_interface',[C.c_void_p,C.c_int])
release = bind('libusb_release_interface',[C.c_void_p,C.c_int])
set_alt = bind('libusb_set_interface_alt_setting',[C.c_void_p,C.c_int,C.c_int])
bulk = bind('libusb_bulk_transfer',[C.c_void_p,C.c_ubyte,C.c_void_p,C.c_int,C.POINTER(C.c_int),C.c_uint])
close = bind('libusb_close',[C.c_void_p],None)
finish = bind('libusb_exit',[C.c_void_p],None)
context = C.c_void_p()
if init(C.byref(context)):
    raise RuntimeError('libusb initialization failed')
handle = open_device(context,0x0781,0x55af)
if not handle:
    finish(context); raise RuntimeError('Could not open matching USB device')
claimed = False
tag = 0
def transfer(endpoint, data_or_size):
    if isinstance(data_or_size,int):
        buf = (C.c_ubyte * data_or_size)(); size=data_or_size
    else:
        buf = C.create_string_buffer(data_or_size);size=len(data_or_size)
    n = C.c_int()
    result = bulk(handle, endpoint, buf, size, C.byref(n), 5000)
    if result:
        raise RuntimeError(f'USB transfer failed: libusb {result}, transferred {n.value}')
    return bytes(buf[:n.value])


RANGES=[('vendor-init-enabled',0x0c00,1),('vendor-init-table',0x0337,300),
        ('vendor-init-config-window',0x8040,304),('command-buffer-pointer',0x0815,3)]
ALLOWED={bytes.fromhex('e4 06 50 07 f0 00'):6}
for name,address,length in RANGES:
    for offset in range(0,length,128):
        a=address+offset;n=min(128,length-offset)
        ALLOWED[bytes([0xe4,n,0x50,a>>8,a&255,0])]=n
def query(cdb):
    global tag
    size = ALLOWED[cdb]  # No caller-supplied or write commands allowed.
    tag += 1
    wrapper = struct.pack('<4sIIBBB16s',b'USBC',tag,size,0x80,0,len(cdb),cdb)
    if len(transfer(outgoing[0],wrapper)) != 31:
        raise RuntimeError('Incomplete command wrapper')
    data = transfer(incoming[0],size)
    if len(data) == 13 and data[:4] == b'USBS':
        raise RuntimeError('Device returned command status instead of query data')
    status = transfer(incoming[0],13)
    if len(status) != 13:
        raise RuntimeError('Missing command status wrapper')
    signature, echoed, residue, code = struct.unpack('<4sIIB',status)
    if signature != b'USBS' or echoed != tag or code != 0 or residue != 0 or len(data) != size:
        raise RuntimeError(f'Query not completed successfully: status={code}, residue={residue}, received={len(data)}')
    return data

try:
    if claim(handle,i['number']):raise RuntimeError('Cannot claim unbound original controller')
    claimed=True
    if set_alt(handle,i['number'],i['alt']):raise RuntimeError('Cannot select original BOT interface')
    version=query(bytes.fromhex('e4 06 50 07 f0 00'))
    if version!=bytes.fromhex('19062091e48a'):raise RuntimeError('Original firmware mismatch')
    print(json.dumps({'original_bridge_firmware':version.hex(),'device':'original controller serial verified; operator must verify physical SSD absence'}),flush=True)
    for name,address,length in RANGES:
        data=b''
        for offset in range(0,length,128):
            a=address+offset;n=min(128,length-offset)
            data+=query(bytes([0xe4,n,0x50,a>>8,a&255,0]))
        path=pathlib.Path(__file__).with_name('private-original-'+name+'.bin')
        import os
        fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,'wb') as stream:stream.write(data)
        print(json.dumps({'read':name,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}),flush=True)
finally:
    if claimed:release(handle,i['number'])
    close(handle);finish(context)
