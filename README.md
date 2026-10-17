# wow-forever-toolkit

Tools and templates for a small team, one developer on macOS and one on Windows, that builds and
maintains addons for **World of Warcraft: Forever** (launch Wednesday 2026-11-04; beta client
1.60.1, `## Interface: 16001`, internal game type "camelot"). Everything also works for retail and
the Classic flavors.

| Folder | What it is | When you use it |
|---|---|---|
| [`patchwatch/`](patchwatch/) | A Python command-line tool (standard library only) that reads Blizzard's UI source from the Gethe/wow-ui-source mirror. For each new build it reports API changes (functions, events, tables, secret-value and restriction annotations), `Blizzard_Deprecated` shims, project constants and the Interface number, then scans your addon: which changed APIs it calls (`file:line`) and whether its TOC declares the new Interface number. It also warns when the mirror could hide a build from you: a watched branch missing or quiet for too long, `forever` carrying another game's version, new or removed mirror branches, a new product in the mirror's exporter. Comes with a GitHub Actions workflow that keeps one issue per watched branch, updated at each new build, plus one issue for mirror alerts. | Every patch day, and continuously from CI. See `templates/PATCH_DAY.md`. |
| [`devsetup/`](devsetup/) | Developer machine setup: `link-addons.sh` (macOS: symlinks) and `link-addons.ps1` (Windows: directory junctions) to link a git checkout into the game's AddOns folder; `check_paths.py`, a path lint for the case and separator mistakes that Windows and macOS hide; `platform-notes.lua` (Mac/Windows-aware addon code); `.gitattributes` and `.editorconfig` for every repository. | Once per machine, then whenever you start working on an addon. |
| [`templates/`](templates/) | The team's starting points: `set-team.sh` (puts your team token, name and organization into every template, once), `addon-repo/` (one addon = one repository = one CurseForge/Wago project, with a Lua 5.1 smoke test in `tests/harness/`) and `new-addon-repo.sh` to stamp out a new one, `shared-lib/` (the embedded team library LibTx-1.0), and the team documents `CONTRIBUTING.md`, `RELEASING.md`, `PATCH_DAY.md`, `SUPPORT.md`, `IDEA_VIABILITY.md`, `CODEOWNERS.example` and `CURSEFORGE_DESCRIPTION.md`. | When you start an addon, release it, or decide what to build. |

## How the pieces fit a Forever project

1. **Set up both machines** ("Quick start" below; details in `devsetup/README.md`).
2. **Publish this toolkit** to your GitHub organization and tag it `v0.2.0` ("Publish the toolkit"
   below). The patchwatch workflow installs patchwatch from that tag.
3. **Make the templates yours once** with `templates/set-team.sh`, and create the organization's
   `.github` repository and the shared library repository (`templates/README.md`).
4. **Check the idea** with `templates/IDEA_VIABILITY.md` before building: Forever runs retail's
   Midnight client code, so many combat values are secret to addons.
5. **Start each addon** with `templates/new-addon-repo.sh`, link the checkout into the game with
   `devsetup/link-addons.*`, and develop with `/reload`. The repository's CI compiles every file
   with Lua 5.1, runs luacheck, the TOC checks and the path lint, builds a test zip, checks that
   the zip holds every file its TOC lists and loads it in a Lua 5.1 smoke test.
6. **Release by pushing a tag** (`templates/RELEASING.md`). The BigWigs packager (pinned to master
   `0f24d21`) builds the zip and uploads it to Wago and a GitHub Release, and to CurseForge (game
   version 1.60.1 under "WoW Forever") once CurseForge has approved the project. The first
   CurseForge file goes through the website.
7. **Watch the game builds** with patchwatch and follow `templates/PATCH_DAY.md` on patch days and
   on launch day, when Forever's final install folder and product become known.

## Quick start

The bash, Python, patchwatch and packager commands below were run on Linux, the link scripts on
simulated macOS and Windows installs. Package installs, real Mac and Windows paths, Git Bash and
the game itself were not tried (see "What was tested"). The command blocks contain no comments,
so they paste into macOS's zsh as they are; run them one block at a time.

