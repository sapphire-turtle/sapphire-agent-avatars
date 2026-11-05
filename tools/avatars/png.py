"""PNG: list chunks, flag the ones that may carry metadata, strip them."""

import struct
import zlib

SIGNATURE = b"\x89PNG\r\n\x1a\n"
ALLOWED = {b"IHDR", b"PLTE", b"IDAT", b"IEND", b"tRNS", b"sRGB", b"gAMA", b"pHYs"}


def chunks(data: bytes) -> list[tuple[bytes, bytes]]:
    """Every chunk as (type, payload); raises ValueError on a malformed file."""
    if not data.startswith(SIGNATURE):
        raise ValueError("not a PNG")
    out = []
    pos = len(SIGNATURE)
    while pos < len(data):
        if pos + 12 > len(data):
            raise ValueError("truncated PNG chunk header")
        (length,) = struct.unpack(">I", data[pos : pos + 4])
        kind = data[pos + 4 : pos + 8]
        end = pos + 12 + length
        if end > len(data):
            raise ValueError(f"truncated PNG chunk {kind!r}")
        payload = data[pos + 8 : pos + 8 + length]
        (crc,) = struct.unpack(">I", data[end - 4 : end])
        if zlib.crc32(kind + payload) & 0xFFFFFFFF != crc:
            raise ValueError(f"bad CRC in PNG chunk {kind!r}")
        out.append((kind, payload))
        pos = end
    if not out or out[0][0] != b"IHDR" or out[-1][0] != b"IEND":
        raise ValueError("PNG must start with IHDR and end with IEND")
    return out


def check(data: bytes) -> list[str]:
    return [
        f"PNG chunk {kind.decode('latin-1')!r} is not allowed"
        for kind, _ in chunks(data)
        if kind not in ALLOWED
    ]


def strip(data: bytes) -> bytes:
    out = SIGNATURE
    for kind, payload in chunks(data):
        if kind in ALLOWED:
            crc = zlib.crc32(kind + payload) & 0xFFFFFFFF
            out += struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", crc)
    return out


def size(data: bytes) -> tuple[int, int]:
    ihdr = chunks(data)[0][1]
    return struct.unpack(">II", ihdr[:8])
