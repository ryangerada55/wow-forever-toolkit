# devsetup: macOS and Windows setup for WoW: Forever addon work

Tools and settings for a team that writes addons on both macOS and Windows. They target
WoW: Forever (launches 2026-11-04; beta 1.60.1, Interface 16001, `_Camelot` TOC suffix) and
also work for retail (`_retail_`) and the Classic flavors.

Each step below carries one of three marks:

| Mark | Meaning |
|---|---|
| **[tested]** | Run in this lane's Linux container on 2026-10-16 (log: `research_notes/WoW Forever addon project operations/handson_xplat.md`). |
| **[static]** | Checked only by a linter or compatibility analyzer. |
| **[untested]** | Needs a real Mac or Windows PC. Package names were checked against the package repositories (Homebrew core `33f30f4`, Homebrew cask `5ed4434`, Scoop Main `5b9a501`, winget-pkgs `f536b90`), but nothing was installed. |

## What is in this folder

| File | Purpose |
|---|---|
| `link-addons.sh` | macOS (and Linux/Wine/CI). Finds WoW installs and links dev checkouts into `<flavor>/Interface/AddOns` with symlinks. |
| `link-addons.ps1` | Windows PowerShell 5.1 and PowerShell 7. Does the same with **directory junctions** (by Microsoft's and Git for Windows' accounts they need no admin rights or Developer Mode; not tried on a real PC). |
| `check_paths.py` | Path lint: file-name case, wrong separators, missing files, Windows-invalid names, TOC BOM. Python 3.8+, standard library only. |
| `tests/` | Lint fixtures: `GoodAddon` must pass, `BrokenAddon` must fail (`python3 tests/selftest.py`). `test_link_scripts.sh` runs both link scripts on fake WoW installs made by `make_fake_installs.py` (`bash tests/test_link_scripts.sh`). |
| `platform-notes.lua` | Commented example of Mac/Windows-aware addon code: platform checks, Cmd (META) key bindings, secure-button limits. |
| `check_platform_api.py` | Proves that every API call in a Lua file exists on a client branch of the Blizzard UI source mirror. |
| `.gitattributes`, `.editorconfig` | Line-ending and encoding rules. Copy both into every addon repository. |

## 1. Install the basics

The same install blocks are in the toolkit README ("Quick start") and in `templates/CONTRIBUTING.md`.
The blocks hold no comments, so they paste into macOS's zsh as they are.

### macOS (Apple Silicon or Intel, macOS 12 or later)
1. Command line tools, which give you git: **[untested]**
   ```sh
   xcode-select --install
   ```
2. Homebrew from https://brew.sh, then: **[untested]**
   ```sh
   brew install git gh bash zip jq python@3.14 luacheck luajit shellcheck
   brew install --cask visual-studio-code
   ```
   You need `bash` because macOS still ships `/bin/bash` 3.2.57, and the BigWigs packager stops on it with
   `ERROR! bash version 4.3 or above is required. Your version is 3.2.57...`. **[tested]** with Apple's
   own bash source (tag bash-144), built here. The toolkit's own scripts run on `/bin/bash` 3.2.
3. In VS Code, run **Shell Command: Install 'code' command in PATH**, then install the extensions in section 2. **[untested]**

### Windows 10/11 (x64 or ARM64)
1. Git, the GitHub CLI, VS Code, Python and PowerShell 7 from winget (PowerShell 7 is optional:
   `link-addons.ps1` also runs on the built-in 5.1): **[untested]**
   ```powershell
   winget install --id Git.Git
   winget install --id GitHub.cli
   winget install --id Microsoft.VisualStudioCode
   winget install --id Python.Python.3.14
   winget install --id Microsoft.PowerShell
   ```
