"""Experimental bounded OPAL access over the tested stock bridge.

Changes volatile bridge RAM, PCIe request registers and NVMe admin queues.
Default operations are Properties, read sessions, allowlisted GETs and EndSession.
Optional credential checks permit one exact firmware-derived challenge or one
fresh factory-MSID check. No user-supplied password guesses are accepted.
The separate --erase-secondary-and-reset-opal mode sends AdminSP.Revert once,
only after fresh SSD identification, explicit private approval and SID auth.
That mode destroys all secondary SSD data. It never flashes firmware.
An authentication failure can increment the drive's authentication retry counter.
Restores saved registers except when an erasing reset's outcome is unknown;
then preserves the live controller state to avoid interrupting completion.
Physical reconnect is otherwise required for normal stock I/O queues.
Linux USB interface must be unbound from both UAS and usb-storage before use.
"""
import ctypes as C
import hashlib, json, pathlib, struct, sys, time
import tcg_ro as tcg
from reset_safety import validate_authorization, save_private_completion

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
def admin_read(opcode,cdw10,cdw11=0,data_size=0,data_out=None):
    global sq_tail,cq_head,cq_phase,command_id
    if opcode==0x81:
        if cdw10!=0x017ffe00 or data_out is None or data_size!=len(data_out):
            raise RuntimeError('Only the fixed TCG diagnostic channel may send data')
        validate_outbound(data_out)
    elif not ((opcode==0x0a and cdw10 in (2,0x0c)) or (opcode==0x82 and cdw10 in (0,0x01000100,0x017ffe00))):
        raise RuntimeError('NVMe command outside diagnostic allowlist')
    if not (0<=data_size<=2048) or cdw11 not in (0,data_size):
        raise RuntimeError('Diagnostic buffer/length rejected')
    command_id+=1
    dw=[0]*16
    dw[0]=opcode|(command_id<<16)
    dw[6]=0x200400 if data_size else 0
    dw[10]=cdw10;dw[11]=cdw11
    ram_write(0xf000+sq_tail*64,struct.pack('<16I',*dw))
    if data_size:ram_write(0xf400,data_out if data_out is not None else b'\xa5'*data_size)
    sq_tail=(sq_tail+1)%4
    reg_write(0x1000,sq_tail)
    deadline=time.monotonic()+(120 if globals().get('erase_sent',False) else 5)
    while True:
        completion=ram_read(0xa000+cq_head*16,16)
        result,reserved,sqhead,sqid,cid,status=struct.unpack('<IIHHHH',completion)
        if status&1==cq_phase and cid==command_id:break
        if time.monotonic()>deadline:
            raise RuntimeError('NVMe completion not verified; last CQE='+completion.hex())
        time.sleep(.005)
    cq_head=(cq_head+1)%4
    if cq_head==0:cq_phase^=1
    reg_write(0x1004,cq_head)
    decoded_status=status>>1
    print(json.dumps({'nvme_diagnostic_opcode':hex(opcode),'cdw10':hex(cdw10),'cid':cid,'sqid':sqid,'sqhead':sqhead,'status':hex(decoded_status),'result':hex(result)}),flush=True)
    if decoded_status:raise RuntimeError('NVMe command failed; result not interpreted')
    return result,ram_read(0xf400,data_size) if data_size and data_out is None else b''

factory_msid=None
authentication_attempted=False
check_factory_admin1='--factory-admin1-check' in sys.argv
check_firmware_admin1='--firmware-admin1-check' in sys.argv
erase_requested='--erase-secondary-and-reset-opal' in sys.argv
check_firmware_sid='--firmware-sid-check' in sys.argv or erase_requested
erase_sent=False
erase_completed=False
authenticated_sid_session=None
if erase_requested:
    if len(sys.argv)!=5 or sys.argv[3]!='--query-anonymous':
        raise RuntimeError('An erasing reset requires a fresh bridge Identify, not a continuation')
    authorization_path=pathlib.Path(__file__).with_name('private-reset-authorization.json')
    if authorization_path.stat().st_mode&0o077:raise RuntimeError('Authorization file must be private')
    authorization=json.loads(authorization_path.read_text())
    validate_authorization(authorization,sys.argv[1],sys.argv[2],'624131EX',time.time())
