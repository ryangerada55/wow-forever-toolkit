# LibTx-1.0

Code shared by every Tx Studio addon: game-flavor and operating-system detection, a
secret-value test and addon message prefix registration. It is a [LibStub](LibStub/LibStub.lua)
library that each addon **embeds** through the BigWigs packager, so players never install it
separately.

```lua
local LibTx = LibStub("LibTx-1.0")
LibTx:GetFlavor()                          -- "forever", "retail", "classic_era" or "classic"
LibTx:IsFlavorSupported({ forever = true })
LibTx:GetPlatform()                        -- "macOS", "Windows", "Linux" or "unknown"
LibTx.IsSecret(value)                      -- true for a secret value (retail 12.x, Forever)
local ok, result = LibTx:RegisterPrefix("TxBags")  -- ok also when another addon registered it first
```

## How addons consume it

In the addon's `.pkgmeta`, always pinned:

```yaml
externals:
  Libs/LibTx-1.0:
    url: https://github.com/YOUR-ORG/LibTx-1.0
    tag: v1.0.0
```

and in the addon's TOC, before the addon's own files:

```text
#@no-lib-strip@
Libs\LibTx-1.0\LibStub\LibStub.lua
Libs\LibTx-1.0\LibTx-1.0.lua
#@end-no-lib-strip@
```

The packager clones the tag into `Libs/LibTx-1.0` and leaves out what this repository's
`.pkgmeta` ignores (README.md, CHANGELOG.md). Tested with the packager at 0f24d21: a
`tag: v1.0.0` pin shipped MINOR 1 while `main` already had MINOR 2; `branch: main` shipped MINOR 2.

Keep this repository **public**: CI clones externals without credentials, and a private
repository would need a deploy key or token in every addon repository. The code ships inside
every addon zip anyway.

## Rules (they follow from how LibStub works)

LibStub keeps one copy per major name for the whole game session. `NewLibrary(MAJOR, MINOR)`
returns nil when an equal or higher MINOR is already loaded, otherwise it upgrades the existing
table in place. The newest copy loaded by **any** installed addon serves **all** of them.

1. **Bump MINOR on every release**, even for a one-line fix. Two different builds with the
   same MINOR: whichever loads first wins, silently.
2. **Never break the public API within `LibTx-1.0`.** An old addon will run against your newest
   copy. Add functions and optional arguments; do not remove, rename or change return values.
   A breaking change gets a new major, `LibTx-2.0`, which loads side by side.
3. **Keep state on the library table** (`lib.cache = lib.cache or {}`), so an upgrade keeps it.
4. **Addons call through the table** (`LibTx:GetFlavor()`). A function cached in a local
   before a newer copy loads keeps running the old code (tested under Lua 5.1).
5. **Test mixed versions:** the newest library together with an addon that still embeds the
   previous tag, and a load-on-demand addon that carries a newer copy (it upgrades the library
   only when it loads).

## Releasing a library version

1. Bump `MINOR` in `LibTx-1.0.lua`, add a `CHANGELOG.md` entry.
2. Merge to `main`, then tag: `git tag -a v1.1.0 -m v1.1.0 && git push origin v1.1.0`.
   There is no CurseForge upload; the tag is the release.
3. In each addon repository: change `tag:` in `.pkgmeta`, test, release the addon.
   A library fix reaches players only when every addon that embeds it ships a new version.

Protect `v*` tags with a tag ruleset (restrict updates and deletions): addons pin tags, so a
moved tag would change what an old pin ships.

## Creating this repository

`templates/README.md` in the toolkit ("Make the templates yours") has the commands: run
`set-team.sh` first, which renames this library everywhere, file names included
(`LibTx-1.0.lua` and `LibTx-1.0.toc` become `LibKs-1.0.*`), then copy the folder, push it as a
**public** repository and tag `v1.0.0`. Never rename the library by search and replace alone: the
files keep their old names while every TOC lists the new ones, and every addon then fails in game
with "Cannot find a library instance". The addon template's CI catches that in its test zip
(`check-toc.sh --packaged` and the smoke test).

## Developing the library

Link this repository into `Interface/AddOns` as its own folder (`LibTx-1.0.toc` loads
LibStub and the library). Addons list `## OptionalDeps: LibTx-1.0`, so the standalone copy loads
before them, and because `main` carries a higher MINOR than the released tags, LibStub serves
your working copy to every addon.

Lint: `luacheck .` (settings in `.luacheckrc`; LibStub is excluded and stays byte-identical
to upstream). CI: copy `.github/workflows/lint.yml` from the addon template and drop its
`package` job.

## License

LibTx-1.0: MIT ([LICENSE](LICENSE)). LibStub: public domain.
