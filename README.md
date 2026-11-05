# sapphire-agent-avatars

Avatars of the default character of [sapphire-agent](https://github.com/sapphire-turtle/sapphire-agent):
2D sprites and a VRM model with VRMA gestures, in regular and chibi proportions.

The agent downloads one avatar into a new workspace; more can be added later from the in-app catalog.

## Avatars

| ID | Outfit | Proportion |
|---|---|---|
| — | — | — |

Each avatar is released as `<id>-v<N>.tar` (2D sprites and a VRM model with its VRMA
gestures, plus `profile.md`) together with `<id>-v<N>.tar.sha256`. To verify a download:

```sh
sha256sum -c default-chibi-v1.tar.sha256
```

The list of every released avatar, with versions, URLs and checksums, is
[`catalog.json`](../../releases/download/catalog/catalog.json).

## Releasing

Push a tag `<id>-v<N>` on a commit already on `main`. CI checks the avatar, builds the tar,
publishes the release and rebuilds the catalog. Push at most three tags at once (GitHub
starts no workflow for larger pushes); if the catalog step fails, run the Release workflow
by hand to rebuild it.

## Checks

`scripts/check` verifies every avatar before it is released: the files named in
`avatar.toml` are present and nothing else is, sprites share one canvas size, and
images and models carry no embedded metadata. `scripts/strip` removes such metadata.
Both need only Python 3.11 or later.

## License

Everything in this repository is dedicated to the public domain under
[CC0 1.0](LICENSE). You may use, modify and redistribute it, commercially or not,
without asking and without credit.
