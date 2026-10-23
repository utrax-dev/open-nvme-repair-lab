"""Pure authorization and completion checks shared by the private lab scripts."""
import math
import json
import os

SCOPE='erase_all_secondary_data_and_recreate_apfs'
MODEL='WD_BLACK SN850XE 4000GB'

def recent(value,now):
    return (type(value) in (int,float) and math.isfinite(value)
            and type(now) in (int,float) and math.isfinite(now)
            and 0<=now-value<86400)

def validate_authorization(auth,usb_serial,ssd_serial,firmware,now):
    if not (isinstance(auth,dict) and auth.get('approved') is True
            and isinstance(usb_serial,str) and bool(usb_serial)
            and isinstance(ssd_serial,str) and bool(ssd_serial)
            and auth.get('target_usb_serial')==usb_serial
            and auth.get('target_ssd_serial')==ssd_serial
            and auth.get('firmware')==firmware and auth.get('scope')==SCOPE
            and recent(auth.get('approved_at_unix'),now)):
        raise RuntimeError('Missing, expired, or mismatched explicit erase authorization')

def validate_reset_proof(proof,auth,now):
    validate_authorization(auth,auth.get('target_usb_serial'),auth.get('target_ssd_serial'),
                           auth.get('firmware'),now)
    if not (isinstance(proof,dict) and proof.get('model')==MODEL
            and proof.get('firmware')==auth['firmware']
            and proof.get('target_ssd_serial')==auth['target_ssd_serial']
            and proof.get('target_usb_serial')==auth['target_usb_serial']
            and type(proof.get('reset_method_status')) is int and proof['reset_method_status']==0
            and proof.get('locking_enabled') is False and proof.get('locked') is False
            and recent(proof.get('completed_at_unix'),now)
            and proof['completed_at_unix']>=auth['approved_at_unix']):
        raise RuntimeError('Matching, completed reset evidence required before formatting')

def save_private_completion(path,proof):
    flags=os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_NOFOLLOW',0)
    fd=os.open(path,flags,0o600)
    with os.fdopen(fd,'w') as stream:
        json.dump(proof,stream)
        stream.flush()
        os.fsync(stream.fileno())