### 1. Tools

macOS (Terminal). First the command line tools, which include git:

```sh
xcode-select --install
```

Then Homebrew from https://brew.sh, and:

```sh
brew install git gh bash zip jq python@3.14 luacheck luajit shellcheck
brew install --cask visual-studio-code
```

`bash` and `zip` are for running the BigWigs packager locally (macOS's own `/bin/bash` 3.2 is too
old for it); everything else in this toolkit runs on macOS's own bash. Add `subversion` only if an
addon's `.pkgmeta` fetches a WowAce Subversion library and you package locally.

Windows (PowerShell). Scoop's installer needs the execution policy change (answer `Y`):

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

Open a new terminal afterwards so the new commands are on `PATH`. `lua-for-windows` is Lua 5.1.5,
the version WoW runs; `luajit` accepts some syntax (`goto`) that WoW rejects. PowerShell 7 is
optional: `link-addons.ps1` also runs on the built-in Windows PowerShell 5.1.

### 2. Your git identity and GitHub sign-in (both machines, once)

```sh
git config --global user.name "Your Name"
git config --global user.email "12345678+yourname@users.noreply.github.com"
gh auth login
```

Use your GitHub "noreply" address (GitHub > Settings > Emails) unless you want your own address in
every public commit. Without an identity, `git commit` stops with "Author identity unknown"; on a
Mac whose host name ends in `.local` it instead commits silently as `you@Your-Mac.local`. In
`gh auth login` choose GitHub.com, HTTPS, and "Authenticate Git with your GitHub credentials":
Yes. GitHub refuses account passwords for `git push` over HTTPS; `gh` sets up a token for git.
Both developers need write access to the organization's repositories.

### 3. Publish the toolkit

