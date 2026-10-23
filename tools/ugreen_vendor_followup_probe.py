"""Bounded factory 0xFE probe or exact original profile-4 replay.

The opcodes have undocumented semantics. This is not a certified read-only
interface or a speed fix. No security, format or firmware commands exist here.
The explicitly selected replay mode sends exactly two factory 0xFD frames
and their 0xFE followups; their meaning and persistence remain undocumented.
Requires the isolated Linux USB diagnostic connection and physical reconnect.
"""
import ctypes as C
import hashlib, json, pathlib, struct, sys, time
from vendor_profile_probe_safety import ProbeSequence, FactoryProfile4Replay, validate_evidence, standard_read_frame, completion_result, verify_profile4_readback

if len(sys.argv)!=4 or sys.argv[3] not in ("--probe-factory-followups", "--replay-original-profile4", "--check-controller-reset-persistence"):
    raise RuntimeError("Exact factory-followup probe mode and both target serials required")
reset_persistence_requested=sys.argv[3]=='--check-controller-reset-persistence'
replay_requested=sys.argv[3] in ('--replay-original-profile4','--check-controller-reset-persistence')

matches = []
for p in pathlib.Path('/sys/bus/usb/devices').iterdir():
    try:
        if (p/'idVendor').read_text().strip() == '174c' and (p/'idProduct').read_text().strip() == '2463':
            matches.append(p)
    except (FileNotFoundError, NotADirectoryError):
        pass
if len(matches) != 1 or (matches[0]/'serial').read_text().strip() != sys.argv[1]:
    raise RuntimeError('Expected exactly one matching, explicitly identified UGREEN bridge')
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
handle = open_device(context,0x174c,0x2463)
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

ALLOWED = {
    bytes.fromhex('e6 06 00 01 00 00 00 00 00 00 00 00 00 00 00 00'):4096,
    bytes.fromhex('e4 06 50 07 f0 00'):6,
    bytes.fromhex('e4 40 50 b0 00 00'):64,
}
for address, size in [(0xb000,128),(0xb080,128),(0xb100,128),(0xb180,128),(0xb250,48)]:
    ALLOWED[bytes([0xe4,size,0x50,address>>8,address&255,0])]=size
ALLOWED[bytes.fromhex('e2 50 00 00 ff 00')]=0xff00
ALLOWED[bytes.fromhex('e2 d0 00 00 81 00')]=0x8100
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

def xread(address, length):
    if not ((0xb200 <= address and address+length <= 0xb300 or 0xa000 <= address and address+length <= 0xa040 or 0xf000 <= address and address+length <= 0xfc00) and 1 <= length <= 128):
        raise RuntimeError('PCIe diagnostic register range required')
    cdb=bytes([0xe4,length,0x50,address>>8,address&255,0])
    ALLOWED[cdb]=length
    return query(cdb)

def xwrite(address, value):
    global tag
    # Only the bridge's documented PCIe request engine; no NVMe memory writes.
    if not (0xb210 <= address <= 0xb223 or address in (0xb254,0xb296) or 0xa000<=address<0xa040 or 0xf000<=address<0xfc00):
        raise RuntimeError('Write outside volatile PCIe request engine rejected')
    if address == 0xb254 and value != 0x0f:
        raise RuntimeError('Unexpected PCIe request trigger')
    if address == 0xb296 and value not in (1,2,4,7):
        raise RuntimeError('Unexpected PCIe status control')
    cdb=bytes([0xe5,value,0x50,address>>8,address&255,0])
    tag+=1
    cbw=struct.pack('<4sIIBBB16s',b'USBC',tag,0,0,0,6,cdb)
    if len(transfer(outgoing[0],cbw)) != 31:
        raise RuntimeError('Incomplete diagnostic register command')
    csw=transfer(incoming[0],13)
    if len(csw)!=13 or struct.unpack('<4sIIB',csw)!=(b'USBS',tag,0,0):
        raise RuntimeError('Diagnostic register write not acknowledged')

