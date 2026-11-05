"""Build catalog.json from catalog.toml and the published releases."""

import re
from pathlib import Path

from . import pack, repo

SCHEMA = 1
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def build(root: Path, releases: list[dict], sums_dir: Path, repo_url: str) -> dict:
    """`releases` is the GitHub releases API listing; `sums_dir` holds the downloaded `.tar.sha256` files."""
    latest: dict[str, tuple[int, dict]] = {}
    for rel in releases:
        try:
            id, version = pack.parse_tag(rel.get("tag_name", ""))
        except ValueError:
            continue
        asset = next((a for a in rel.get("assets", []) if a["name"] == f"{id}-v{version}.tar"), None)
        if asset is None:
            continue
        if id not in latest or latest[id][0] < version:
            latest[id] = (version, asset)

    avatars = []
    for entry in repo.load_catalog(root):
        id = entry["id"]
        if id not in latest:
            continue
        version, asset = latest[id]
        sum_file = sums_dir / f"{asset['name']}.sha256"
        if not sum_file.is_file():
            raise ValueError(f"{sum_file} is missing")
        digest = sum_file.read_text().split()[0] if sum_file.read_text().split() else ""
        if not SHA256_RE.match(digest):
            raise ValueError(f"{sum_file} does not hold a sha256")
        avatars.append(
            {
                "id": id,
                "outfit": entry["outfit"],
                "proportion": entry["proportion"],
                "title": {"en": entry["title"]["en"], "ja": entry["title"]["ja"]},
                "version": version,
                "url": asset["browser_download_url"],
                "sha256": digest,
                "size": asset["size"],
                "thumbnail": f"{repo_url}/releases/download/catalog/{id}.webp",
            }
        )
    return {"schema": SCHEMA, "avatars": avatars}