Do this once, on the Mac, from the folder you received (it must still contain its hidden `.git`
folder and the scripts' executable bits; unpack an archive with `tar -xzf`, which keeps both).
Create the repository as **public**: the patchwatch workflow and the template workflows fetch
from it without credentials.

```sh
cd ~/dev/wow-forever-toolkit
git add -A
git commit -m "Toolkit: patchwatch, devsetup, team templates"
gh repo create your-org/wow-forever-toolkit --public --source . --remote origin --push
git tag -a v0.2.0 -m v0.2.0
git push origin v0.2.0
```

Replace `your-org` with your GitHub organization. The tag `v0.2.0` matches patchwatch's version
(`patchwatch/pyproject.toml`); addon repositories install patchwatch from it
(`patchwatch/README.md`, "GitHub Actions"). When patchwatch changes later, bump its version, tag
the toolkit again and move the pin in each addon repository on purpose.

If you commit from Git Bash on Windows instead, the `.sh` files are stored without their
executable bit (Git for Windows uses `core.filemode=false`), and macOS then answers
"Permission denied". The `Checks` workflow fails on that; fix each file with
`git update-index --chmod=+x path/to/script.sh` and commit again. Running a script as
`bash path/to/script.sh`, as every command in these documents does, works either way.

The other developer clones it (Windows: Git Bash or PowerShell):

```sh
git clone https://github.com/your-org/wow-forever-toolkit ~/dev/wow-forever-toolkit
```

```powershell
git clone https://github.com/your-org/wow-forever-toolkit D:\dev\wow-forever-toolkit
```

In Git Bash, `~/dev` is `C:\Users\<you>\dev` and `D:\dev` is `/d/dev`. The Windows examples in
these documents use `D:\dev`; pick one place and use it everywhere.

### 4. Make the templates yours and start an addon

Once for the team (the full procedure, including the `.github` and `LibKs-1.0` repositories, is in
`templates/README.md`, "Make the templates yours"). The example team is Kestrel Studio with the
token `Ks`; use your own values:

```sh
cd ~/dev/wow-forever-toolkit
bash templates/set-team.sh Ks "Kestrel Studio" your-org abcd1234
git add -A templates
git commit -m "Templates: Kestrel Studio"
git push
```

Then for each addon (`templates/README.md`, "Start a new addon"):

```sh
bash ~/dev/wow-forever-toolkit/templates/new-addon-repo.sh ~/dev/Ks_Bags Ks_Bags your-org "Ks Bags"
cd ~/dev/Ks_Bags
git init -b main
git add -A
git commit -m "Start Ks_Bags"
gh repo create your-org/Ks_Bags --public --source . --remote origin --push
git clone --depth 1 --branch v1.0.0 https://github.com/your-org/LibKs-1.0 Libs/LibKs-1.0
```

The other developer clones the addon and its library instead of running `new-addon-repo.sh`:

```sh
git clone https://github.com/your-org/Ks_Bags ~/dev/Ks_Bags
cd ~/dev/Ks_Bags
git clone --depth 1 --branch v1.0.0 https://github.com/your-org/LibKs-1.0 Libs/LibKs-1.0
```

### 5. Link the addon into the game

macOS:

```sh
bash ~/dev/wow-forever-toolkit/devsetup/link-addons.sh list
bash ~/dev/wow-forever-toolkit/devsetup/link-addons.sh link -f _classic_beta_ ~/dev/Ks_Bags
```

Windows (PowerShell):

```powershell
cd D:\dev\wow-forever-toolkit
powershell -ExecutionPolicy Bypass -File .\devsetup\link-addons.ps1 list
powershell -ExecutionPolicy Bypass -File .\devsetup\link-addons.ps1 link -Flavor _classic_beta_ D:\dev\Ks_Bags
```

`list` shows every installed client folder with its product and build, and what `-f forever`
means on this machine. The Forever beta lives in `_classic_beta_` until it goes offline on
2026-10-19, so link into it by name. When more than one folder looks like WoW: Forever (for
example the beta and the "WoW: Forever - Stress Test" in `_forever_`), `-f forever` stops and lists
them; name the folder with `-f` (or pin it: `--forever-folder` / `-ForeverFolder` /
`WOW_FOREVER_FOLDER`), and link into both if you test on both. `devsetup/README.md`, section 3,
has the rest, including the launch-day layouts. Check once that the Mac client loads a
symlinked addon (it is listed in the AddOn List); nobody has confirmed that yet.

### 6. Check an addon like CI does

From the addon folder (macOS, or Git Bash on Windows):

```sh
find . -name '*.lua' -not -path './Libs/*' -not -path './.release/*' -print0 | xargs -0 -I{} lua -e "assert(loadfile([[{}]]))"
luacheck .
bash .github/scripts/check-toc.sh
python3 .github/scripts/check_paths.py .
bash tests/harness/run.sh
```

The first line compiles every file with Lua 5.1. On the Mac use `luajit` for `lua`, which
also accepts `goto` (CI's real Lua 5.1 does not); on Windows `lua` comes from
`lua-for-windows`, and Python is `py` instead of `python3`. `tests/harness/run.sh` needs the
library in `Libs/` (step 4).

### 7. patchwatch on your machine

macOS:

```sh
cd ~/dev/wow-forever-toolkit
python3 -m venv .venv
source .venv/bin/activate
python -m pip install ./patchwatch
patchwatch fetch --branches forever,live,ptr
patchwatch diff forever@-1 forever --addon ~/dev/Ks_Bags --md ~/report.md
```

Windows (PowerShell):

```powershell
cd D:\dev\wow-forever-toolkit
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install .\patchwatch
patchwatch fetch --branches forever,live,ptr
patchwatch diff forever@-1 forever --addon D:\dev\Ks_Bags --md $HOME\report.md
```

The report goes to your home folder, outside every repository. Keep Git's default
`core.autocrlf=true` on Windows: this repository's `.gitattributes` (and the one in every addon
repository) checks every text file out with LF, so the bash scripts run in Git Bash.

## Which one to copy: `templates/addon-repo` or the HelloAzeroth sample

The starter addon `wow-addon-sample` (HelloAzeroth, a separate repository) is a complete,
working example; `templates/addon-repo` is the team's production skeleton. Both use one
unsuffixed TOC, the same packager pin, tag-driven releases, the same `.gitattributes`,
`.editorconfig` and path lint, and both set `GH_API_TOKEN` and `GITHUB_OAUTH` for the packager.

- **Start every team addon from `templates/addon-repo`** with `new-addon-repo.sh`. It has the
  hardened workflows (actions pinned by commit SHA, `persist-credentials: false`, Dependabot,
  a tag-name check that refuses `-rc` tags, a fork guard, an upload-ID/token check, a test zip on
  every pull request that is checked against the TOC and smoke-loaded), the shared library with
  one flavor detector for all addons, and the third-party library pins checked for Forever.
- **Copy features from the sample** that the template leaves out: the Settings API options panel,
  the addon compartment entry, `Database.lua` (schema version with migrations that run before
  defaults are filled), the out-of-combat queue and a second locale. The sample's files depend on
  each other and on its `Flavor.lua`; its README, "Copying features into a team addon", lists
  exactly what to copy and change.
- **Different on purpose:** the sample's TOC lists `11509, 16001, 120105` (one zip for Forever,
  retail and Classic Era); the template's lists `16001` with the Forever-only game-type gate
  (`## AllowLoadGameType: camelot`, `## ExcludeLoadGameType: standard, classic`; the rule and its
  evidence are in `templates/PATCH_DAY.md`, "TOC rule"). Use the template's for a Forever-only
  addon. The full comparison is in `templates/addon-repo/README.md`, "This template and the
  HelloAzeroth sample".

