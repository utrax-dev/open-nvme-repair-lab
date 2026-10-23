"""Restricted TCG codec; no device I/O.

Information queries are the default. Firmware-derived authentication and the
two fixed revert variants require separate explicit arguments to packet().
There is no arbitrary SET, activation, PIN change, or vendor command encoder.
"""
import struct

SM = bytes.fromhex('00000000000000ff')
ADMIN_SP = bytes.fromhex('0000020500000001')
LOCKING_SP = bytes.fromhex('0000020500000002')
MSID = bytes.fromhex('0000000b00008402')
GLOBAL_RANGE = bytes.fromhex('0000080200000001')
LOCKING_INFO = bytes.fromhex('0000080100000001')
THIS_SP = bytes.fromhex('0000000000000001')
ADMIN1 = bytes.fromhex('0000000900010001')
SID = bytes.fromhex('0000000900000006')
PROPERTIES = bytes.fromhex('000000000000ff01')
START_SESSION = bytes.fromhex('000000000000ff02')
GET = bytes.fromhex('0000000600000016')
AUTHENTICATE = bytes.fromhex('000000060000001c')
REVERT_SP = bytes.fromhex('0000000600000011')
REVERT_TPER = bytes.fromhex('0000000600000202')
SL, EL, SN, EN, CALL, EOD, EOS = (bytes([i]) for i in (0xf0,0xf1,0xf2,0xf3,0xf8,0xf9,0xfa))

