"""Malformed, recursive, spoofed, incomplete parent DNS cannot become recovery evidence."""
from pathlib import Path
import struct
import sys
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'tofu/cloudflare'))
from delegation import parse
from control_plane import ContractError


def encode(domain):
    return b''.join(bytes([len(label)])+label.encode() for label in domain.split('.'))+b'\0'


def packet():
    question=encode('chayan.me')+struct.pack('!HH',2,1)
    records=b''
    for target in ['coby.ns.cloudflare.com','nia.ns.cloudflare.com']:
        data=encode(target)
        records+=b'\xc0\x0c'+struct.pack('!HHIH',2,1,3600,len(data))+data
    return struct.pack('!6H',42,0x8000,1,0,2,0)+question+records


def test_independent_parent_referral():
    assert parse(packet(),42,'chayan.me')=={'coby.ns.cloudflare.com','nia.ns.cloudflare.com'}


@pytest.mark.parametrize('field,value',[(0,43),(1,0x8100),(1,0x8200),(1,0x8003),(2,0),(3,1),(4,0)])
def test_invalid_header_rejected(field,value):
    original=packet();header=list(struct.unpack('!6H',original[:12]));header[field]=value
    with pytest.raises(ContractError): parse(struct.pack('!6H',*header)+original[12:],42,'chayan.me')


@pytest.mark.parametrize('data',[b'',packet()[:-1],packet()+b'junk',packet()[:12]+b'\xc0\x0c'+packet()[14:]])
def test_truncated_or_cyclic_response_rejected(data):
    with pytest.raises(ContractError): parse(data,42,'chayan.me')
