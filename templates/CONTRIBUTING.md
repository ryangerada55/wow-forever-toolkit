# Contributing to Tx Studio addons

This file applies to every repository of the organization. Each addon's README covers what is
specific to it. Releases: [RELEASING.md](RELEASING.md). Client patches: [PATCH_DAY.md](PATCH_DAY.md).
Help and bug reports: [SUPPORT.md](SUPPORT.md). Addon ideas: [IDEA_VIABILITY.md](IDEA_VIABILITY.md).

## Ground rules

- **`main` is always releasable.** Work on short-lived branches and merge through pull requests.
- **Every pull request needs one approval and a green Lint run.** Changes to `.github/`,
  `.pkgmeta`, a TOC or `LICENSE` also need a release manager (CODEOWNERS).
- **Only release managers push `v*` tags.** A tag is a release: CI uploads it to CurseForge
  and Wago within minutes.
- **No secrets in repositories, issues or logs.** Tokens live only in GitHub secrets and in
  your local, git-ignored `.env`.
- **WoW: Forever comes first.** Retail and Classic support is per addon and optional.

## Set up your machine

The same install blocks are in the toolkit README ("Quick start") and its `devsetup/README.md`.
Paste them one block at a time; they contain no comments, so macOS's zsh takes them as they are.

macOS (Terminal): the command line tools first (they include git), then Homebrew from
https://brew.sh and the tools:

```sh
xcode-select --install
```

```sh
brew install git gh bash zip jq python@3.14 luacheck luajit shellcheck
brew install --cask visual-studio-code
```

Windows (PowerShell): Scoop's installer needs the execution policy change (answer `Y`):

```powershell
winget install --id Git.Git
winget install --id GitHub.cli
winget install --id Microsoft.VisualStudioCode
winget install --id Python.Python.3.14
winget install --id Microsoft.PowerShell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
irm get.scoop.sh | iex
scoop install luacheck luajit lua-for-windows zip jq shellcheck
```

Then, on both systems, your git identity and the GitHub sign-in (choose HTTPS and "Authenticate
Git with your GitHub credentials"; use your GitHub noreply address unless you want your own
address in public commits):

```sh
git config --global user.name "Your Name"
git config --global user.email "12345678+yourname@users.noreply.github.com"
gh auth login
```

| | macOS | Windows |
|---|---|---|
| Editor | VS Code; each repository's `.vscode/extensions.json` recommends the WoW API, TOC and EditorConfig extensions | same |
| Lua 5.1 (compile check, smoke test) | `luajit` (it also accepts `goto`, which WoW rejects; CI uses real Lua 5.1) | `lua` from `lua-for-windows` (5.1.5), in Git Bash |
| Link checkouts into the game | toolkit `devsetup/link-addons.sh` (symlinks) | toolkit `devsetup/link-addons.ps1` (directory junctions) |
| Run the packager locally (rarely needed; always with `-d`) | Homebrew's bash (macOS ships bash 3.2): `"$(brew --prefix)/bin/bash" ~/dev/packager/release.sh -d` from the addon folder | WSL with `sudo apt install zip jq`, or Git Bash with Scoop's `zip` (or `-z`) |

Game folders (default install locations; yours may differ):

| Client | macOS | Windows |
|---|---|---|
| WoW: Forever beta | `/Applications/World of Warcraft/_classic_beta_/Interface/AddOns` | `C:\Program Files (x86)\World of Warcraft\_classic_beta_\Interface\AddOns` |
| WoW: Forever at launch | not announced yet; never hard-code the folder | same |
| Retail | `.../_retail_/Interface/AddOns` | `...\_retail_\Interface\AddOns` |
| Classic Era | `.../_classic_era_/Interface/AddOns` | `...\_classic_era_\Interface\AddOns` |

Mixed macOS/Windows team, three rules:

1. **Line endings:** every repository has a `.gitattributes` that keeps text files LF. Do not
   override it. A local `.env` saved with CRLF breaks the packager's tokens.
