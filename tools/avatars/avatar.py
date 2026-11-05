"""One avatar directory: avatar.toml, the files it names, and nothing else."""

import tomllib
from pathlib import Path

from . import glb, png, webp

# The same limits the agent enforces when it installs an avatar.
MAX_FILE = 256 * 1024 * 1024
MAX_AVATAR_TOTAL = 100_000_000
SPRITE_EXPRESSIONS = ("happy", "angry", "sad", "relaxed", "surprised")
CONFIG = "avatar.toml"

SPRITE_FORMATS = {".png": png, ".webp": webp}


def path_problem(path: str) -> str | None:
    """Why a path named in avatar.toml is unsafe, mirroring the agent's rule; None if fine."""
    if not path:
        return "path is empty"
    if path.startswith("/") or "\\" in path or ":" in path:
        return f"path {path!r} must be relative and use '/'"
    parts = path.split("/")
    if any(p in ("", ".", "..") for p in parts):
        return f"path {path!r} has an empty, '.' or '..' component"
    if any(p.startswith(".") or p.endswith(".uploading") for p in parts):
        return f"path {path!r} has a hidden or '.uploading' component"
    if path.lower() == CONFIG:
        return f"path {path!r} names the config itself"
    return None


def _structure(config: dict) -> tuple[list[str], list[str], list[str]]:
    """(problems, sprite paths, vrm paths) from the parsed config."""
    problems, sprites, models = [], [], []
    vrm = config.get("vrm")
    if vrm is not None:
        if not vrm.get("model"):
            problems.append("vrm.model is empty")
        else:
            models.append(vrm["model"])
        if "idle" in vrm:
            if not vrm["idle"]:
                problems.append("vrm.idle is empty")
            else:
                models.append(vrm["idle"])
        for name, path in vrm.get("actions", {}).items():
            if not name or not path:
                problems.append(f"vrm.actions.{name} is empty")
            else:
                models.append(path)
    sprite = config.get("sprite")
    if sprite is not None:
        poses = sprite.get("poses", {})
        if not poses:
            problems.append("sprite.poses is empty")
        elif sprite.get("default_pose") not in poses:
            problems.append(f"sprite.default_pose {sprite.get('default_pose')!r} is not one of sprite.poses")
        for name, pose in poses.items():
            if not pose.get("base"):
                problems.append(f"sprite.poses.{name}.base is empty")
            else:
                sprites.append(pose["base"])
            for key, path in pose.get("expressions", {}).items():
                if key not in SPRITE_EXPRESSIONS:
                    problems.append(
                        f"sprite.poses.{name}.expressions.{key} is not one of {', '.join(SPRITE_EXPRESSIONS)}"
                    )
                elif not path:
                    problems.append(f"sprite.poses.{name}.expressions.{key} is empty")
                else:
                    sprites.append(path)
    return problems, sprites, models


def _format_problems(rel: str, data: bytes) -> list[str]:
    ext = Path(rel).suffix.lower()
    try:
        if ext in SPRITE_FORMATS:
            found = SPRITE_FORMATS[ext].check(data)
        elif ext == ".vrm":
            found = glb.check(data, "vrm")
        elif ext == ".vrma":
            found = glb.check(data, "vrma")
        else:
            return [f"{rel}: extension {ext or '(none)'!r} is not allowed"]
    except ValueError as e:
        return [f"{rel}: unreadable: {e}"]
    return [f"{rel}: {p}" for p in found]


def check(dir: Path, profile: Path) -> list[str]:
    """Problems with the avatar in `dir`, shipped together with `profile`; empty when clean."""
    try:
        config = tomllib.loads((dir / CONFIG).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as e:
        return [f"{CONFIG}: {e}"]

    problems, sprites, models = _structure(config)
    referenced = set()
    sizes = {}
    for rel in sprites + models:
        why = path_problem(rel)
        if why:
            problems.append(why)
            continue
        if rel in referenced:
            continue
        referenced.add(rel)
        path = dir / rel
        if not path.is_file():
            problems.append(f"{rel} is named in {CONFIG} but missing")
            continue
        data = path.read_bytes()
        found = _format_problems(rel, data)
        problems += found
        if not found and rel in sprites:
            sizes[rel] = SPRITE_FORMATS[path.suffix.lower()].size(data)

    if len(set(sizes.values())) > 1:
        listing = ", ".join(f"{rel} {w}x{h}" for rel, (w, h) in sorted(sizes.items()))
        problems.append(f"sprites must share one canvas size: {listing}")

    total = 0
    for path in sorted(p for p in dir.rglob("*") if p.is_file()):
        rel = path.relative_to(dir).as_posix()
        size = path.stat().st_size
        total += size
        if size > MAX_FILE:
            problems.append(f"{rel} is {size} bytes, over {MAX_FILE}")
        if rel != CONFIG and rel not in referenced:
            problems.append(f"{rel} is not named in {CONFIG}")

    try:
        profile_bytes = profile.read_bytes()
        profile_bytes.decode("utf-8")
        total += len(profile_bytes)
    except OSError as e:
        problems.append(f"profile: {e}")
    except UnicodeDecodeError:
        problems.append(f"{profile.name} is not UTF-8")
    if total > MAX_AVATAR_TOTAL:
        problems.append(f"total size {total} bytes is over {MAX_AVATAR_TOTAL}")
    return problems