2. Scoop (https://scoop.sh; its installer needs the execution policy change, answer `Y`), then the
   Lua and packaging tools: **[untested]**
   ```powershell
   Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
   irm get.scoop.sh | iex
   scoop install luacheck luajit lua-for-windows zip jq shellcheck
   ```
   `lua-for-windows` is Lua 5.1.5 as `lua`. Alternatives: `winget install GnuWin32.Zip` for zip, and
   `DEVCOM.LuaJIT` for LuaJIT (`DEVCOM.Lua` is Lua 5.4, which is not what WoW runs).
3. Leave Git's line-ending default (`core.autocrlf=true`) alone. The `.gitattributes` in each repository
   overrides it, and every text file checks out as LF. **[tested]** by simulating Git for Windows' default with
   `core.autocrlf=true`: without the file, `.sh`, `.lua` and `.toc` files came out CRLF and a CRLF bash script failed
   with `$'\r': command not found`; with the file, all of them came out LF.
4. Case-only renames: use `git mv -f old.lua Old.lua`. A plain rename may not register on NTFS or APFS. **[untested]**
5. Scripts committed from Windows lose their executable bit: Git for Windows sets `core.filemode=false`, so a
   new `.sh` file is stored as mode 100644 and macOS answers "Permission denied" when it is run as
   `./script.sh`. Mark it executable in git and commit:
   ```sh
   git update-index --chmod=+x path/to/script.sh
   ```
   The Lint workflow of the templates and the sample (and the toolkit's own Checks workflow) fails on any
   `.sh` file that is not stored as 100755. Running scripts as `bash path/to/script.sh`, as these documents
   do, works either way. **[tested]** on a scratch repository with `core.filemode=false`.

### Your git identity and GitHub sign-in (both machines)
```sh
git config --global user.name "Your Name"
git config --global user.email "12345678+yourname@users.noreply.github.com"
gh auth login
```
Use your GitHub "noreply" address (GitHub > Settings > Emails) unless you want your own address in every
public commit. Without an identity, `git commit` stops with "Author identity unknown" (on a Mac whose host name
ends in `.local` it commits silently as `you@Your-Mac.local` instead). In `gh auth login` choose GitHub.com,
HTTPS and "Authenticate Git with your GitHub credentials": Yes; GitHub refuses account passwords for
`git push`. **[untested]** on a real machine.

### Lua 5.1
WoW runs Lua 5.1. Homebrew has no plain 5.1 build (`lua` is 5.4); Scoop's `lua-for-windows` is 5.1.5. Use
`luacheck` (the templates' `.luacheckrc` sets `std = "lua51"`) for linting and LuaJIT (5.1-compatible, but it
also accepts `goto`) or Lua 5.1 for running code. On Linux CI, `apt install lua5.1` or the
`leafo/gh-actions-lua` action works. **[tested]** here, where Lua 5.1.5 ran the `platform-notes.lua` test.

CI compiles every Lua file with real Lua 5.1, because luacheck accepts newer syntax. The same check on your
machine, from the addon folder (macOS: write `luajit` for `lua`):
```sh
find . -name '*.lua' -not -path './Libs/*' -not -path './.release/*' -print0 | xargs -0 -I{} lua -e "assert(loadfile([[{}]]))"
```

## 2. VS Code extensions (both OSes)
Install: `code --install-extension ketho.wow-api`, which pulls in `sumneko.lua` (LuaLS), plus
`stanzilla.vscode-wow-toc` and `EditorConfig.EditorConfig`. **[untested]** (the IDs come from the extensions' own
manifests, see `setup.md`)
- **Don't commit `.vscode/settings.json`.** Ketho's extension writes a version-stamped, OS-specific
  extension path into it, which breaks for teammates on the other OS. Commit `.vscode/extensions.json` and a
  `.luarc.json` instead; the addon template and the HelloAzeroth sample ship both (the extension list above,
  and `runtime.version` "Lua 5.1" plus `WOW_PROJECT_CAMELOT` as a known global, which the extension does
  not annotate). Turn on the extension's FrameXML annotations (`wowAPI.luals.frameXML`) in your own user
  settings, or `Settings` and other Blizzard globals show as undefined.
- **Windows on ARM64:** LuaLS publishes no `win32-arm64` build (only linux-x64/arm64, darwin-x64/arm64 and
  win32-x64). Expect x64 emulation, or no language server, on Snapdragon PCs. **[untested]**

## 3. Link your checkout into the game

The game loads only `<WoW root>/<flavor>/Interface/AddOns/<Name>/<Name>.toc`. The link tools find the
install and link each addon folder under its **TOC name**. For example, `~/dev/wow-addon-sample`, which
holds `HelloAzeroth.toc`, becomes `AddOns/HelloAzeroth`.

Run the commands from this folder (`cd ~/dev/wow-forever-toolkit/devsetup`, or `D:\dev\wow-forever-toolkit\devsetup`).
The macOS column starts with `bash`, which works even if the script lost its executable bit (section 1).
The Windows column is PowerShell; prefix each line with `powershell -ExecutionPolicy Bypass -File` as in the
first row, unless you ran `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once.

| | macOS | Windows |
|---|---|---|
| list installs | `bash link-addons.sh list` | `powershell -ExecutionPolicy Bypass -File .\link-addons.ps1 list` |
| link (dry run) | `bash link-addons.sh link -n -f _classic_beta_ ~/dev/MyAddon` | `.\link-addons.ps1 link -Flavor _classic_beta_ D:\dev\MyAddon -DryRun` (or `-WhatIf`) |
| link | `bash link-addons.sh link -f _classic_beta_ ~/dev/MyAddon` | `.\link-addons.ps1 link -Flavor _classic_beta_ D:\dev\MyAddon` |
| link by flavor name | `bash link-addons.sh link -f forever ~/dev/MyAddon` | `.\link-addons.ps1 link -Flavor forever D:\dev\MyAddon` |
| status | `bash link-addons.sh status -f forever ~/dev/MyAddon` | `.\link-addons.ps1 status -Flavor forever D:\dev\MyAddon` |
| unlink, restore installed copy | `bash link-addons.sh unlink --restore -f forever ~/dev/MyAddon` | `.\link-addons.ps1 unlink -Flavor forever D:\dev\MyAddon -Restore` |
| explicit root | `-r "/Volumes/Games/World of Warcraft"` or `WOW_ROOT=...` | `-WowRoot "D:\Games\World of Warcraft"` or `$env:WOW_ROOT` |
| pin what `forever` means | `--forever-folder _forever_` or `WOW_FOREVER_FOLDER=_forever_` | `-ForeverFolder _forever_` or `$env:WOW_FOREVER_FOLDER` |

- **Flavors.** `retail`, `ptr`, `xptr`, `beta`, `classic` (MoP), `era`, `anniversary`, `classic_ptr`,
  `era_ptr`, `forever`, or a literal folder name such as `_classic_beta_`.
- **How `forever` is resolved.** The launch folder is not announced (see "Launch day" below), so `forever` is
  worked out from evidence in each install, in this order:
  1. A folder whose product version is 1.60 or later (Classic Era is 1.15). The product comes from the folder's
     `.flavor.info` (written by the Battle.net agent) or from `product.db`, and the version from `.build.info`.
     This works before the client has ever started.
  2. A folder whose `WTF/Config.wtf` says `lastAddonVersion` 16000-19999. This is ignored when the folder's
     product is known to run another game, except for `_retail_`, which Forever might share.
  3. `_classic_beta_`, the beta folder (WowUp's and instawow's mapping), unless its product now runs another game.

  If several folders qualify (for example the beta in `_classic_beta_` and the "WoW: Forever - Stress Test"
  in `_forever_`, or the launch client while the beta is still installed), the tool never picks one: it
  lists every candidate with its product and build, changes nothing, and asks you to name the folder with
  `-f _folder_`, or to pin it with `--forever-folder _folder_` / `-ForeverFolder _folder_` or the
  environment variable `WOW_FOREVER_FOLDER`. A pin overrides all of this. `list` prints each folder's
  product and version and, for each install, what `forever` resolves to and why (or the candidates).
  Until the beta goes offline (2026-10-19), link into it by name (`-f _classic_beta_`); link into both
  folders if you test on both.
- **Detection.**
  - `--wow-root` or `WOW_ROOT` first.
  - Then Battle.net's `product.db` (protobuf; field numbers from WowUp's decoder):
    `/Users/Shared/Battle.net/Agent/product.db` on macOS, `%ProgramData%\Battle.net\Agent\product.db` plus
    `<drive>:\ProgramData\...` on every drive on Windows.
  - Then Spotlight (`mdfind`) on macOS.
  - Then the defaults `/Applications/World of Warcraft` and `C:\Program Files (x86)\World of Warcraft`.
- **Safety.**
  - A real folder that is in the way, such as a CurseForge-installed copy, is moved to
    `<flavor>/Interface/AddOns-devsetup-backup/<Name>.<timestamp>`. That is outside `AddOns`, so the client and
    addon managers do not load it.
  - Links are only removed when they point at your checkout; `--force`/`-Force` overrides this.
  - Real folders are never deleted.
  - Every action is printed. With `-n`/`-DryRun`, nothing changes.
  - On Windows the junction is removed with `RemoveDirectory`, which Microsoft documents as removing the junction
    without touching the target.
- **Windows execution policy.** Windows client machines default to `Restricted`. Run the script with
  `powershell -ExecutionPolicy Bypass -File ...`, or once run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`
  (the Scoop install in section 1 does that).
  The script is ASCII-only on purpose: Windows PowerShell 5.1 reads BOM-less UTF-8 as ANSI.
- **Junction limits.** Microsoft's `mklink` documentation gives the junction syntax; that junctions need no
  admin rights or Developer Mode comes from secondary sources (the Git for Windows wiki, a Windows blog post),
  and that both folders must be on local NTFS volumes is an inference. For a checkout in WSL
  (`\\wsl.localhost\...`) or on a network share, use `-Symlink`. It needs Developer Mode or an elevated
  prompt. **[untested]** on a real PC.
- **After linking.** Restart the client after adding or renaming a `.toc`; `/reload` is enough for Lua and XML.
  Keep addon managers away from linked folders: WowUp's own warning says its updates replace symlinks with real
  folders.

Test status:
- `link-addons.sh`: **[tested]** in every mode on fake macOS, Windows and Wine trees, with bash 5.2 and with bash 3.2.57
  built from Apple's source. 40 of 40 checks passed on each, and `shellcheck` 0.11.0 is clean.
  - **[tested]** (1.1.0, 2026-10-16) the launch-day layouts A, B, C, a reused beta slot, the degraded case and the
    `forever` pin on fake trees: 25 of 25 checks on bash 5.2 and on bash 3.2.57, and the original 40 still pass.
    Log: `research_notes/WoW Forever addon project playbook/gap_1.md`, "Repo changes made".
  - **[tested]** (1.2.0, 2026-10-16) several Forever folders at once (beta plus Stress Test, launch day with the beta
    still installed, a shared `_retail_` with a stale beta): `-f forever` refuses, lists each candidate with product
    and build and changes nothing; `-f _folder_`, `--forever-folder` and `WOW_FOREVER_FOLDER` pick one.
    `tests/test_link_scripts.sh`: 19 of 19 checks on bash 5.2 and on bash 3.2.57. The earlier suites pass with the
    refusal expected where the old version picked a folder (40 + 27 checks on each bash). Log:
    `research_notes/WoW Forever addon project playbook/fixes_repos.md`.
  - **[untested]** on a real Mac: the BSD userland (Apple awk 20200816, `ln`, `readlink`, `od`), `mdfind`, and
    **whether the Mac client follows a symlinked AddOns folder**. No source confirms it either way, so check the
    AddOn List once.
- `link-addons.ps1`: **[tested]** under PowerShell 7.6.7 on Linux with Windows paths simulated (29 of 29 checks;
  launch-day layouts and the `-ForeverFolder` pin: 17 of 17; several Forever folders at once,
  `tests/test_link_scripts.sh`: 12 of 12; the earlier suites again with the new refusal: 29 + 18).
  **[static]** PSScriptAnalyzer 1.25.0 is clean, including the PowerShell 5.1 and 7.0 compatibility profiles for
  Windows.
  - **[untested]** on real Windows: junction creation and removal, how `LinkType` and `Target` behave on 5.1,
    drive scanning, network/WSL detection, and the real `product.db` contents.

### Launch day: which folder is WoW: Forever? (2026-11-04)
Three layouts are possible. The evidence (`research_notes/WoW Forever addon project playbook/gap_1.md`)
favours **A**: Blizzard put the "WoW: Forever - Stress Test" on its own Battle.net product, `wowf`, which you
can pre-install now.

| Layout | What `list` shows | What to do |
|---|---|---|
| **A** own product and folder (for example `_forever_`) | a new folder labelled `WoW: Forever (new folder)`, with `product wowf 1.60.x` or similar | While the beta folder is still installed, `forever` is ambiguous: `link -f forever` lists both and stops. Link with `-f _forever_` (or pin `WOW_FOREVER_FOLDER=_forever_`) and re-run `link` for every checkout. Once you no longer need the beta folder, uninstall it in Battle.net; `forever` then means the new folder again. |
| **B** a game type inside retail (shared `_retail_`) | `_retail_` labelled `Retail + WoW: Forever (shared folder?)` after a Forever session | Set `WOW_FOREVER_FOLDER=_retail_` (or `-ForeverFolder _retail_`) on both machines. Otherwise `forever` is ambiguous while the stale beta folder is installed, or falls back to it whenever Midnight was the last game run. Every link then loads in both game types, so each addon's TOC must gate the game type (`## AllowLoadGameType: camelot` plus `## ExcludeLoadGameType: standard, classic` for Forever-only addons; `templates/PATCH_DAY.md`, "TOC rule"). The tools warn about this on every `link`. |
| **C** the beta slot (`_classic_beta_`) | `_classic_beta_` with a newer 1.60.x product version | Nothing changes. |

- **Check it before launch.** In Battle.net, install "WoW: Forever - Stress Test" (Game Version menu, "In
  Development"). Then run `list`, or open the gear menu > Show in Explorer/Finder. If its folder is new, that is
  layout A's folder for the stress test. Re-check during name reservation (from 2026-10-27) and at launch.
  Without installing, you can also ask Blizzard's CDN for a product's install folder: see "Before launch" in
  `templates/PATCH_DAY.md` **[untested]**.
- **Degraded case.** If a folder has no `.flavor.info` and `product.db` was not read (`--wow-root`), the tool
  cannot tie a new folder to its product until the client has run once. It then warns that
  `.build.info also lists wowf 1.60.x`. Pass `-f _new_folder_` once.

## 4. Line endings, encoding and file names (`.gitattributes`, `.editorconfig`)
- **Rule: LF in the repository and in every checkout; UTF-8; no BOM in `.toc` files.** **[tested]**
  - The client accepts both CRLF and LF. The BigWigs packager rewrites `.lua .md .toc .txt .xml` to CRLF by default
    (`-u` gives LF), and Mac players run those CRLF zips.
  - The packager also strips a BOM from your **project TOC files** on output, but not from Lua or XML files.
  - Blizzard ships BOMs in 5 Lua and 9 XML files on Forever 70425, but in 0 of its 350 TOC files.
  - None of the 7 large addons scanned commit a BOM in any Lua, TOC or XML file.
- **Keep file names ASCII.** Avoid spaces and Windows-reserved names (`CON`, `AUX`, `NUL`, `COM1`...) and
  characters `<>:"|?*`. Never have two names that differ only in case. `check_paths.py` flags all of these.
- **Path length is not a practical issue.** The worst case measured was about 167 of 260 characters.

## 5. Path lint (`check_paths.py`)
```sh
python3 check_paths.py path/to/MyAddon
python3 check_paths.py path/to/repo
python3 tests/selftest.py
```
The first line checks one addon folder, the second every addon folder in a multi-addon repository, and the
third proves that the lint still catches the fixture's bugs. On Windows, write `py` for `python3`.
- **What it checks.** It compares every TOC entry, XML `<Script>`/`<Include>`, and every `Interface\AddOns\<Addon>\...`
  texture, font or sound path in Lua and XML against the real directory listing. Missing files are fine when
  `.pkgmeta` externals provide them at package time.
- **It works on macOS and Windows too.** It compares names from directory listings and does not rely on the file
  system being case-sensitive.
- **CI.** Run it on `ubuntu-latest` next to luacheck.
- **The `SEP` check.** A single backslash inside a quoted Lua string is an escape: `"Interface\AddOns\X\bar"` reaches
  the game as `InterfaceAddOnsX<backspace>ar` (verified with Lua 5.1.5). Write `\\`, `/` or `[[...]]`.
- **Results on real code** **[tested]**:

  | Project | Errors | Warnings | Details |
  |---|---|---|---|
  | DBM `4786603` | 39 | | all 38 `Sounds`/`sounds` case mismatches, plus `DBM-Core\textures\otravi.blp`, which does not exist |
  | Questie `ef1241c` | 6 | 2 `EXT` | 6 icon case mismatches; the `EXT` warnings are `.blp` references to files that exist only as `.tga`/`.png` |
  | ElvUI `1ded8b8` | 1 | | a stale `E.TexturePath` |
  | WeakAuras `a690a22` | 0 | | |
  | Packaged BigWigs v427.6 | 0 | | |
  | `wow-addon-sample` | 0 | 1 `TOCNAME` | the repo folder name differs from `HelloAzeroth.toc`, which is expected for a repo |

## 6. Running the BigWigs packager locally
Release builds belong in GitHub Actions (`ubuntu-latest`, the packager pinned to master commit `0f24d21`, as in every
workflow of the templates and the HelloAzeroth sample). Do not use `BigWigsMods/packager@v2`: that tag is still v2.6.1,
which lacks the October Forever fixes; the reasons and the trade-off are in `templates/RELEASING.md`, "Packager
version". Locally, use the same commit (`git clone https://github.com/BigWigsMods/packager` and
`git -C packager checkout 0f24d2169de3ceb3b79a981311b2ebab4c6160c7`), and only for dry runs:
- **macOS:** run it from the addon folder with Homebrew's bash. `-d` skips the upload and `-z` the zip:
  ```sh
  git clone https://github.com/BigWigsMods/packager ~/dev/packager
  git -C ~/dev/packager checkout 0f24d2169de3ceb3b79a981311b2ebab4c6160c7
  cd ~/dev/Tx_Bags
  "$(brew --prefix)/bin/bash" ~/dev/packager/release.sh -d
  ```
  Running `release.sh` from another folder fails ("Could not find an addon TOC file"). **[untested]** on macOS.
  Only BSD `date` is handled explicitly in the script; `sed`, `awk` and `sort -V` on macOS are unverified. If the
  changelog step fails, put GNU sed first on `PATH` for that run (`brew install gnu-sed` installs it as `gsed`):
  ```sh
  PATH="$(brew --prefix)/opt/gnu-sed/libexec/gnubin:$PATH" "$(brew --prefix)/bin/bash" ~/dev/packager/release.sh -d
  ```
- **Windows, Git Bash:** Git for Windows ships bash 5.3, which is new enough, but no `zip`. Install `zip` (Scoop) or
  pass `-z`. Set `MSYS_NO_PATHCONV=1` if paths get mangled. **[untested]**
- **Windows, WSL:** `wsl --install`, clone inside the Linux file system, and run `release.sh` there. This is the
  closest match to CI. **[untested]**
- On Linux: **[tested]** the packager ran here (commit `0f24d21`). It produced CRLF output by default, LF with `-u`,
  removed the BOM from the TOC and kept it in Lua.

## 7. Platform-specific addon code
See `platform-notes.lua`. In short:
- **Platform checks.** Use `IsMacClient()`, `IsWindowsClient()` and `IsLinuxClient()`.
- **Cmd is the META modifier.** Bindings use the order `ALT-CTRL-SHIFT-META-<key>`.
- **Secure buttons ignore Cmd.** They only have `alt-`, `ctrl-` and `shift-` prefixes.
- **Mac-only CVar.** `MacUseCommandLeftClickAsRightClick` exists only on the Mac client.
- **Guard `PlatformIsHandheld`.** It exists on Forever and on the 12.1.7 PTR, not on live 12.1.5.
- **On Classic flavors, test `IsWindowsClient` and `IsLinuxClient` before calling them.** Blizzard's Classic code
  neither documents nor calls them.

Test status:
- **[tested]** `luac5.1 -p` passes, and a stubbed Lua 5.1 run passes 26 of 26 checks.
  - In 64 cases, its chord builder matches Blizzard's own `CreateKeyChordStringUsingMetaKeyState`, loaded from
    the Forever branch.
  - `check_platform_api.py` finds all 22 calls on `origin/forever`.
- **[untested]** in game.
