"""The repository: catalog.toml, avatars/, thumbnails/ and character/profile.md agree."""

import re
import tomllib
from pathlib import Path

from . import avatar, webp

ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*-(regular|chibi)$")


def profile_path(root: Path) -> Path:
    return root / "character" / "profile.md"


def load_catalog(root: Path) -> list[dict]:
    """The [[avatar]] entries of catalog.toml, in order; ValueError if its shape is wrong."""
    entries = tomllib.loads((root / "catalog.toml").read_text(encoding="utf-8")).get("avatar", [])
    if not isinstance(entries, list) or not all(isinstance(e, dict) for e in entries):
        raise ValueError("catalog.toml: avatar must be an array of tables ([[avatar]])")
    for i, entry in enumerate(entries):
        for key in ("id", "outfit", "proportion"):
            if not isinstance(entry.get(key), str):
                raise ValueError(f"catalog.toml avatar[{i}]: {key} must be a string")
        title = entry.get("title")
        if not isinstance(title, dict) or not all(isinstance(title.get(k), str) and title[k] for k in ("en", "ja")):
            raise ValueError(f"catalog.toml avatar[{i}]: title must be a table with non-empty en and ja")
    return entries


def check(root: Path, only: str | None = None) -> list[str]:
    """Problems across the repository; avatar contents only for `only` when given."""
    try:
        entries = load_catalog(root)
    except (OSError, ValueError) as e:
        return [f"catalog.toml: {e}"]

    problems = []
    ids = []
    for i, entry in enumerate(entries):
        id = entry.get("id", "")
        if not ID_RE.match(id):
            problems.append(f"catalog.toml avatar[{i}]: id {id!r} must be <outfit>-<regular|chibi> in lowercase ASCII")
        else:
            outfit, proportion = id.rsplit("-", 1)
            if entry.get("outfit") != outfit or entry.get("proportion") != proportion:
                problems.append(f"{id}: outfit/proportion must be {outfit!r}/{proportion!r}")
        if id in ids:
            problems.append(f"{id}: duplicate id in catalog.toml")
        ids.append(id)

    dirs = {p.name for p in (root / "avatars").iterdir() if p.is_dir()} if (root / "avatars").is_dir() else set()
    for id in sorted(dirs - set(ids)):
        problems.append(f"{id}: avatars/{id} has no catalog.toml entry")
    for id in sorted(set(ids) - dirs):
        problems.append(f"{id}: catalog.toml entry has no avatars/{id}")

    expected = {f"{id}.webp" for id in ids} | {".gitkeep"}
    thumbs = root / "thumbnails"
    for path in sorted(thumbs.iterdir()) if thumbs.is_dir() else []:
        if path.name not in expected:
            problems.append(f"thumbnails/{path.name} belongs to no catalog.toml entry")

    for id in ids:
        thumb = root / "thumbnails" / f"{id}.webp"
        if not thumb.is_file():
            problems.append(f"{id}: thumbnail thumbnails/{id}.webp is missing")
        else:
            try:
                problems += [f"{id}: thumbnail: {p}" for p in webp.check(thumb.read_bytes())]
            except ValueError as e:
                problems.append(f"{id}: thumbnail unreadable: {e}")

    for id in ids:
        if (only is None or id == only) and id in dirs:
            problems += [f"{id}: {p}" for p in avatar.check(root / "avatars" / id, profile_path(root))]
    return problems
