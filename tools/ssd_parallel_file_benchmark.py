"""Bounded macOS file benchmark; no raw-device writes or existing-file edits."""
import fcntl
from concurrent.futures import ThreadPoolExecutor
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
SIZE=4*1024**3
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

guard()
path=ROOT/('codex-ssd-benchmark-'+str(uuid.uuid4())+'.bin')
block=os.urandom(BLOCK)
fd=None
identity=None
try:
    fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_RDWR,0o600)
    created=os.fstat(fd);identity=(created.st_dev,created.st_ino)
    if created.st_dev!=ROOT.stat().st_dev:raise RuntimeError('File is not on the verified volume')
    fcntl.fcntl(fd,48,1)  # F_NOCACHE: request cache avoidance on this descriptor.
    print(json.dumps({'test':'4 GiB sequential file write, first read with 8 parallel workers, separate SHA-256 check',
                      'volume':'UTRAX Secondary Drive','cache_policy':'macOS F_NOCACHE requested',
                      'measurement_limit':'file I/O only; device caching and other traffic may affect results'}),flush=True)
    start=time.monotonic()
    for index in range(SIZE//BLOCK):
        view=memoryview(block)
        while view:
            count=os.write(fd,view)
            if count<=0:raise RuntimeError('Write made no progress')
            view=view[count:]
        if (index+1)%256==0:print(json.dumps({'write_progress_GiB':(index+1)//256}),flush=True)
    os.fsync(fd)
    fcntl.fcntl(fd,51,0)  # F_FULLFSYNC: include the requested device flush in write timing.
    result('write_and_full_flush',time.monotonic()-start)
    # Close the writing descriptor before the first read; do not intentionally
    # warm the file with a preceding sequential read.
    os.close(fd)
    fd=os.open(path,os.O_RDONLY)
    fcntl.fcntl(fd,48,1)
    fcntl.fcntl(fd,45,0)  # F_RDAHEAD off; cache avoidance is still a request.
    def physical_stats():
        tree=plistlib.loads(subprocess.check_output(['ioreg','-r','-c','IONVMeController','-a','-l']))
        for node in tree:
            if node.get('Model Number')=='WD_BLACK SN850XE 4000GB':
                def find(value):
                    if value.get('IORegistryEntryName')=='IOBlockStorageDriver':return value['Statistics']
                    for child in value.get('IORegistryEntryChildren',[]):
                        answer=find(child)
                        if answer is not None:return answer
                answer=find(node)
                if answer is not None:return answer
        raise RuntimeError('Physical I/O counters for target unavailable')
    before=physical_stats()
    def read_slice(worker):
        begin=worker*(SIZE//8)
        end=begin+SIZE//8
        position=begin
        while position<end:
            data=os.pread(fd,min(BLOCK,end-position),position)
            if not data:raise RuntimeError('Unexpected EOF during parallel read')
            position+=len(data)
        return position-begin
    start=time.monotonic()
    with ThreadPoolExecutor(max_workers=8) as pool:
        received=sum(pool.map(read_slice,range(8)))
    elapsed=time.monotonic()-start
    if received!=SIZE:raise RuntimeError('Parallel read incomplete')
    after=physical_stats()
    result('first_read_8_parallel_workers_without_hashing',elapsed)
    print(json.dumps({'parallel_read_physical_bytes':after['Bytes (Read)']-before['Bytes (Read)'],
                      'parallel_read_physical_operations':after['Operations (Read)']-before['Operations (Read)'],
                      'read_errors_added':after['Errors (Read)']-before['Errors (Read)'],
                      'read_retries_added':after['Retries (Read)']-before['Retries (Read)']}),flush=True)
    # Hash separately so CPU hashing time cannot be presented as storage throughput.
    expected=hashlib.sha256()
    for _ in range(SIZE//BLOCK):expected.update(block)
    os.lseek(fd,0,os.SEEK_SET)
    actual=hashlib.sha256();remaining=SIZE
    while remaining:
        data=os.read(fd,min(BLOCK,remaining))
        if not data:raise RuntimeError('Unexpected EOF during verification')
        actual.update(data);remaining-=len(data)
    if expected.digest()!=actual.digest():raise RuntimeError('Written/read data hash mismatch')
    print(json.dumps({'verification':'full 4 GiB SHA-256 matched','sha256':actual.hexdigest()}),flush=True)
finally:
    if fd is not None:os.close(fd)
    if identity is not None:
        try:
            observed=path.stat()
            if (observed.st_dev,observed.st_ino)==identity:
                path.unlink()
                print('Removed only the temporary benchmark file created by this run.',flush=True)
            else:print('Temporary path identity changed; cleanup skipped.',flush=True)
        except FileNotFoundError:pass