firmware_candidate=None
if check_firmware_admin1 or check_firmware_sid:
    candidate_path=pathlib.Path(__file__).with_name('private-firmware-auth-challenge.bin')
    if candidate_path.stat().st_mode&0o077:
        raise RuntimeError('Firmware challenge file must be private')
    firmware_candidate=candidate_path.read_bytes()
    if len(firmware_candidate)!=32:raise RuntimeError('Unexpected challenge length')

def validate_outbound(payload):
    global authentication_attempted,erase_sent
    decoded=tcg.response(payload)
    if decoded['pending']:raise RuntimeError('Empty TCG request rejected')
    length=struct.unpack_from('>I',payload,52)[0]
    body=payload[56:56+length]
    if tcg.packet(body,hsn=decoded['hsn'],tsn=decoded['tsn'],factory_msid=factory_msid,firmware_candidate=firmware_candidate,allow_factory_reset=erase_requested)!=payload:
        raise RuntimeError('TCG request is not an exact allowlisted encoding')
    if body==tcg.factory_reset():
        if not erase_requested or erase_sent or authenticated_sid_session!=(decoded['hsn'],decoded['tsn']):
            raise RuntimeError('Erasing request lacks one-time authenticated SID authorization')
        erase_sent=True
    if firmware_candidate is not None:
        for sp,authority,enabled in ((tcg.LOCKING_SP,tcg.ADMIN1,check_firmware_admin1),(tcg.ADMIN_SP,tcg.SID,check_firmware_sid)):
            if body==tcg.start_credential_session(sp,authority,firmware_candidate):
                if not enabled or authentication_attempted or decoded['hsn'] or decoded['tsn']:
                    raise RuntimeError('Firmware authentication check disabled or already used')
                authentication_attempted=True
    if factory_msid is not None and body==tcg.authenticate_factory_admin1(factory_msid):
        if not check_factory_admin1 or authentication_attempted or decoded['hsn']!=105:
            raise RuntimeError('Authentication check disabled or already used')
        authentication_attempted=True

def exchange(body,hsn=0,tsn=0):
    payload=tcg.packet(body,hsn=hsn,tsn=tsn,factory_msid=factory_msid,firmware_candidate=firmware_candidate,allow_factory_reset=erase_requested)
    admin_read(0x81,0x017ffe00,len(payload),len(payload),payload)
    deadline=time.monotonic()+(120 if body==tcg.factory_reset() else 12)
    while True:
        _,data=admin_read(0x82,0x017ffe00,2048,2048)
        answer=tcg.response(data)
        if answer['minimum']>2048:raise RuntimeError('TCG response exceeds bounded buffer')
        if not answer['pending']:
            if answer['outstanding']:raise RuntimeError('Multipart TCG response not supported')
            return answer
        if time.monotonic()>deadline:raise RuntimeError('TCG response deadline')
        time.sleep(.025)

def named_columns(answer):
    if answer['status']:raise RuntimeError('Required table GET was rejected')
    found={};tok=answer['tokens']
    for index in range(len(tok)-3):
        if tok[index]==tcg.SN and isinstance(tok[index+1],int) and tok[index+3]==tcg.EN:
            found[tok[index+1]]=tok[index+2]
    return found

def range_audit(hsn,tsn):
    info=named_columns(exchange(tcg.get_columns(tcg.LOCKING_INFO,4,4),hsn,tsn))
    count=info.get(4)
    if not isinstance(count,int) or not 0<=count<=16:
        raise RuntimeError('Locking range count outside bounded audit')
    print(json.dumps({'maximum_additional_locking_ranges':count}),flush=True)
    ranges=[]
    for number in range(count+1):
        row=named_columns(exchange(tcg.get_columns(tcg.range_uid(number),3,8),hsn,tsn))
        if set(row)!={3,4,5,6,7,8} or any(not isinstance(value,int) for value in row.values()):
            raise RuntimeError('Incomplete authenticated locking range result')
        item={'range':number,'start':row[3],'length':row[4],'read_lock_enabled':row[5],
              'write_lock_enabled':row[6],'read_locked':row[7],'write_locked':row[8]}
        ranges.append(item)
        print(json.dumps({'locking_range_audit':item}),flush=True)
    safe=all(all(row[key]==0 for key in ('start','length','read_lock_enabled','write_lock_enabled','read_locked','write_locked')) for row in ranges)
    result={'all_ranges_unconfigured_and_unlocked':safe,'ranges':ranges}
    pathlib.Path('/tmp/ugreen-locking-range-audit.json').write_text(json.dumps(result))
    print(json.dumps({'all_ranges_unconfigured_and_unlocked':safe}),flush=True)
    return result

