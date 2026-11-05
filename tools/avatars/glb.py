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
# meta.name is the avatar's display name: free text, exempt from NAME_RE.
FREE_TEXT_PATHS = {"$.extensions.VRMC_vrm.meta.name"}

ASSET_KEYS = {"version", "minVersion", "generator"}
# Extensions a VRM 1.0 model or VRMA animation may use. Anything else fails,
# so a new metadata extension cannot slip through.
EXTENSIONS = {
    "VRMC_vrm",
    "VRMC_springBone",
    "VRMC_springBone_extended_collider",
    "VRMC_node_constraint",
    "VRMC_materials_mtoon",
    "VRMC_vrm_animation",
    "KHR_materials_unlit",
    "KHR_materials_emissive_strength",
    "KHR_texture_transform",
    "EXT_texture_webp",
}
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
    chunks = []
    pos = 12
    while pos < len(data):
        if pos + 8 > len(data):
            raise ValueError("truncated glTF chunk header")
        size, kind = struct.unpack("<II", data[pos : pos + 8])
        end = pos + 8 + size
        if end > len(data):
            raise ValueError("truncated glTF chunk")
        chunks.append((kind, data[pos + 8 : end]))
        pos = end
    kinds = [k for k, _ in chunks]
    if kinds not in ([JSON_CHUNK], [JSON_CHUNK, BIN_CHUNK]):
        raise ValueError("glTF binary must hold one JSON chunk, then at most one BIN chunk, and nothing else")
    try:
        gltf = json.loads(chunks[0][1].decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise ValueError(f"glTF JSON chunk is not valid JSON: {e}") from None
    if not isinstance(gltf, dict):
        raise ValueError("glTF JSON must be an object")
    return gltf, chunks[1][1] if len(chunks) == 2 else b""


def write(gltf: dict, bin_: bytes) -> bytes:
    js = json.dumps(gltf, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    js += b" " * (-len(js) % 4)
    out = struct.pack("<II", len(js), JSON_CHUNK) + js
    if bin_:
        b = bin_ + b"\x00" * (-len(bin_) % 4)
        out += struct.pack("<II", len(b), BIN_CHUNK) + b
    return b"glTF" + struct.pack("<II", 2, 12 + len(out)) + out


def _walk(node, path, out):
    """Problems anywhere in the JSON: extras, unknown extensions, unsafe names."""
    if isinstance(node, dict):
        for key, value in node.items():
            here = f"{path}.{key}"
            if key == "extras":
                out.append(f"{here} is not allowed")
                continue
            if key == "extensions":
                if not isinstance(value, dict):
                    out.append(f"{here} must be an object")
                    continue
                for ext in value:
                    if ext not in EXTENSIONS:
                        out.append(f"{here}.{ext} is not an allowed extension")
            if key in ("extensionsUsed", "extensionsRequired") and path == "$":
                for ext in value if isinstance(value, list) else [value]:
                    if ext not in EXTENSIONS:
                        out.append(f"{here} lists {ext!r}, not an allowed extension")
                continue
            if key == "name" and here not in FREE_TEXT_PATHS:
                if not isinstance(value, str) or not NAME_RE.match(value):
                    out.append(f"{here} {value!r} must be ASCII letters, digits, '_' or '-', up to 64")
                continue
            _walk(value, here, out)
    elif isinstance(node, list):
        for i, value in enumerate(node):
            _walk(value, f"{path}[{i}]", out)


def _check_images(gltf: dict, bin_: bytes, problems: list) -> None:
    buffers = gltf.get("buffers", [])
    for i, buffer in enumerate(buffers):
        if not isinstance(buffer, dict) or "uri" in buffer:
            problems.append(f"buffers[{i}] uses a uri; only the embedded BIN buffer is allowed")
    for i, image in enumerate(gltf.get("images", [])):
        if not isinstance(image, dict):
            problems.append(f"images[{i}] must be an object")
            continue
        if "uri" in image:
            problems.append(f"images[{i}] uses a uri; images must be embedded")
            continue
        mime = image.get("mimeType")
        if mime not in IMAGE_CHECKS or not isinstance(image.get("bufferView"), int):
            problems.append(f"images[{i}] must be an embedded image/png or image/webp")
            continue
        try:
            view = gltf["bufferViews"][image["bufferView"]]
            if view.get("buffer") != 0:
                problems.append(f"images[{i}] must live in the BIN buffer")
                continue
            start = view.get("byteOffset", 0)
            found = IMAGE_CHECKS[mime](bin_[start : start + view["byteLength"]])
        except (ValueError, IndexError, KeyError, TypeError, AttributeError) as e:
            found = [f"unreadable: {e}"]
        problems += [f"images[{i}]: {p}" for p in found]


def check(data: bytes, kind: str) -> list[str]:
    """Problems with a "vrm" or "vrma" file; empty when clean."""
    if kind not in ("vrm", "vrma"):
        raise ValueError(f"unknown kind {kind!r}")
    try:
        gltf, bin_ = read(data)
    except ValueError as e:
        return [f"unreadable: {e}"]
    problems = []
    asset = gltf.get("asset")
    if not isinstance(asset, dict):
        return ["asset must be an object"]
    if asset.get("generator") != GENERATOR:
        problems.append(f"asset.generator is {asset.get('generator')!r}, expected {GENERATOR!r}")
    for key in sorted(set(asset) - ASSET_KEYS):
        problems.append(f"asset.{key} is not allowed")
    _walk(gltf, "$", problems)
    try:
        _check_images(gltf, bin_, problems)
    except (TypeError, AttributeError) as e:
        problems.append(f"malformed buffers or images: {e}")

    extensions = gltf.get("extensions", {})
    if not isinstance(extensions, dict):
        return problems
    if kind == "vrm":
        vrm = extensions.get("VRMC_vrm")
        meta = vrm.get("meta") if isinstance(vrm, dict) else None
        if not isinstance(meta, dict):
            problems.append("extensions.VRMC_vrm.meta is missing (VRM 1.0 required)")
        else:
            for key, value in EXPECTED_META.items():
                if meta.get(key) != value:
                    problems.append(f"meta.{key} is {meta.get(key)!r}, expected {value!r}")
            for key in sorted(set(meta) - set(EXPECTED_META) - FREE_META):
                problems.append(f"meta.{key} is not allowed")
    elif "VRMC_vrm_animation" not in extensions:
        problems.append("extensions.VRMC_vrm_animation is missing")
    return problems


def strip(data: bytes) -> bytes:
    """Set asset.generator to GENERATOR; everything else, BIN included, is kept."""
    gltf, bin_ = read(data)
    gltf.setdefault("asset", {})["generator"] = GENERATOR
    return write(gltf, bin_)
