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


# The extensions each role accepts.
SPRITE_EXTS = (".png", ".webp")
MODEL_EXTS = (".vrm",)
ANIMATION_EXTS = (".vrma",)


def _structure(config: dict) -> tuple[list[str], dict[str, list[tuple[str, ...]]]]:
    """(problems, {path: the extensions each of its roles allows}) from the parsed config."""
    problems: list[str] = []
    files: dict[str, list[tuple[str, ...]]] = {}

    def add(key: str, value, exts: tuple[str, ...]) -> None:
        if not isinstance(value, str) or not value:
            problems.append(f"{key} must be a non-empty string")
        else:
            files.setdefault(value, []).append(exts)

    def table(key: str, value) -> bool:
        if not isinstance(value, dict):
            problems.append(f"{key} must be a table")
            return False
        return True

    vrm = config.get("vrm")
    if vrm is not None and table("vrm", vrm):
        add("vrm.model", vrm.get("model"), MODEL_EXTS)
        if "idle" in vrm:
            add("vrm.idle", vrm["idle"], ANIMATION_EXTS)
        actions = vrm.get("actions", {})
        if table("vrm.actions", actions):
            for name, path in actions.items():
                add(f"vrm.actions.{name}", path, ANIMATION_EXTS)

    sprite = config.get("sprite")
    if sprite is not None and table("sprite", sprite):
        poses = sprite.get("poses", {})
        if table("sprite.poses", poses):
            if not poses:
                problems.append("sprite.poses is empty")
            elif sprite.get("default_pose") not in poses:
                problems.append(f"sprite.default_pose {sprite.get('default_pose')!r} is not one of sprite.poses")
            for name, pose in poses.items():
                if not table(f"sprite.poses.{name}", pose):
                    continue
                add(f"sprite.poses.{name}.base", pose.get("base"), SPRITE_EXTS)
                expressions = pose.get("expressions", {})
                if not table(f"sprite.poses.{name}.expressions", expressions):
                    continue
                for key, path in expressions.items():
                    if key not in SPRITE_EXPRESSIONS:
                        problems.append(
                            f"sprite.poses.{name}.expressions.{key} is not one of {', '.join(SPRITE_EXPRESSIONS)}"
                        )
                    else:
                        add(f"sprite.poses.{name}.expressions.{key}", path, SPRITE_EXTS)
    return problems, files


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
    except (ValueError, TypeError, AttributeError, KeyError, IndexError) as e:
        return [f"{rel}: unreadable: {e}"]
    return [f"{rel}: {p}" for p in found]


def check(dir: Path) -> list[str]:
    """Problems with the avatar in `dir`; empty when clean."""
    try:
        config = tomllib.loads((dir / CONFIG).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as e:
        return [f"{CONFIG}: {e}"]

    problems, files = _structure(config)
    referenced = set()
    sizes = {}
    for rel, roles in files.items():
        why = path_problem(rel)
        if why:
            problems.append(why)
            continue
        referenced.add(rel)
        ext = Path(rel).suffix.lower()
        wrong = [exts for exts in roles if ext not in exts]
        if wrong:
            problems += [f"{rel}: a role here takes {' or '.join(exts)} files" for exts in wrong]
            continue
        path = dir / rel
        if not path.is_file():
            problems.append(f"{rel} is named in {CONFIG} but missing")
            continue
        data = path.read_bytes()
        found = _format_problems(rel, data)
        problems += found
        if not found and ext in SPRITE_FORMATS:
            try:
                sizes[rel] = SPRITE_FORMATS[ext].size(data)
            except ValueError as e:
                problems.append(f"{rel}: unreadable: {e}")

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

    if total > MAX_AVATAR_TOTAL:
        problems.append(f"total size {total} bytes is over {MAX_AVATAR_TOTAL}")
    return problems