## Libraries on Forever

Checked on 2026-10-16 against Forever 1.60.1 build 70425; `templates/addon-repo/.pkgmeta` has
them ready to uncomment and `templates/addon-repo/README.md` explains each choice.

| Library | Pin |
|---|---|
| Ace3 (with LibStub, CallbackHandler-1.0, ChatThrottleLib) | `https://github.com/WoWUIDev/Ace3`, `commit: 40f4cc1356ae7fcc0cf71fc0a19dc7d50d6ae6c2` (master), `path:` per folder. Not `Release-r1403`: it predates the Forever fixes (AceDB-3.0 MINOR 33 instead of 39). |
| LibDataBroker-1.1 | `https://github.com/tekkub/libdatabroker-1-1`, `tag: v1.1.4` |
| HereBeDragons-2.0 | `https://github.com/Nevcairiel/HereBeDragons`, `tag: 2.18-release` |
| LibDBIcon-1.0, LibSharedMedia-3.0 | WowAce Subversion only: `/trunk` URL plus an svn `tag:`; LibDBIcon MINOR 57 or newer. On Forever, prefer the addon compartment to a LibDBIcon minimap button. |

## Checks

`.github/workflows/checks.yml` runs on every push and pull request. Locally, from the toolkit
root (Linux, or macOS with the Homebrew tools above):

```sh
bash devsetup/tests/test_link_scripts.sh
bash templates/tests/test_check_toc.sh
bash templates/tests/test_new_addon.sh --packager ~/dev/packager/release.sh
python3 devsetup/tests/selftest.py
```

`test_new_addon.sh` needs the BigWigs packager at commit `0f24d21` (`devsetup/README.md`,
section 6), bash 4.3 or newer for it (macOS: add `--packager-bash "$(brew --prefix)/bin/bash"`),
Lua 5.1 or LuaJIT, git, perl, python3 and zip; `--help` explains the options. patchwatch's tests
run with `python -m pip install "./patchwatch[test]"` and then `python -m pytest` in `patchwatch/`.

## What was tested (2026-10-16) and what was not

All checks ran in a Linux container; the logs are in the research notes
(`WoW Forever addon project playbook/fixes_repos.md`, and before it `integration.md`,
`finalize.md` and the `handson_*.md` notes they link). The last full re-run was the review-fix
pass on 2026-10-16.

