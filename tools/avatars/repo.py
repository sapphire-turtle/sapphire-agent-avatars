"""The repository: catalog.toml, avatars/, thumbnails/ and character/profile.md agree."""

import re
import tomllib
from pathlib import Path

from . import avatar, webp

ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*-(regular|chibi)$")


def profile_path(root: Path) -> Path:
    return root / "character" / "profile.md"


def load_catalog(root: Path) -> list[dict]:
    """The [[avatar]] entries of catalog.toml, in order."""
    return tomllib.loads((root / "catalog.toml").read_text(encoding="utf-8")).get("avatar", [])


def check(root: Path, only: str | None = None) -> list[str]:
    """Problems across the repository; avatar contents only for `only` when given."""
    try:
        entries = load_catalog(root)
    except (OSError, tomllib.TOMLDecodeError) as e:
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
        title = entry.get("title", {})
        if not title.get("en") or not title.get("ja"):
            problems.append(f"{id}: title.en and title.ja are required")
        if id in ids:
            problems.append(f"{id}: duplicate id in catalog.toml")
        ids.append(id)

    dirs = {p.name for p in (root / "avatars").iterdir() if p.is_dir()} if (root / "avatars").is_dir() else set()
    for id in sorted(dirs - set(ids)):
        problems.append(f"{id}: avatars/{id} has no catalog.toml entry")
    for id in sorted(set(ids) - dirs):
        problems.append(f"{id}: catalog.toml entry has no avatars/{id}")

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
