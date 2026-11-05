"""WebP: list RIFF chunks, flag the ones that may carry metadata, strip them."""

import struct

ALLOWED = {b"VP8 ", b"VP8L", b"VP8X", b"ALPH", b"ANIM", b"ANMF"}
# Chunks allowed inside an ANMF frame, after its 16-byte frame header.
FRAME_ALLOWED = {b"VP8 ", b"VP8L", b"ALPH"}
ANMF_HEADER = 16
VP8X_SIZE = 10
# VP8X flag bits announcing chunks this module removes.
FLAG_ICC = 0x20
FLAG_EXIF = 0x08
FLAG_XMP = 0x04


def _parse(data: bytes, pos: int) -> list[tuple[bytes, bytes]]:
    out = []
    while pos < len(data):
        if pos + 8 > len(data):
            raise ValueError("truncated WebP chunk header")
        kind = data[pos : pos + 4]
        (length,) = struct.unpack("<I", data[pos + 4 : pos + 8])
        end = pos + 8 + length
        if end > len(data):
            raise ValueError(f"truncated WebP chunk {kind!r}")
        out.append((kind, data[pos + 8 : end]))
        pos = end + (length % 2)
    return out


def chunks(data: bytes) -> list[tuple[bytes, bytes]]:
    """Every top-level chunk as (type, payload); raises ValueError on a malformed file."""
    if len(data) < 12 or data[:4] != b"RIFF" or data[8:12] != b"WEBP":
        raise ValueError("not a WebP")
    (riff_size,) = struct.unpack("<I", data[4:8])
    if riff_size + 8 != len(data):
        raise ValueError("WebP RIFF size does not match the file")
    out = _parse(data, 12)
    if not out:
        raise ValueError("WebP has no chunks")
    for kind, payload in out:
        if kind == b"VP8X" and len(payload) != VP8X_SIZE:
            raise ValueError("WebP VP8X chunk has the wrong size")
        if kind == b"ANMF" and len(payload) < ANMF_HEADER:
            raise ValueError("WebP ANMF chunk is too short")
    return out


def frame_chunks(anmf: bytes) -> list[tuple[bytes, bytes]]:
    """The chunks inside an ANMF payload."""
    return _parse(anmf, ANMF_HEADER)


def _encode(kind: bytes, payload: bytes) -> bytes:
    out = kind + struct.pack("<I", len(payload)) + payload
    return out + b"\x00" if len(payload) % 2 else out


def check(data: bytes) -> list[str]:
    problems = []
    for kind, payload in chunks(data):
        if kind not in ALLOWED:
            problems.append(f"WebP chunk {kind.decode('latin-1')!r} is not allowed")
        elif kind == b"ANMF":
            problems += [
                f"WebP chunk {sub.decode('latin-1')!r} inside an animation frame is not allowed"
                for sub, _ in frame_chunks(payload)
                if sub not in FRAME_ALLOWED
            ]
    return problems


def strip(data: bytes) -> bytes:
    body = b""
    for kind, payload in chunks(data):
        if kind not in ALLOWED:
            continue
        if kind == b"VP8X":
            payload = bytes([payload[0] & ~(FLAG_ICC | FLAG_EXIF | FLAG_XMP) & 0xFF]) + payload[1:]
        elif kind == b"ANMF":
            frames = b"".join(_encode(k, v) for k, v in frame_chunks(payload) if k in FRAME_ALLOWED)
            payload = payload[:ANMF_HEADER] + frames
        body += _encode(kind, payload)
    return b"RIFF" + struct.pack("<I", 4 + len(body)) + b"WEBP" + body


def size(data: bytes) -> tuple[int, int]:
    """The canvas size: from VP8X when present, else from the image header."""
    for kind, payload in chunks(data):
        if kind == b"VP8X":
            w = int.from_bytes(payload[4:7], "little") + 1
            h = int.from_bytes(payload[7:10], "little") + 1
            return w, h
        if kind == b"VP8L":
            if len(payload) < 5 or payload[0] != 0x2F:
                raise ValueError("bad VP8L header")
            (bits,) = struct.unpack("<I", payload[1:5])
            return (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
        if kind == b"VP8 ":
            if len(payload) < 10 or payload[3:6] != b"\x9d\x01\x2a":
                raise ValueError("bad VP8 header")
            w, h = struct.unpack("<HH", payload[6:10])
            return w & 0x3FFF, h & 0x3FFF
    raise ValueError("WebP has no image chunk")