| Part | Tested | Result |
|---|---|---|
| patchwatch | pytest under Python 3.13 and 3.9, including the mirror alerts (missing, stale and re-purposed branches, new or removed branches, exporter and export-product changes) on a fake git mirror and `check --since` on a branch with too few builds; the Lua parser cross-checked against Lua 5.1 (lupa) on every API documentation file of forever 70425 (earlier also live 12.1.5 and Classic Era 1.15.9); `check` on a copy of the real mirror (13 branches, 12 exporter products) and on the GitHub mirror; `pip install` from a `git+...@v0.2.0#subdirectory=patchwatch` URL; the workflow's shell steps with stub `patchwatch` and `gh` | pass (71 tests on 3.13 with lupa; 67 + 1 skipped without lupa, on 3.13 and 3.9; 646 files) |
| devsetup | `tests/selftest.py`; `check_paths.py` on the sample, the templates and a packaged build; Python 3.13 and 3.9. The link scripts on fake macOS and Windows installs, including several Forever folders at once and the launch-day layouts (`tests/test_link_scripts.sh`: bash 5.2 and Apple's bash 3.2.57, 19 checks each; PowerShell 7.6.7, 12 checks; plus the earlier suites: 40 + 27 checks per bash, 29 + 18 on PowerShell); PSScriptAnalyzer 1.25.0 | pass |
| templates | YAML and GitHub schemas, issue-form rules, actionlint with shellcheck, luacheck, Lua 5.1 compile and runtime tests, CODEOWNERS syntax, Markdown links; `tests/test_check_toc.sh` (26 cases under bash 5.2 and 3.2.57); `tests/test_new_addon.sh` (48 checks: `set-team.sh` with token Ks, `new-addon-repo.sh`, the addon's CI checks, the BigWigs packager with uploads off, the packaged folder against its TOC, the smoke harness on Forever, retail and Classic Era, vendored patchwatch kept out of luacheck and the zip, the reviewers' text-only rename and seeded mistakes caught); the BigWigs packager on generated repositories with a fake `curl` and a local mock server for uploads, with and without `CURSEFORGE_UPLOADS=on` | pass |
| HelloAzeroth sample (separate repository) | Lua 5.1 compile, luacheck, the mock-load harness in `tests/harness/` with Blizzard's own UI code from 3 clients (32 runs, 13 of 13 seeded bugs caught), a packager dry run with uploads off, actionlint | pass |

Not tested:
- **No real Mac or Windows PC**: Homebrew/winget/Scoop installs, the macOS client following a
  symlinked addon folder, real junctions, Git Bash.
- **No game client**: nothing was loaded in WoW: Forever, retail or Classic. Rendering, taint,
  secret values and SavedVariables files are only emulated.
- **No GitHub servers**: no real workflow run, issue-form rendering, Dependabot, rulesets.
- **No uploads** to CurseForge, Wago or WoWInterface (those hosts are blocked here), and no fetch
  from WowAce's Subversion repositories (LibDBIcon-1.0, LibSharedMedia-3.0).
- **Forever's launch layout** (install folder, product) is unannounced; patchwatch and the link
  scripts must be re-checked on 2026-11-04.

## Repository notes

- Nothing is committed yet ("Publish the toolkit" above). `.gitignore` keeps out Python caches,
  virtual environments, patchwatch state and reports, packager output and `.env` token files.
- License: MIT ([LICENSE](LICENSE)), like the HelloAzeroth sample and the templates. The team may
  pick another license before publishing; change `LICENSE` and the `license` field in
  `patchwatch/pyproject.toml` together.
- `.gitattributes` keeps every text file LF (the PowerShell script too; `.cmd`/`.bat` stay CRLF),
  and `.editorconfig` sets the same rules for editors.
- The two `.toc` fixtures with a UTF-8 BOM (`devsetup/tests/fixtures/BrokenAddon`,
  `patchwatch/tests/fixtures/addons`) carry it on purpose.