def pcie_read(fmt,address):
    if fmt not in (0,4,5):
        raise RuntimeError('Only PCIe configuration/memory READ requests allowed')
    # Stock bank 1 AE7E sets PCIe request tag 0x20 in B216.
    header=struct.pack('>III',(fmt<<24)|1,0x200f,address)
    for offset,value in enumerate(header):xwrite(0xb210+offset,value)
    if xread(0xb210,12)!=header:
        raise RuntimeError('PCIe request header readback mismatch; no request triggered')
    for flag in (1,2,4):xwrite(0xb296,flag)
    xwrite(0xb254,15)
    deadline=time.monotonic()+3
    while not xread(0xb296,1)[0]&4:
        if time.monotonic()>deadline:raise RuntimeError('PCIe engine ready timeout')
        time.sleep(.01)
    xwrite(0xb296,4)
    while True:
        status=xread(0xb296,1)[0]
        if status&1:raise RuntimeError('PCIe completion timeout/error')
        if status&2:break
        if time.monotonic()>deadline:raise RuntimeError('No PCIe completion')
        time.sleep(.01)
    completion=xread(0xb224,12)
    value=int.from_bytes(xread(0xb220,4),'big')
    xwrite(0xb296,2)
    # Callers report meaningful state changes; avoid logging every poll.
    return value

def ram_read(address,length):
    return b''.join(xread(address+offset,min(128,length-offset)) for offset in range(0,length,128))

def ram_write(address,data):
    if not (0xa000<=address and address+len(data)<=0xa040 or 0xf000<=address and address+len(data)<=0xfc00):
        raise RuntimeError('Diagnostic RAM range required')
    for offset,value in enumerate(data):xwrite(address+offset,value)
    if ram_read(address,len(data))!=data:
        raise RuntimeError('RAM readback verification failed')

NVME_BASE=0xa00000
def reg_read(offset):return pcie_read(0,NVME_BASE+offset)
def reg_write(offset,value):
    if offset not in (0x0c,0x10,0x14,0x24,0x28,0x2c,0x30,0x34,0x1000,0x1004):
        raise RuntimeError('Only controller/admin-queue registers may be written')
    # PCIe payload is staged in big-endian write order, as stock firmware does.
    # DATA-register reads expose the opposite byte lanes: a raw 11 22 33 44
    # write reads back 44 33 22 11. Header registers read in normal order.
    for n,v in enumerate(value.to_bytes(4,'big')):xwrite(0xb220+n,v)
    header=struct.pack('>III',0x40000001,0x200f,NVME_BASE+offset)
    for n,v in enumerate(header):xwrite(0xb210+n,v)
    actual_header=xread(0xb210,12)
    actual_data=xread(0xb220,4)
    if actual_header!=header or actual_data!=value.to_bytes(4,'little'):
        raise RuntimeError('Register request verification failed: header='+actual_header.hex()+' expected_header='+header.hex()+' data='+actual_data.hex()+' expected_data='+value.to_bytes(4,'big').hex())
    for flag in (1,2,4):xwrite(0xb296,flag)
    xwrite(0xb254,15)
    deadline=time.monotonic()+3
    while not xread(0xb296,1)[0]&4:
        if time.monotonic()>deadline:raise RuntimeError('Register write transport timeout')
        time.sleep(.01)
    xwrite(0xb296,4)
    if offset in (0x14,0x24,0x28,0x2c,0x30,0x34):
        observed=reg_read(offset)
        # Disabling EN resets other CC fields on this controller. Check EN,
        # then use CSTS.RDY for the reset handshake, rather than stale fields.
        accepted = not (observed&1) if offset==0x14 and not (value&1) else observed==value
        if not accepted:
            raise RuntimeError('NVMe register readback differs: offset='+hex(offset)+' requested='+hex(value)+' observed='+hex(observed))

