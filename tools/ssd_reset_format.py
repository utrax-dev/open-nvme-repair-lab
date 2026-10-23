"""Recreate APFS only after an explicitly approved and verified secondary reset."""
import json
import pathlib
import plistlib
import re
import subprocess
import sys
import time
from reset_safety import SCOPE, validate_authorization, validate_reset_proof

MODEL='WD_BLACK SN850XE 4000GB'
FIRMWARE='624131EX'
SIZE=4000787030016
NAME='UTRAX Secondary Drive'

def find_target(profiler,serial):
    rows=[]
    def walk(value):
        if isinstance(value,dict):
            if value.get('device_model')==MODEL and value.get('device_serial','').strip()==serial:
                rows.append(value)
            for child in value.values():walk(child)
        elif isinstance(value,list):
            for child in value:walk(child)
    walk(profiler)
    if len(rows)!=1:raise RuntimeError('Exactly one matching physical NVMe identity required')
    row=rows[0];bsd=row.get('bsd_name','')
    if not re.fullmatch(r'disk[1-9][0-9]*',bsd) or row.get('device_revision')!=FIRMWARE or row.get('size_in_bytes')!=SIZE:
        raise RuntimeError('Unexpected physical namespace identity or capacity')
    return bsd

def validate_target(bsd,serial,smart,info):
    if smart.get('model_name')!=MODEL or smart.get('serial_number')!=serial or smart.get('firmware_version')!=FIRMWARE:
        raise RuntimeError('Fresh Identify does not match approved SSD')
    if info.get('DeviceIdentifier')!=bsd or info.get('WholeDisk') is not True or info.get('Internal') is not False or info.get('TotalSize')!=SIZE:
        raise RuntimeError('External whole-device/capacity guard failed')

def main():
    if sys.argv[1:]!=['--format-approved-secondary']:
        raise RuntimeError('Explicit format mode required')
    base=pathlib.Path(__file__).parent
    authorization_path=base/'private-reset-authorization.json'
    proof_path=base/'private-reset-result.json'
    for path in (authorization_path,proof_path):
        if path.stat().st_mode&0o077:raise RuntimeError('Private authorization/result permissions required')
    authorization=json.loads(authorization_path.read_text())
    proof=json.loads(proof_path.read_text())
    serial=authorization.get('target_ssd_serial')
    validate_authorization(authorization,authorization.get('target_usb_serial'),serial,FIRMWARE,time.time())
    validate_reset_proof(proof,authorization,time.time())
    profiler=json.loads(subprocess.check_output(['system_profiler','SPNVMeDataType','-json']))
    bsd=find_target(profiler,serial)
    smart=json.loads(subprocess.check_output(['/opt/homebrew/bin/smartctl','-i','-j','/dev/'+bsd]))
    info=plistlib.loads(subprocess.check_output(['diskutil','info','-plist','/dev/'+bsd]))
    validate_target(bsd,serial,smart,info)
    print('Approved target verified by fresh NVMe identity and external whole-device checks: '+bsd,flush=True)
    subprocess.run(['diskutil','eraseDisk','APFS',NAME,'GPT','/dev/'+bsd],check=True)
    volume=plistlib.loads(subprocess.check_output(['diskutil','info','-plist','/Volumes/'+NAME]))
    apfs=plistlib.loads(subprocess.check_output(['diskutil','apfs','list','-plist']))
    containers=[c for c in apfs['Containers'] if c['ContainerReference']==volume.get('ParentWholeDisk')]
    if len(containers)!=1 or [p['DeviceIdentifier'] for p in containers[0]['PhysicalStores']]!=[bsd+'s2']:
        raise RuntimeError('Created APFS volume did not resolve to the approved physical device')
    result={'volume_name':NAME,'volume_uuid':volume['VolumeUUID'],'physical_device':bsd,'formatted_at_unix':time.time()}
    (base/'secondary-after-reset-volume.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result),flush=True)

if __name__=='__main__':main()
