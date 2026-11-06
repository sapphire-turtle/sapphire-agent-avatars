"""Builders for minimal, valid test files, so no binary fixtures are committed."""

import json
import struct
import sys
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))


def png_chunk(kind: bytes, payload: bytes) -> bytes:
    crc = zlib.crc32(kind + payload) & 0xFFFFFFFF
    return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", crc)


def png(w: int, h: int, extra_chunks=()) -> bytes:
    """An 8-bit RGBA PNG of zero pixels; `extra_chunks` go after IHDR."""
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0)
    raw = b"".join(b"\x00" + b"\x00" * (4 * w) for _ in range(h))
    out = b"\x89PNG\r\n\x1a\n" + png_chunk(b"IHDR", ihdr)
    for kind, payload in extra_chunks:
        out += png_chunk(kind, payload)
    out += png_chunk(b"IDAT", zlib.compress(raw)) + png_chunk(b"IEND", b"")
    return out


def riff_chunk(kind: bytes, payload: bytes) -> bytes:
    out = kind + struct.pack("<I", len(payload)) + payload
    if len(payload) % 2:
        out += b"\x00"
    return out


def vp8l(w: int, h: int) -> bytes:
    """A VP8L chunk payload carrying only the header (enough for size parsing)."""
    bits = (w - 1) | ((h - 1) << 14) | (1 << 28)
    return b"\x2f" + struct.pack("<I", bits) + b"\x00\x00\x00"


def webp_lossless(w: int, h: int, extra_chunks=(), vp8x_flags=None) -> bytes:
    """A WebP with a VP8L image; a VP8X header is added when `vp8x_flags` is set."""
    body = b""
    if vp8x_flags is not None:
        payload = bytes([vp8x_flags, 0, 0, 0]) + (w - 1).to_bytes(3, "little") + (h - 1).to_bytes(3, "little")
        body += riff_chunk(b"VP8X", payload)
    body += riff_chunk(b"VP8L", vp8l(w, h))
    for kind, payload in extra_chunks:
        body += riff_chunk(kind, payload)
    return b"RIFF" + struct.pack("<I", 4 + len(body)) + b"WEBP" + body


def glb(gltf: dict, bin_bytes: bytes = b"") -> bytes:
    js = json.dumps(gltf, separators=(",", ":")).encode()
    js += b" " * (-len(js) % 4)
    out = struct.pack("<I", len(js)) + b"JSON" + js
    if bin_bytes:
        b = bin_bytes + b"\x00" * (-len(bin_bytes) % 4)
        out += struct.pack("<I", len(b)) + b"BIN\x00" + b
    return b"glTF" + struct.pack("<II", 2, 12 + len(out)) + out


AVATAR_TOML = """\
[vrm]
model = "vrm/model.vrm"
idle = "vrm/idle.vrma"

[sprite]
default_pose = "idle"

[sprite.poses.idle]
base = "sprite/idle.webp"
expressions = { happy = "sprite/idle-happy.webp" }
"""


def sample_vrm() -> bytes:
    from avatars import glb as glb_mod

    return glb(
        {
            "asset": {"version": "2.0", "generator": glb_mod.GENERATOR},
            "extensionsUsed": ["VRMC_vrm"],
            "extensions": {"VRMC_vrm": {"specVersion": "1.0", "meta": dict(glb_mod.EXPECTED_META, name="Sample")}},
        }
    )


def sample_vrma() -> bytes:
    from avatars import glb as glb_mod

    return glb(
        {
            "asset": {"version": "2.0", "generator": glb_mod.GENERATOR},
            "extensions": {"VRMC_vrm_animation": {"specVersion": "1.0"}},
        }
    )


def avatar(dir: Path) -> None:
    """A valid avatar: one sprite pose with one expression, a VRM and an idle VRMA."""
    (dir / "sprite").mkdir(parents=True)
    (dir / "vrm").mkdir()
    (dir / "avatar.toml").write_text(AVATAR_TOML)
    (dir / "sprite" / "idle.webp").write_bytes(webp_lossless(8, 12))
    (dir / "sprite" / "idle-happy.webp").write_bytes(webp_lossless(8, 12))
    (dir / "vrm" / "model.vrm").write_bytes(sample_vrm())
    (dir / "vrm" / "idle.vrma").write_bytes(sample_vrma())


def repo(root: Path, ids=("default-chibi",)) -> Path:
    """A valid repository holding the given avatars."""
    (root / "thumbnails").mkdir(parents=True)
    entries = []
    for id in ids:
        outfit, proportion = id.rsplit("-", 1)
        avatar(root / "avatars" / id)
        (root / "thumbnails" / f"{id}.webp").write_bytes(webp_lossless(4, 4))
        entries.append(
            f'[[avatar]]\nid = "{id}"\noutfit = "{outfit}"\nproportion = "{proportion}"\n'
            f'title = {{ en = "{id}", ja = "{id}" }}\n'
        )
    (root / "catalog.toml").write_text("\n".join(entries))
    return root