def wait_ready(wanted):
    deadline=time.monotonic()+12
    last=None
    while True:
        status=reg_read(0x1c)
        if status!=last:print(json.dumps({'controller_status':hex(status),'waiting_for_ready':wanted}),flush=True);last=status
        if status&2:raise RuntimeError('NVMe controller fatal status; stopping')
        if bool(status&1)==wanted:return
        if time.monotonic()>deadline:raise RuntimeError('Controller ready timeout')
        time.sleep(.02)

sq_tail=0
cq_head=0
cq_phase=1
command_id=0xf000
sequence=FactoryProfile4Replay() if replay_requested else ProbeSequence()
pending_submission=False

def submit(frame, data_size=0):
    global sq_tail,cq_head,cq_phase,pending_submission
    if len(frame)!=64 or data_size not in (0,512,1024):
        raise RuntimeError('Unexpected bounded submission')
    dw=struct.unpack('<16I',frame)
    cid=dw[0]>>16
    ram_write(0xf000+sq_tail*64,frame)
    if data_size:ram_write(0xf400,b'\xa5'*data_size)
    sq_tail=(sq_tail+1)%4
    pending_submission=True
    reg_write(0x1000,sq_tail)
    deadline=time.monotonic()+8
    while True:
        cqe=ram_read(0xa000+cq_head*16,16)
        words=struct.unpack('<IIHHHH',cqe)
        if words[-1]&1==cq_phase and words[-2]==cid:
            break
        if time.monotonic()>deadline:
            raise RuntimeError('Submission completion unknown; no automatic retry')
        time.sleep(.005)
    if words[1]!=0 or words[2]>=4 or words[3]!=0:
        raise RuntimeError('Completion queue identity invalid; outcome remains unknown')
    # An otherwise valid matching nonzero status is a known rejection.
    if words[-1]>>1:
        pending_submission=False
    result=completion_result(cqe,cid,cq_phase)
    pending_submission=False
    cq_head=(cq_head+1)%4
    if cq_head==0:cq_phase^=1
    reg_write(0x1004,cq_head)
    print(json.dumps({'opcode':hex(dw[0]&255),'cdw10':hex(dw[10]),'cdw11':hex(dw[11]),
                      'status':0,'completion_dword0':result}),flush=True)
    return result,ram_read(0xf400,data_size) if data_size else b''

def standard_read(opcode,cdw10,size=0):
    global command_id
    command_id+=1
    return submit(standard_read_frame(opcode,cdw10,size,command_id),size)

def rebuild_diagnostic_queue():
    global sq_tail,cq_head,cq_phase
    reg_write(0x14,original[0x14]&~1)
    wait_ready(False)
    ram_write(0xf000,b'\0'*256)
    ram_write(0xa000,b'\0'*64)
    for offset,value in [(0x24,0x30003),(0x28,0x200000),(0x2c,0),(0x30,0x820000),(0x34,0)]:
        reg_write(offset,value)
    sq_tail=0
    cq_head=0
    cq_phase=1
    reg_write(0x14,original[0x14]|1)
    wait_ready(True)

def health():
    _,data=standard_read(2,0x007f0002,512)
    result={'critical_warning':data[0],
            'temperature_c':int.from_bytes(data[1:3],'little')-273.15,
            'available_spare':data[3],'percentage_used':data[5],
            'media_errors':int.from_bytes(data[160:176],'little'),
            'error_log_count':int.from_bytes(data[176:192],'little')}
    print(json.dumps({'smart':result}),flush=True)
    if result['critical_warning'] or result['temperature_c']>=65 or result['media_errors']:
        raise RuntimeError('Health/temperature guard stopped the experiment')
    return result