2. **Upper/lower case:** macOS and Windows disks ignore case by default, CI does not.
   Name files exactly as the TOC lists them; `bash .github/scripts/check-toc.sh` checks it.
3. **Paths in Lua and TOCs use backslashes** (`Libs\LibTx-1.0\LibTx-1.0.lua`), which the game
   accepts on both systems.
4. **Scripts stay executable:** Git for Windows does not record the executable bit, so a `.sh`
   file added from Windows reaches macOS as "Permission denied". Lint fails on such a file; fix it
   with `git update-index --chmod=+x path/to/script.sh` and commit. Run scripts as
   `bash path/to/script.sh`, which works either way.

Linking: on either system, check after linking that the addon appears in the AddOn list (neither
junctions on Windows nor symlinks on macOS were tested in the game here, and nobody has confirmed
that the macOS client follows symlinks in `AddOns`). If it does not appear, remove the link first
(`bash link-addons.sh unlink -f <folder> <checkout>`), then sync a copy into the `AddOns` path that
`link-addons.sh list` prints, in quotes because it contains spaces:
`rsync -a --delete --exclude .git <checkout>/ "<AddOns>/<Name>/"`. Without the unlink, rsync
writes through the link into your checkout. Do not let an addon manager update a linked folder;
it replaces the link with a real folder.

Running the packager locally: always pass `-d`. Without it, real IDs in the TOC plus tokens in a
local `.env` upload the build, and an untagged commit goes out as an alpha. Use the commit CI uses
(`git -C <packager clone> checkout 0f24d2169de3ceb3b79a981311b2ebab4c6160c7`; RELEASING.md,
"Packager version").

In game while developing: `/reload` after each change, but restart the client after adding or
renaming a file in the TOC (or the TOC itself); BugGrabber + BugSack (or `/console scriptErrors 1`)
for errors; `/dump expression`, `/fstack` and `/etrace` to inspect (`/dump` asks once before it
allows scripts, and some clients block it).
Keep `/console loadDeprecationFallbacks 0` so your code never leans on Blizzard's temporary
compatibility shims.

## Branches, commits and pull requests

- Branch from `main`: `feat/short-name`, `fix/issue-123`, `chore/bump-libtx`.
- Commit messages: `Area: what changed`, for example `Options: add scale slider`.
- Open the pull request early (draft is fine). Fill in the template, especially which client
  and build you tested on. Every PR gets a test zip: open the PR's **Lint** run, download the
  `test-package` artifact and install it like a normal download.
- Squash-merge. Add a player-facing line to `CHANGELOG.md` under "Unreleased" (add that heading
  at the top if the last release renamed it). Nothing else goes into `CHANGELOG.md`: the packager
  uploads the whole file as the release notes.
- Reviewers check: behavior on Forever, combat safety, new globals, saved-variable migrations,
  strings in `Locales/enUS.lua`, and that the change matches the issue.

## Naming conventions

Everything below shares one namespace across **all** installed addons, and collisions fail
silently (the last or a random writer wins). Our team token is `Tx`.

| Thing | Rule | Example |
|---|---|---|
| Addon folder, TOC and repository | `Tx_<Name>`; sub-addons `Tx_<Name>_<Part>` | `Tx_Bags`, `Tx_Bags_Options` |
| AddOn list grouping | `## Category: Tx Studio` in every TOC | |
| SavedVariables | `Tx<Name>DB`, per character `Tx<Name>CharDB` | `TxBagsDB` |
| Other globals | none. Use the private table: `local addonName, ns = ...` | |
| Named frames (create globals) | avoid; if needed `Tx<Name><Purpose>` | `TxBagsMainFrame` |
| Slash commands | key `TX<NAME>`, command `/tx<name>`; never generic words like `/bags` | `SlashCmdList.TXBAGS`, `/txbags` |
| Addon message prefix | `Tx<Name>`, at most 16 characters, via `LibTx:RegisterPrefix` | `TxBags` |
| Locale keys | `UPPER_SNAKE_CASE` | `L.OPEN_BAGS` |

