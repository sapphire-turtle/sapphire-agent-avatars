"""Build one avatar's release tar, byte for byte the same on every run."""

import hashlib
import io
import re
import tarfile
from pathlib import Path

from . import repo

TAG_RE = re.compile(r"^(?P<id>.+)-v(?P<version>[1-9][0-9]*)$")


def parse_tag(tag: str) -> tuple[str, int]:
    """`<id>-v<N>` → (id, N); ValueError for anything else."""
    m = TAG_RE.match(tag)
    if not m or not repo.ID_RE.match(m["id"]):
        raise ValueError(f"tag {tag!r} is not <outfit>-<regular|chibi>-v<N>")
    return m["id"], int(m["version"])


def _info(name: str, size: int | None) -> tarfile.TarInfo:
    info = tarfile.TarInfo(name)
    info.mtime = 0
    info.uid = info.gid = 0
    info.uname = info.gname = ""
    if size is None:
        info.type = tarfile.DIRTYPE
        info.mode = 0o755
    else:
        info.size = size
        info.mode = 0o644
    return info


def build(root: Path, id: str, version: int, out_dir: Path) -> Path:
    """Write `<id>-v<N>.tar` and its `.sha256` into `out_dir`; ValueError if the avatar is not publishable."""
    if id not in [e.get("id") for e in repo.load_catalog(root)]:
        raise ValueError(f"{id} is not in catalog.toml")
    problems = repo.check(root, only=id)
    if problems:
        raise ValueError("\n".join(problems))

    src = root / "avatars" / id
    entries = {"avatar": None}
    for path in src.rglob("*"):
        entries["avatar/" + path.relative_to(src).as_posix()] = None if path.is_dir() else path

    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w", format=tarfile.USTAR_FORMAT) as tar:
        for name in sorted(entries):
            path = entries[name]
            if path is None:
                tar.addfile(_info(name, None))
            else:
                data = path.read_bytes()
                tar.addfile(_info(name, len(data)), io.BytesIO(data))

    out_dir.mkdir(parents=True, exist_ok=True)
    name = f"{id}-v{version}.tar"
    out = out_dir / name
    out.write_bytes(buf.getvalue())
    digest = hashlib.sha256(buf.getvalue()).hexdigest()
    (out_dir / f"{name}.sha256").write_text(f"{digest}  {name}\n")
    return out
