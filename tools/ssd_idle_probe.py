"""Bounded macOS file benchmark; no raw-device writes or existing-file edits."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import plistlib
import subprocess
import time
import uuid

ROOT=Path('/Volumes/UTRAX Secondary Drive')
record=json.loads(Path(__file__).with_name('secondary-after-reset-volume.json').read_text())
VOLUME_UUID=record['volume_uuid']
if record['volume_name']!='UTRAX Secondary Drive':raise RuntimeError('Unexpected formatted volume record')
SIZE=32*1024**2
BLOCK=4*1024**2

def guard():
    info=plistlib.loads(subprocess.check_output(['diskutil','info','-plist',str(ROOT)]))
    if info.get('VolumeUUID')!=VOLUME_UUID or info.get('MountPoint')!=str(ROOT):
        raise RuntimeError('Expected secondary volume UUID/mount required')
    from ssd_reset_format import find_target,validate_target,FIRMWARE
    from reset_safety import validate_authorization,validate_reset_proof
    base=Path(__file__).parent
    authorization=json.loads((base/'private-reset-authorization.json').read_text())
    proof=json.loads((base/'private-reset-result.json').read_text())
    serial=authorization['target_ssd_serial']
    validate_authorization(authorization,authorization['target_usb_serial'],serial,FIRMWARE,time.time())
    validate_reset_proof(proof,authorization,time.time())
    profiler=json.loads(subprocess.check_output(['system_profiler','SPNVMeDataType','-json']))
    bsd=find_target(profiler,serial)
    smart=json.loads(subprocess.check_output(['/opt/homebrew/bin/smartctl','-i','-j','/dev/'+bsd]))
    physical=plistlib.loads(subprocess.check_output(['diskutil','info','-plist','/dev/'+bsd]))
    validate_target(bsd,serial,smart,physical)
    if info.get('APFSPhysicalStores')!=[{'APFSPhysicalStore':bsd+'s2'}]:
        raise RuntimeError('Benchmark volume is not on the approved physical SSD')
    print(json.dumps({'host_load_averages':os.getloadavg(),'measurement_started_unix':time.time()}),flush=True)
    if os.statvfs(ROOT).f_bavail*os.statvfs(ROOT).f_frsize<SIZE+1024**3:
        raise RuntimeError('Insufficient space for bounded file test')

def result(phase,elapsed):
    print(json.dumps({'phase':phase,'bytes':SIZE,'seconds':round(elapsed,6),
                      'MB_per_second':round(SIZE/elapsed/1e6,1)}),flush=True)


def physical_stats():
    tree=plistlib.loads(subprocess.check_output(['ioreg','-r','-c','IONVMeController','-a','-l']))
    def find(node):
        if node.get('IORegistryEntryName')=='IOBlockStorageDriver':return node['Statistics']
        for child in node.get('IORegistryEntryChildren',[]):
            answer=find(child)
            if answer is not None:return answer
    nodes=[n for n in tree if n.get('Model Number')=='WD_BLACK SN850XE 4000GB']
    if len(nodes)!=1:raise RuntimeError('Target physical counter identity ambiguous')
    return find(nodes[0])

guard()
path=ROOT/('codex-ssd-idle-'+str(uuid.uuid4())+'.bin')
fd=None;identity=None
block=os.urandom(BLOCK)
try:
    fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_RDWR,0o600)
    st=os.fstat(fd);identity=(st.st_dev,st.st_ino)
    if st.st_dev!=ROOT.stat().st_dev:raise RuntimeError('Wrong volume')
    fcntl.fcntl(fd,48,1)
    for index in range(SIZE//BLOCK):
        view=memoryview(block)
        while view:
            count=os.write(fd,view)
            if count<=0:raise RuntimeError('Write made no progress')
            view=view[count:]
    os.fsync(fd);fcntl.fcntl(fd,51,0)
    os.close(fd);fd=None
    before=physical_stats()
    print(json.dumps({'idle_probe_started':True,'requested_idle_seconds':60,'file_bytes':SIZE}),flush=True)
    idle_start=time.monotonic();time.sleep(60)
    after_idle=physical_stats()
    fd=os.open(path,os.O_RDONLY);fcntl.fcntl(fd,48,1);fcntl.fcntl(fd,45,0)
    start=time.monotonic();data=bytearray()
    while len(data)<SIZE:
        part=os.read(fd,min(BLOCK,SIZE-len(data)))
        if not part:raise RuntimeError('Unexpected EOF')
        data.extend(part)
    elapsed=time.monotonic()-start
    after=physical_stats()
    expected=hashlib.sha256()
    for _ in range(SIZE//BLOCK):expected.update(block)
    if hashlib.sha256(data).digest()!=expected.digest():raise RuntimeError('Wake read hash mismatch')
    print(json.dumps({'idle_seconds_observed':round(start-idle_start,3),'wake_read_seconds':round(elapsed,6),
        'file_bytes':SIZE,'physical_read_bytes':after['Bytes (Read)']-after_idle['Bytes (Read)'],
        'background_physical_reads_during_idle':after_idle['Operations (Read)']-before['Operations (Read)'],
        'background_physical_writes_during_idle':after_idle['Operations (Write)']-before['Operations (Write)'],
        'read_errors_added':after['Errors (Read)']-before['Errors (Read)'],
        'read_retries_added':after['Retries (Read)']-before['Retries (Read)'],
        'full_file_hash':'matched'}),flush=True)
finally:
    if fd is not None:os.close(fd)
    if identity is not None:
        try:
            st=path.stat()
            if (st.st_dev,st.st_ino)==identity:path.unlink();print('Removed only this probe temporary file.',flush=True)
        except FileNotFoundError:pass