restore_needed=False
original={}
try:
    if claim(handle,i['number']):raise RuntimeError('Cannot claim unbound diagnostic interface')
    claimed=True
    if set_alt(handle,i['number'],i['alt']):raise RuntimeError('Cannot select BOT alternate')
    identity=query(next(iter(ALLOWED)))
    model=identity[24:64].decode('ascii').strip()
    serial=identity[4:24].decode('ascii').strip()
    firmware=identity[64:72].decode('ascii').strip()
    if (model,serial,firmware)!=('WD_BLACK SN850XE 4000GB',sys.argv[2],'624131EX'):
        raise RuntimeError('Fresh SSD identity or tested firmware mismatch')
    if query(bytes.fromhex('e4 06 50 07 f0 00'))!=bytes.fromhex('250717850000'):
        raise RuntimeError('Unexpected UGREEN bridge firmware')
    base=pathlib.Path(__file__).parent
    evidence=json.loads((base/'original-vendor-init-table-decoded.json').read_text())
    table=(base/'private-original-vendor-init-table.bin').read_bytes()
    flag=(base/'private-original-vendor-init-enabled.bin').read_bytes()
    print(json.dumps({'model':model,'firmware':firmware,'identity':'fresh verified',
                      'scope':'exact original factory profile 4 replay' if replay_requested else 'two exact factory 0xFE followups; no 0xFD, reset, format or firmware commands'}),flush=True)
    if reg_read(8)!=0x10400 or reg_read(0x1c)!=1:
        raise RuntimeError('NVMe endpoint not in expected ready state')
    original={o:reg_read(o) for o in [0x0c,0x14,0x24,0x28,0x2c,0x30,0x34]}
    if original[0x14]!=0x460001:raise RuntimeError('Untested controller configuration')
    restore_needed=True
    reg_write(0x0c,0xffffffff)
    rebuild_diagnostic_queue()
    _,effects=standard_read(2,0x00ff0005,1024)
    validate_evidence(table,flag,evidence.get('original_bridge_firmware'),effects)
    health()
    power,_=standard_read(0x0a,2)
    print(json.dumps({'standard_power_feature':power}),flush=True)
    results=[]
    for index in (range(4) if replay_requested else (1,2)):
        command_id+=1
        frame=sequence.take(index,command_id)
        result,_=submit(frame)
        words=struct.unpack('<16I',frame)
        results.append({'opcode':hex(words[0]&255),'parameter':words[10],
                        'value':words[11],'completion_dword0':result})
    health()
    if replay_requested:
        verify_profile4_readback(results)
    if reset_persistence_requested:
        print('Factory values verified; resetting only NVMe CC.EN in the same USB attachment.',flush=True)
        rebuild_diagnostic_queue()
        readback=ProbeSequence()
        after_reset=[]
        for parameter in (1,2):
            command_id+=1
            result,_=submit(readback.take(parameter,command_id))
            after_reset.append({'parameter':parameter,'completion_dword0':result})
        print(json.dumps({'after_controller_reset':after_reset,
                          'physical_usb_reconnect_between_write_and_readback':False}),flush=True)
        health()
    print(json.dumps({'factory_vendor_results':results,'meaning_confirmed':False,
                      'no_0xfd_sent':not replay_requested,'speed_fix_proven':False}),flush=True)
finally:
    try:
        if restore_needed and pending_submission:
            print('COMMAND OUTCOME UNKNOWN: preserving controller state; do not reconnect until reviewed.',flush=True)
        elif restore_needed:
            reg_write(0x14,original[0x14]&~1)
            wait_ready(False)
            for offset in (0x24,0x28,0x2c,0x30,0x34):reg_write(offset,original[offset])
            reg_write(0x14,original[0x14])
            wait_ready(True)
            reg_write(0x10,0xffffffff)
            if original[0x0c]:reg_write(0x0c,original[0x0c])
            if {o:reg_read(o) for o in original}!=original:
                raise RuntimeError('Original controller registers did not restore exactly')
            print('Original controller registers restored and verified. Reconnect required for normal I/O.',flush=True)
    finally:
        if claimed:release(handle,i['number'])
        close(handle);finish(context)
