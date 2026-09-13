"""Independent, non-recursive parent delegation checks without a host resolver/cache."""

import secrets
import socket
import struct

from control_plane import require


def name(data, offset):
    labels = []
    end = None
    visited = set()
    while True:
        require(
            offset < len(data) and offset not in visited and len(visited) < 128,
            "invalid DNS name",
        )
        visited.add(offset)
        size = data[offset]
        if size & 0xC0 == 0xC0:
            require(offset + 1 < len(data), "truncated DNS pointer")
            if end is None:
                end = offset + 2
            offset = ((size & 0x3F) << 8) | data[offset + 1]
            continue
        require(size <= 63, "invalid DNS label")
        offset += 1
        if size == 0:
            break
        require(offset + size <= len(data), "truncated DNS label")
        labels.append(data[offset : offset + size].decode("ascii").lower())
        offset += size
    value = ".".join(labels)
    require(len(value) <= 253, "DNS name exceeds bound")
    return value, end if end is not None else offset


def parse(data, transaction, domain):
    require(len(data) >= 12, "truncated DNS response")
    identity, flags, questions, answers, authority, additional = struct.unpack(
        "!6H", data[:12]
    )
    require(
        identity == transaction
        and flags & 0x8000
        and not flags & 0x020F
        and not flags & 0x0100
        and questions == 1
        and answers == 0
        and 0 < authority <= 32
        and additional <= 32,
        "invalid parent DNS response",
    )
    question, offset = name(data, 12)
    require(
        question == domain
        and offset + 4 <= len(data)
        and data[offset : offset + 4] == b"\x00\x02\x00\x01",
        "DNS question differs",
    )
    offset += 4
    result = set()
    for index in range(authority + additional):
        owner, offset = name(data, offset)
        require(offset + 10 <= len(data), "truncated DNS record")
        kind, record_class, ttl, size = struct.unpack(
            "!HHIH", data[offset : offset + 10]
        )
        offset += 10
        require(offset + size <= len(data), "truncated DNS record data")
        if index < authority and owner == domain and kind == 2 and record_class == 1:
            target, end = name(data, offset)
            require(end == offset + size, "DNS nameserver record differs")
            result.add(target)
        offset += size
    require(offset == len(data) and result, "parent nameservers missing")
    return result


def nameservers(parent, domain):
    transaction = secrets.randbelow(65536)
    question = (
        b"".join(
            bytes([len(label)]) + label.encode("ascii") for label in domain.split(".")
        )
        + b"\x00\x00\x02\x00\x01"
    )
    packet = struct.pack("!6H", transaction, 0, 1, 0, 0, 0) + question
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as connection:
        connection.settimeout(10)
        connection.connect((parent, 53))
        connection.send(packet)
        return parse(connection.recv(65536), transaction, domain)