luacheck enforces the "no other globals" rule: each repository's `.luacheckrc` lists the
globals the addon may write (`globals`) and the WoW API it reads (`read_globals`).

## Coding rules for WoW: Forever

Forever runs retail's Midnight client code with Classic game rules. In practice:

- **Flavor:** ask `LibTx:GetFlavor()`. Do not compare `WOW_PROJECT_ID` with numbers and do not
  key code on the word "Camelot" outside the library: Forever's project ID changed during the
  beta, and a rename of the internal label has been rumored (not confirmed).
- **API availability:** before calling an API that not every client has, test it:
  `if C_SwingTimer and C_SwingTimer.IsTargetWithinSwingRange then`. Never use API presence to
  decide which game you are in: retail test builds already contain most Forever-only APIs.
- **Secret values:** in combat, many unit, aura, cooldown and cast values reach addons as
  secrets. Pass them straight to widgets (`FontString:SetText`, `StatusBar:SetValue`); never
  compare, add, concatenate or use them as table keys. `LibTx.IsSecret(v)` tells you.
  Test every combat feature in combat.
- **Combat log:** closed to addons on Forever and retail. Do not plan features on it.
- **Protected actions:** while `InCombatLockdown()` is true, queue changes to secure frames
  and run them on `PLAYER_REGEN_ENABLED`.
- **Character keys:** Forever has region-wide unique names with surnames. Do not build keys from
  "Name-Realm"; key per-character data by `UnitGUID("player")`, or let AceDB-3.0 handle it.
  Only AceDB-3.0 MINOR 39 (Ace3 master; not the Release-r1403 package) uses the Forever keys
  ("Name Surname", realms grouped by ruleset); see the addon-repo README, "AceDB-3.0 data on Forever".
- **Saved variables:** keep a `dbVersion` and migrate old layouts at `ADDON_LOADED`. Players
  keep settings across updates; a crash in a migration loses them.
- **Experience presets:** Forever players choose a Classic or an Enhanced UI preset at login.
  Test UI addons with both.

## Shared library and dependencies

- Shared code goes into `LibTx-1.0` (its README has the rules). Bump its MINOR on every release
  and keep its public functions backward compatible.
- Addons pin every external in `.pkgmeta` with `tag:` (or `commit:` with a full SHA). `branch:`
  and unpinned externals change under you between builds. The pins checked for Forever (Ace3
  master by commit, LibDataBroker-1.1, HereBeDragons 2.18, LibDBIcon-1.0 MINOR 57 or newer) are
  in the addon-repo README, "Third-party libraries on WoW: Forever".
- Third-party libraries: check the license allows redistribution inside our zip. Code from
  GPL-licensed addons (WeakAuras) must not be pasted into our MIT addons; code from "All Rights
  Reserved" addons (DBM, Details, BigWigs) must not be copied at all.

## Localization

Strings live in the repository: `Locales/enUS.lua` defines every key, other files
(`Locales/deDE.lua`, ...) overwrite the keys they translate. Translators send pull requests.
We do not use CurseForge's translation tool: it works per CurseForge project, so shared strings
would be translated once per addon.

## Before you ask for review

- [ ] Loaded on the Forever client (or the newest Forever build you can reach) with only this
      addon and BugSack enabled; no errors after `/reload`, in and out of combat.
- [ ] From the repository root (the libraries in `Libs/`): `luacheck .`,
      `bash .github/scripts/check-toc.sh`, `python3 .github/scripts/check_paths.py .` and
      `bash tests/harness/run.sh` pass (CI runs them all, the last one on the test zip).
- [ ] New strings are in `Locales/enUS.lua`; new globals are listed in `.luacheckrc`.
- [ ] `CHANGELOG.md` has a line under "Unreleased".