def session_get(sp,requests):
    global factory_msid,authenticated_sid_session,erase_completed
    credential_session=sp==tcg.LOCKING_SP and check_firmware_admin1 or sp==tcg.ADMIN_SP and check_firmware_sid
    authority=tcg.ADMIN1 if sp==tcg.LOCKING_SP else tcg.SID
    request=tcg.start_credential_session(sp,authority,firmware_candidate) if credential_session else tcg.start_session(sp)
    answer=exchange(request)
    print(json.dumps({'session_sp':'AdminSP' if sp==tcg.ADMIN_SP else 'LockingSP',
                      'authority':('Admin1' if sp==tcg.LOCKING_SP else 'SID')+', firmware candidate' if credential_session else 'anonymous',
                      'method_status':answer['status']}),flush=True)
    if answer['status']:
        if erase_requested:raise RuntimeError('Authenticated SID session failed; reset not sent')
        return
    tok=answer['tokens']
    if len(tok)<8 or tok[0]!=tcg.CALL or tok[3]!=tcg.SL or tok[4]!=105 or not isinstance(tok[5],int):
        raise RuntimeError('StartSession result does not identify the requested host session')
    hsn,tsn=tok[4],tok[5]
    if credential_session and sp==tcg.ADMIN_SP:authenticated_sid_session=(hsn,tsn)
    try:
        if sp==tcg.LOCKING_SP and check_factory_admin1:
            if factory_msid is None:raise RuntimeError('Factory value not read; no authentication attempt')
            auth=exchange(tcg.authenticate_factory_admin1(factory_msid),hsn,tsn)
            success=auth['status']==0 and auth['tokens'][:3]==[tcg.SL,1,tcg.EL]
            print(json.dumps({'factory_admin1_authentication':'accepted' if success else 'not accepted',
                              'method_status':auth['status'],'attempt_count':1}),flush=True)
        for name,uid,first,last in requests:
            answer=exchange(tcg.get_columns(uid,first,last),hsn,tsn)
            item={'table_get':name,'authenticated':credential_session,'method_status':answer['status']}
            if answer['status']==0:
                named={}
                tok=answer['tokens']
                for index in range(len(tok)-3):
                    if tok[index]==tcg.SN and isinstance(tok[index+1],int) and tok[index+3]==tcg.EN:
                        named[tok[index+1]]=tok[index+2]
                if name=='factory_MSID':
                    value=named.get(3)
                    item.update(value_read=isinstance(value,bytes),length=len(value) if isinstance(value,bytes) else None,
                                credential_handling='not logged or saved')
                    if check_factory_admin1:
                        if not isinstance(value,bytes) or len(value)!=32:
                            raise RuntimeError('Factory value has unexpected encoding')
                        factory_msid=value
                    # Do not emit raw tokens, response buffers, or the factory credential.
                    del value
                else:
                    if any(not isinstance(v,int) for v in named.values()):
                        raise RuntimeError('Unexpected diagnostic field encoding')
                    item['columns']=named
            print(json.dumps(item),flush=True)
        if credential_session and sp==tcg.LOCKING_SP:
            range_audit(hsn,tsn)
        if erase_requested:
            if not credential_session or sp!=tcg.ADMIN_SP:raise RuntimeError('SID session required for erasing reset')
            print('Explicitly authorized secondary SSD factory reset: sending AdminSP.Revert once.',flush=True)
            reset=exchange(tcg.factory_reset(),hsn,tsn)
            print(json.dumps({'factory_reset_method_status':reset['status']}),flush=True)
            if reset['status']:raise RuntimeError('Factory reset not accepted; no automatic retry')
            # Successful Revert aborts its own TCG session. Do not send EndSession.
            print('Factory reset accepted. Awaiting inactive/unlocked Discovery0 state.',flush=True)
            deadline=time.monotonic()+120
            while True:
                _,discovery=admin_read(0x82,0x01000100,512,512)
                total=int.from_bytes(discovery[:4],'big')+4
                if not 48<=total<=len(discovery):raise RuntimeError('Invalid post-reset discovery length')
                pos=48;locking=None
                while pos<total:
                    if pos+4>total:raise RuntimeError('Truncated post-reset feature header')
                    kind=int.from_bytes(discovery[pos:pos+2],'big');length=discovery[pos+3]
                    if pos+4+length>total:raise RuntimeError('Truncated post-reset feature')
                    if kind==2 and length:locking=discovery[pos+4]
                    pos+=4+length
                if locking is None:raise RuntimeError('Post-reset locking feature absent')
                print(json.dumps({'post_reset_locking_enabled':bool(locking&2),'post_reset_locked':bool(locking&4)}),flush=True)
                if not locking&6:
                    # Avoid interrupting background completion immediately after a TCG revert.
                    time.sleep(10)
                    erase_completed=True
                    proof={'target_usb_serial':sys.argv[1],'target_ssd_serial':sys.argv[2],
                           'model':model,'firmware':firmware,'completed_at_unix':time.time(),
                           'reset_method_status':0,'locking_enabled':False,'locked':False}
                    proof_path=pathlib.Path(__file__).with_name('private-reset-result.json')
                    save_private_completion(proof_path,proof)
                    break
                if time.monotonic()>deadline:raise RuntimeError('Post-reset locking state did not settle')
                time.sleep(.5)
    finally:
        if not erase_sent:
            ended=exchange(tcg.EOS,hsn,tsn)
            if ended['tokens']!=[tcg.EOS]:raise RuntimeError('Session did not close normally')
            print('TCG session closed.',flush=True)