def uint(value):
    if not 0 <= value <= 0xffffffff:
        raise ValueError('Unsupported integer')
    if value < 64:
        return bytes([value])
    size = max(1, (value.bit_length()+7)//8)
    return bytes([0x80|size])+value.to_bytes(size,'big')

def blob(value):
    if not 1 <= len(value) <= 2047:
        raise ValueError('Unsupported byte string')
    if len(value)<16:
        return bytes([0xa0|len(value)])+value
    return bytes([0xd0|(len(value)>>8),len(value)&255])+value

def call(uid,method,args):
    return CALL+blob(uid)+blob(method)+SL+args+EL+EOD+SL+b'\0\0\0'+EL

def properties():
    limits = [('MaxComPacketSize',2048),('MaxPacketSize',2028),
              ('MaxIndTokenSize',1992),('MaxPackets',1),
              ('MaxSubpackets',1),('MaxMethods',1)]
    names=b''.join(SN+blob(name.encode('ascii'))+uint(value)+EN for name,value in limits)
    return call(SM,PROPERTIES,SN+b'\0'+SL+names+EL+EN)

def start_session(sp,hsn=105):
    if sp not in (ADMIN_SP,LOCKING_SP) or hsn!=105:
        raise ValueError('Anonymous diagnostic session only')
    # Opal requires Write=True support; Write=False sessions are optional.
    # This grants no authority: no authentication is supplied, and our only
    # permitted in-session operations are the three explicit GETs and EOS.
    return call(SM,START_SESSION,uint(hsn)+blob(sp)+b'\1')

def get_columns(uid,start,end):
    allowed=[(MSID,3,3),(LOCKING_SP,6,6),(GLOBAL_RANGE,3,8),(LOCKING_INFO,4,4)]
    allowed.extend((range_uid(n),3,8) for n in range(1,17))
    if (uid,start,end) not in allowed:
        raise ValueError('GET target outside explicit diagnostic allowlist')
    return call(uid,GET,SL+SN+b'\3'+uint(start)+EN+SN+b'\4'+uint(end)+EN+EL)

def authenticate_factory_admin1(factory_msid):
    if not isinstance(factory_msid,bytes) or len(factory_msid)!=32:
        raise ValueError('A freshly read 32-byte factory MSID is required')
    return call(THIS_SP,AUTHENTICATE,blob(ADMIN1)+SN+b'\0'+blob(factory_msid)+EN)

def start_credential_session(sp,authority,challenge):
    if (sp,authority) not in ((LOCKING_SP,ADMIN1),(ADMIN_SP,SID)):
        raise ValueError('Unsupported authority/SP pair')
    if not isinstance(challenge,bytes) or len(challenge)!=32:
        raise ValueError('Exact firmware-derived 32-byte challenge required')
    args=uint(105)+blob(sp)+b'\1'+SN+b'\0'+blob(challenge)+EN+SN+b'\3'+blob(authority)+EN
    return call(SM,START_SESSION,args)

def range_uid(number):
    if not 0<=number<=16:raise ValueError('Locking range outside bounded audit')
    return GLOBAL_RANGE if number==0 else bytes.fromhex('0000080200030000')[:-1]+bytes([number])

def revert_keep_global():
    # Keeps only the global key; other configured ranges can lose their keys.
    # This variant is not used for the case's approved full-reset procedure.
    return call(THIS_SP,REVERT_SP,SN+uint(0x060000)+b'\1'+EN)

def factory_reset():
    return call(ADMIN_SP,REVERT_TPER,b'')

def packet(body,comid=0x7ffe,hsn=0,tsn=0,factory_msid=None,firmware_candidate=None,allow_revert_keep_global=False,allow_factory_reset=False):
    # Only bodies constructible by the fixed diagnostic operations may be sent.
    allowed=[properties(),start_session(ADMIN_SP),start_session(LOCKING_SP),EOS,
             get_columns(MSID,3,3),get_columns(LOCKING_SP,6,6),get_columns(GLOBAL_RANGE,3,8)]
    allowed.append(get_columns(LOCKING_INFO,4,4))
    allowed.extend(get_columns(range_uid(n),3,8) for n in range(1,17))
    if factory_msid is not None:
        allowed.append(authenticate_factory_admin1(factory_msid))
    if firmware_candidate is not None:
        allowed.append(start_credential_session(LOCKING_SP,ADMIN1,firmware_candidate))
        allowed.append(start_credential_session(ADMIN_SP,SID,firmware_candidate))
    if allow_revert_keep_global and firmware_candidate is not None and hsn==105 and tsn:
        allowed.append(revert_keep_global())
    if allow_factory_reset and firmware_candidate is not None and hsn==105 and tsn:
        allowed.append(factory_reset())
    if body not in allowed or comid!=0x7ffe:
        raise ValueError('Unapproved TCG body or ComID')
    if hsn not in (0,105) or not 0 <= tsn <= 0xffffffff:
        raise ValueError('Invalid session number')
    sub=struct.pack('>6sHI',b'\0'*6,0,len(body))+body
    sub+=b'\0'*((-len(sub))%4)
    pkt=struct.pack('>IIIHHII',tsn,hsn,0,0,0,0,len(sub))+sub
    cp=struct.pack('>IHHIII',0,comid,0,0,0,len(pkt))+pkt
    return cp+b'\0'*((-len(cp))%512)

def tokens(data):
    out=[];pos=0
    while pos<len(data):
        lead=data[pos];pos+=1
        if lead<0x80:
            if lead&0x40:raise ValueError('Unexpected signed tiny integer')
            out.append(lead);continue
        if 0x80<=lead<0xc0:
            length=lead&15;is_blob=bool(lead&0x20)
            if lead&0x10:raise ValueError('Unexpected signed/continuation atom')
        elif 0xc0<=lead<0xe0:
            if pos>=len(data):raise ValueError('Truncated medium atom')
            length=((lead&7)<<8)|data[pos];pos+=1;is_blob=bool(lead&0x10)
            if lead&8:raise ValueError('Unexpected signed/continuation atom')
        elif lead>=0xf0:
            out.append(bytes([lead]));continue
        else:raise ValueError('Unsupported atom encoding')
        if not length or pos+length>len(data):raise ValueError('Truncated or empty atom')
        value=data[pos:pos+length];pos+=length
        if not is_blob and length>8:raise ValueError('Oversized integer')
        out.append(value if is_blob else int.from_bytes(value,'big'))
    return out

def response(data,comid=0x7ffe):
    if len(data)<20:raise ValueError('Truncated ComPacket')
    reserved,received,extension,outstanding,minimum,cp_len=struct.unpack_from('>IHHIII',data)
    if received not in (0,comid) or extension:raise ValueError('Unexpected ComID')
    if not cp_len:
        return {'pending':True,'outstanding':outstanding,'minimum':minimum}
    if cp_len<36 or cp_len+20>len(data):raise ValueError('Invalid ComPacket length')
    tsn,hsn,seq,reserved,ack,ackno,pkt_len=struct.unpack_from('>IIIHHII',data,20)
    if pkt_len<12 or pkt_len+24!=cp_len:raise ValueError('Invalid Packet length')
    kind,sub_len=struct.unpack_from('>HI',data,50)
    if kind or sub_len>pkt_len-12 or 56+sub_len>20+cp_len:raise ValueError('Invalid SubPacket length')
    result=tokens(data[56:56+sub_len])
    if result==[EOS]:status=0
    elif len(result)>=6 and result[-6:][0]==EOD and result[-5]==SL and result[-1]==EL:
        if any(not isinstance(v,int) for v in result[-4:-1]):raise ValueError('Invalid method status')
        status=result[-4]
    else:raise ValueError('Missing method status')
    return {'pending':False,'tsn':tsn,'hsn':hsn,'status':status,'tokens':result,
            'outstanding':outstanding,'minimum':minimum}
