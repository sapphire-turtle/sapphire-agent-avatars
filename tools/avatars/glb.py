"""glTF binary (VRM / VRMA): check metadata, embedded images and names; rewrite the generator."""

import json
import re
import struct

from . import png, webp

GENERATOR = "sapphire-agent-avatars"

# The VRM 1.0 meta every model must carry. Change a permission here.
EXPECTED_META = {
    "authors": ["sapphire-agent"],
    "licenseUrl": "https://vrm.dev/licenses/1.0/",
    "otherLicenseUrl": "https://creativecommons.org/publicdomain/zero/1.0/",
    "avatarPermission": "everyone",
    "commercialUsage": "corporation",
    "creditNotation": "unnecessary",
    "allowRedistribution": True,
    "modification": "allowModificationRedistribution",
    "allowExcessivelyViolentUsage": True,
    "allowExcessivelySexualUsage": True,
    "allowPoliticalOrReligiousUsage": True,
    "allowAntisocialOrHateUsage": True,
}
# Meta keys allowed besides EXPECTED_META, with any value.
FREE_META = {"name", "version", "thumbnailImage"}

NAMED = ("images", "textures", "materials", "meshes", "nodes", "skins", "animations", "samplers")
NAME_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
IMAGE_CHECKS = {"image/png": png.check, "image/webp": webp.check}

JSON_CHUNK = 0x4E4F534A
BIN_CHUNK = 0x004E4942


def read(data: bytes) -> tuple[dict, bytes]:
    """The JSON and BIN chunks; raises ValueError on a malformed file."""
    if len(data) < 20 or data[:4] != b"glTF":
        raise ValueError("not a glTF binary")
    version, length = struct.unpack("<II", data[4:12])
    if version != 2 or length != len(data):
        raise ValueError("bad glTF binary header")
    gltf, bin_ = None, b""
    pos = 12
    while pos < len(data):
        if pos + 8 > len(data):
            raise ValueError("truncated glTF chunk header")
        size, kind = struct.unpack("<II", data[pos : pos + 8])
        end = pos + 8 + size
        if end > len(data):
            raise ValueError("truncated glTF chunk")
        payload = data[pos + 8 : end]
        if kind == JSON_CHUNK and gltf is None:
            gltf = json.loads(payload.decode("utf-8"))
        elif kind == BIN_CHUNK:
            bin_ = payload
        pos = end
    if gltf is None:
        raise ValueError("glTF binary has no JSON chunk")
    return gltf, bin_


def write(gltf: dict, bin_: bytes) -> bytes:
    js = json.dumps(gltf, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    js += b" " * (-len(js) % 4)
    out = struct.pack("<II", len(js), JSON_CHUNK) + js
    if bin_:
        b = bin_ + b"\x00" * (-len(bin_) % 4)
        out += struct.pack("<II", len(b), BIN_CHUNK) + b
    return b"glTF" + struct.pack("<II", 2, 12 + len(out)) + out


def _extras(node, path, out):
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "extras":
                out.append(f"{path}.extras is not allowed")
            _extras(value, f"{path}.{key}", out)
    elif isinstance(node, list):
        for i, value in enumerate(node):
            _extras(value, f"{path}[{i}]", out)


def _image_bytes(gltf: dict, bin_: bytes, view_index: int) -> bytes:
    view = gltf["bufferViews"][view_index]
    start = view.get("byteOffset", 0)
    return bin_[start : start + view["byteLength"]]


def check(data: bytes, kind: str) -> list[str]:
    """Problems with a "vrm" or "vrma" file; empty when clean."""
    gltf, bin_ = read(data)
    problems = []
    asset = gltf.get("asset", {})
    if asset.get("generator") != GENERATOR:
        problems.append(f"asset.generator is {asset.get('generator')!r}, expected {GENERATOR!r}")
    if "copyright" in asset:
        problems.append("asset.copyright is not allowed")
    _extras(gltf, "$", problems)

    for i, image in enumerate(gltf.get("images", [])):
        if "uri" in image:
            problems.append(f"images[{i}] uses a uri; images must be embedded")
            continue
        mime = image.get("mimeType")
        if mime not in IMAGE_CHECKS or "bufferView" not in image:
            problems.append(f"images[{i}] must be an embedded image/png or image/webp")
            continue
        try:
            found = IMAGE_CHECKS[mime](_image_bytes(gltf, bin_, image["bufferView"]))
        except (ValueError, IndexError, KeyError) as e:
            found = [f"unreadable: {e}"]
        problems += [f"images[{i}]: {p}" for p in found]

    for section in NAMED:
        for i, item in enumerate(gltf.get(section, [])):
            name = item.get("name")
            if name is not None and not NAME_RE.match(name):
                problems.append(f"{section}[{i}].name {name!r} must be ASCII letters, digits, '_' or '-', up to 64")

    extensions = gltf.get("extensions", {})
    if kind == "vrm":
        meta = extensions.get("VRMC_vrm", {}).get("meta")
        if meta is None:
            problems.append("extensions.VRMC_vrm.meta is missing (VRM 1.0 required)")
        else:
            for key, value in EXPECTED_META.items():
                if meta.get(key) != value:
                    problems.append(f"meta.{key} is {meta.get(key)!r}, expected {value!r}")
            for key in sorted(set(meta) - set(EXPECTED_META) - FREE_META):
                problems.append(f"meta.{key} is not allowed")
    elif kind == "vrma":
        if "VRMC_vrm_animation" not in extensions:
            problems.append("extensions.VRMC_vrm_animation is missing")
    else:
        raise ValueError(f"unknown kind {kind!r}")
    return problems


def strip(data: bytes) -> bytes:
    """Set asset.generator to GENERATOR; everything else, BIN included, is kept."""
    gltf, bin_ = read(data)
    gltf.setdefault("asset", {})["generator"] = GENERATOR
    return write(gltf, bin_)