original=None
restore_needed=False
try:
    if len(sys.argv) not in (4,5) or sys.argv[3] not in ('--query-anonymous','--same-attachment-retry'):
        raise RuntimeError('Explicit diagnostic mode is required')
    if len(sys.argv)==5 and sys.argv[4] not in ('--factory-admin1-check','--firmware-admin1-check','--firmware-sid-check','--erase-secondary-and-reset-opal'):
        raise RuntimeError('Unknown diagnostic option')
    if claim(handle,i['number']):raise RuntimeError('Cannot claim unbound diagnostic interface')
    claimed=True
    if set_alt(handle,i['number'],i['alt']):raise RuntimeError('Cannot select BOT alternate')
    if sys.argv[3]=='--query-anonymous':
        identity=query(next(iter(ALLOWED)))
        model=identity[24:64].decode('ascii').strip()
        serial=identity[4:24].decode('ascii').strip()
        firmware=identity[64:72].decode('ascii').strip()
        if (model,serial,firmware)!=('WD_BLACK SN850XE 4000GB',sys.argv[2],'624131EX'):
            raise RuntimeError('SSD identity or tested firmware mismatch')
        identity_note='fresh Identify Controller verified'
    else:
        # Private lab continuation only: same still-attached USB device was
        # positively identified by the immediately preceding completed query.
        # Stock bridge queue cursors require a physical replug after restore,
        # so its E6 Identify cannot be reused between these two probes.
        model,firmware='WD_BLACK SN850XE 4000GB','624131EX'
        identity_note='previous query verified SSD; same serial-verified USB attachment; no fresh E6 Identify'
    bridge=query(bytes.fromhex('e4 06 50 07 f0 00'))
    if bridge!=bytes.fromhex('250717850000'):raise RuntimeError('Unexpected bridge firmware')
    print(json.dumps({'model':model,'firmware':firmware,'identity':identity_note,'bridge_firmware':bridge.hex()}),flush=True)
    if reg_read(8)!=0x10400 or reg_read(0x1c)!=1:
        raise RuntimeError('NVMe endpoint not in expected ready state')
    original={o:reg_read(o) for o in [0x0c,0x14,0x24,0x28,0x2c,0x30,0x34]}
    if original[0x14]!=0x460001:raise RuntimeError('Untested controller configuration')
    pathlib.Path('/tmp/ugreen-original-controller-registers.json').write_text(json.dumps(original))
    restore_needed=True
    reg_write(0x0c,0xffffffff)
    reg_write(0x14,original[0x14]&~1)
    wait_ready(False)
    ram_write(0xf000,b'\0'*256)
    ram_write(0xa000,b'\0'*64)
    for offset,value in [(0x24,0x30003),(0x28,0x200000),(0x2c,0),(0x30,0x820000),(0x34,0)]:
        reg_write(offset,value)
    reg_write(0x14,original[0x14]|1)
    wait_ready(True)
    _,data=admin_read(0x82,0x01000100,512,512)
    total=int.from_bytes(data[:4],'big')+4
    if not 48<=total<=len(data):raise RuntimeError('Invalid Discovery0 length')
    features={};pos=48
    while pos<total:
        if pos+4>total:raise RuntimeError('Truncated Discovery0 feature header')
        kind=int.from_bytes(data[pos:pos+2],'big');length=data[pos+3]
        if pos+4+length>total:raise RuntimeError('Truncated Discovery0 feature')
        features[kind]=data[pos+4:pos+4+length];pos+=4+length
    if 0x203 not in features or features[0x203][:2]!=b'\x7f\xfe':
        raise RuntimeError('Unexpected Opal ComID; no session requests sent')
    if len(features.get(2,b''))<1 or len(features.get(0x402,b''))<1:
        raise RuntimeError('Required locking/SID state unavailable')
    print(json.dumps({'locking_enabled':bool(features[2][0]&2),'locked':bool(features[2][0]&4),
                      'sid_differs_from_msid':bool(features[0x402][0]&1),
                      'sid_authentication_blocked':bool(features[0x402][0]&2)}),flush=True)
    answer=exchange(tcg.properties())
    print(json.dumps({'properties_method_status':answer['status']}),flush=True)
    if answer['status']:raise RuntimeError('Properties exchange not accepted')
    tok=answer['tokens']
    prop={}
    for index in range(len(tok)-3):
        if tok[index]==tcg.SN and isinstance(tok[index+1],bytes) and isinstance(tok[index+2],int) and tok[index+3]==tcg.EN:
            name=tok[index+1].decode('ascii')
            if name.isalnum() and len(name)<40:prop[name]=tok[index+2]
    print(json.dumps({'tcg_properties':prop}),flush=True)
    if check_firmware_sid:
        session_get(tcg.ADMIN_SP,[('LockingSP_lifecycle',tcg.LOCKING_SP,6,6)])
    elif not check_firmware_admin1:
        session_get(tcg.ADMIN_SP,[('LockingSP_lifecycle',tcg.LOCKING_SP,6,6),('factory_MSID',tcg.MSID,3,3)])
    if not check_firmware_sid:
        session_get(tcg.LOCKING_SP,[('global_locking_range',tcg.GLOBAL_RANGE,3,8)])
    print('Authorized factory-reset flow completed.' if erase_completed else 'Information queries completed. No PIN changes, revert, or erase requested.',flush=True)
finally:
    try:
        if restore_needed and erase_sent and not erase_completed:
            print('RESET OUTCOME UNKNOWN: preserving live controller state; do not power-cycle until readback establishes completion.',flush=True)
        elif restore_needed:
            reg_write(0x14,original[0x14]&~1)
            wait_ready(False)
            for offset in (0x24,0x28,0x2c,0x30,0x34):reg_write(offset,original[offset])
            reg_write(0x14,original[0x14])
            wait_ready(True)
            reg_write(0x10,0xffffffff)
            if original[0x0c]:reg_write(0x0c,original[0x0c])
            observed={o:reg_read(o) for o in original}
            if observed!=original:raise RuntimeError('Original controller registers did not restore exactly')
            print('Original controller registers restored and verified. Physical reconnect needed for normal I/O queues.',flush=True)
    finally:
        if claimed:release(handle,i['number'])
        close(handle);finish(context)
