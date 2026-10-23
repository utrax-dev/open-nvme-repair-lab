"""Extract the tested challenge from an owner's exact known code image.

No device I/O, authentication, reset, or firmware modification is performed.
Credential bytes are written only to a new mode-0600 file, never to stdout.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path

CODE_SIZE=65368
CODE_SHA256='0468b822080cc3b26de98b935175495120c1ad5046e505d4325e73a412ddac20'
INITIALIZER=0x091e
PAYLOAD=INITIALIZER+3

def extract_challenge(code):
    if len(code)!=CODE_SIZE or hashlib.sha256(code).hexdigest()!=CODE_SHA256:
        raise ValueError('Unsupported code image: exact reviewed build required')
    if code[INITIALIZER:PAYLOAD]!=bytes.fromhex('450ca4') or code[PAYLOAD+5]!=0:
        raise ValueError('Reviewed XDATA initializer framing missing')
    return code[PAYLOAD:PAYLOAD+5]+b'\0'*27

def save_private(path,value):
    if not isinstance(value,bytes) or len(value)!=32:
        raise ValueError('Exact 32-byte challenge required')
    flags=os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_NOFOLLOW',0)
    fd=os.open(path,flags,0o600)
    with os.fdopen(fd,'wb') as stream:
        stream.write(value)
        stream.flush()
        os.fsync(stream.fileno())

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--code-image',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args()
    value=extract_challenge(args.code_image.read_bytes())
    save_private(args.output,value)
    print(json.dumps({'challenge_bytes':len(value),'permissions':'0600',
                      'credential_output':'private file only','device_commands_sent':0}))

if __name__=='__main__':main()
