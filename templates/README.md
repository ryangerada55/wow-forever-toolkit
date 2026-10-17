# Team templates for WoW: Forever addons

Starting points for a small studio that builds several addons for World of Warcraft: Forever
(launch 2026-11-04), with retail and Classic as optional extra targets. Everything here was
checked against the BigWigs packager, GitHub's schemas and a Lua 5.1 runtime on 2026-10-16
(see "What was validated" below).

| Path | What it is | Where it goes |
|---|---|---|
| [`addon-repo/`](addon-repo/) | Skeleton of one addon repository: TOC, Lua, `.pkgmeta` with library pins checked for Forever, lint config, `.gitattributes`/`.editorconfig`, path lint, issue forms, PR template, CODEOWNERS, Dependabot, lint and release workflows | a new repository per addon (use `new-addon-repo.sh`) |
| [`shared-lib/`](shared-lib/) | Skeleton of the team library `LibTx-1.0` that every addon embeds | one repository, `LibTx-1.0` |
| [`set-team.sh`](set-team.sh) | Puts your team token, name, organization, Discord invite and GitHub teams into every template and renames the files that carry them (`LibTx-1.0.lua` → `LibKs-1.0.lua`, ...) | run once per team, before anything else |
| [`new-addon-repo.sh`](new-addon-repo.sh) | Copies `addon-repo/` and renames the placeholders for a new addon | run once per addon |
| [`tests/`](tests/) | `test_check_toc.sh` (the TOC checks) and `test_new_addon.sh` (set-team.sh, new-addon-repo.sh, packager and smoke test, end to end) | the toolkit's own CI |
| [`CONTRIBUTING.md`](CONTRIBUTING.md) | Machine setup on macOS and Windows, branches and reviews, naming rules, Forever coding rules | the organization's `.github` repository |
| [`RELEASING.md`](RELEASING.md) | Versions, release checklist, hotfix and rollback, packager version, first-time project setup and first CurseForge publication (`CURSEFORGE_UPLOADS`), launch-window plan | the organization's `.github` repository |
| [`PATCH_DAY.md`](PATCH_DAY.md) | Runbook for client patches and hotfix builds, with patchwatch; Forever's launch day and the TOC rule | the organization's `.github` repository |
| [`SUPPORT.md`](SUPPORT.md) | How players get help and report bugs; how the team triages | the organization's `.github` repository |
| [`CODEOWNERS.example`](CODEOWNERS.example) | Annotated code-owner rules | `.github/CODEOWNERS` in each repository |
| [`CURSEFORGE_DESCRIPTION.md`](CURSEFORGE_DESCRIPTION.md) | Project summary and description template | the CurseForge and Wago project pages |
| [`IDEA_VIABILITY.md`](IDEA_VIABILITY.md) | Screen for addon ideas against Forever's restrictions, with the in-game tests that settle them | the organization's `.github` repository |

## The structure these templates implement

**One git repository per CurseForge project**, plus **one repository for the shared library**,
plus the organization's **`.github` repository** for team documents.

```text
YOUR-ORG/
├── .github          public; CONTRIBUTING.md, SUPPORT.md, RELEASING.md, PATCH_DAY.md, IDEA_VIABILITY.md,
│                    CURSEFORGE_DESCRIPTION.md
├── LibTx-1.0        shared library, tagged v1.0.0, v1.1.0, ...
├── Tx_Bags          addon -> CurseForge project A, Wago project A
├── Tx_Map           addon -> CurseForge project B, Wago project B
└── ...
```

Why not one repository for all addons? The BigWigs packager builds **one zip for one project per
run** and takes the version and changelog from the **whole repository**: in a test, building
AddonA at a commit tagged `AddonB-v2.0.0` produced `AddonA-AddonB-v2.0.0.zip` with AddonB's
commit in AddonA's changelog. A package also advertises every game version found in any TOC at
the root of its zip. And a TOC without its own `## X-Curse-Project-ID` line borrows the ID of
another folder in the zip (tested here: it would have uploaded to the wrong project). Separate
repositories avoid all of that. Several folders in one repository (`move-folders`) are only for
addons that always ship together, such as an addon and its load-on-demand options.

GitHub uses `CONTRIBUTING.md`, `SUPPORT.md` and the issue templates from a **public** repository
named `.github` for every repository of the organization that has no file of its own.
`RELEASING.md`, `PATCH_DAY.md`, `IDEA_VIABILITY.md` and `CURSEFORGE_DESCRIPTION.md` are not
inherited: they are read in the `.github` repository itself, and each addon README links them.
Each addon repository here brings its own issue forms (they name the addon), which replace the
defaults completely. CODEOWNERS, workflows and LICENSE are never inherited: every repository needs
its own.

## Make the templates yours

Do this once, in the toolkit checkout (after "Publish the toolkit" in the toolkit README), with
`set-team.sh`. **Do not search and replace by hand:** a text-only replacement of `LibTx-1.0` leaves
the files `shared-lib/LibTx-1.0.lua` and `.toc` behind while every TOC lists `LibKs-1.0.lua`; lint,
the TOC check and the packager all pass, and the packaged addon dies in game with "Cannot find a
library instance". `set-team.sh` replaces the text and renames the files in one run, checks that
nothing old is left, and records the values in `templates/team.conf`; `new-addon-repo.sh` refuses
templates that were half renamed by hand.

| Placeholder | Meaning | Example |
|---|---|---|
| `Tx` / `Tx Studio` | team token (one capital and 1 to 3 small letters, unused on CurseForge and Wago) and team name | `Ks` / `Kestrel Studio` |
| `LibTx-1.0` | the shared library's name (`Lib<Token>-1.0`), file names included | `LibKs-1.0` |
| `YOUR-ORG` | GitHub organization | `kestrel-studio` |
| `addon-devs`, `release-managers` | GitHub teams in CODEOWNERS (`@YOUR-ORG/addon-devs`) and the rulesets | (default) |
| `YOUR-INVITE` | Discord invite code (the part after `discord.gg/`) | `abcd1234` |

The example values are Kestrel Studio's; use your own. From the toolkit root (macOS Terminal; on
Windows, Git Bash):

```sh
bash templates/set-team.sh Ks "Kestrel Studio" kestrel-studio abcd1234
git add -A templates
git commit -m "Templates: Kestrel Studio"
git push
```

Two more arguments set other team slugs (`bash templates/set-team.sh Ks "Kestrel Studio"
kestrel-studio abcd1234 devs releasers`). Run the script again to change a value later. It does
not touch this README, `new-addon-repo.sh`, itself or `tests/`. `new-addon-repo.sh` then fills in
the per-addon names (`Ks_Example`, `KsExample`, `KSEXAMPLE`, `ksexample`, `Ks Example`); prose
such as `Tx<Name>DB` in CONTRIBUTING.md's naming table is rewritten to `Ks<Name>DB` as well.

Then create the organization's repositories once (the GitHub CLI signed in with `gh auth login`;
or create each empty **public** repository on github.com and use `git remote add origin ...` and
`git push -u origin main` instead of `gh repo create`):

1. Teams: Organization > Teams > New team, **visible**: `addon-devs` and `release-managers`
   (RELEASING.md, "First-time setup for a new addon", has their permissions).
2. The `.github` repository with the team documents:

   ```sh
   mkdir -p ~/dev/.github
   cp ~/dev/wow-forever-toolkit/templates/{CONTRIBUTING,SUPPORT,RELEASING,PATCH_DAY,IDEA_VIABILITY,CURSEFORGE_DESCRIPTION}.md ~/dev/.github/
   cd ~/dev/.github
   git init -b main
   git add -A
   git commit -m "Team documents"
   gh repo create kestrel-studio/.github --public --source . --remote origin --push
   ```

3. The shared library, tagged `v1.0.0` (every addon pins that tag). Protect `v*` tags with a
   ruleset (Settings > Rules > Rulesets > New tag ruleset: restrict creations, updates and
   deletions, bypass `release-managers`):

   ```sh
   cp -R ~/dev/wow-forever-toolkit/templates/shared-lib ~/dev/LibKs-1.0
   cd ~/dev/LibKs-1.0
   git init -b main
   git add -A
   git commit -m "LibKs-1.0 v1.0.0"
   gh repo create kestrel-studio/LibKs-1.0 --public --source . --remote origin --push
   git tag -a v1.0.0 -m v1.0.0
   git push origin v1.0.0
   ```

## Start a new addon

```sh
bash ~/dev/wow-forever-toolkit/templates/new-addon-repo.sh ~/dev/Ks_Bags Ks_Bags kestrel-studio "Ks Bags"
cd ~/dev/Ks_Bags
git init -b main
git add -A
git commit -m "Start Ks_Bags"
gh repo create kestrel-studio/Ks_Bags --public --source . --remote origin --push
git clone --depth 1 --branch v1.0.0 https://github.com/kestrel-studio/LibKs-1.0 Libs/LibKs-1.0
```

`new-addon-repo.sh` checks everything before it writes, builds the copy in a temporary folder and
prints what is left to fill in by hand (the TOC's `## Notes`, the README's first sentence and
CurseForge link, the Discord invite if `set-team.sh` has not run, the upload IDs). It was tested
with macOS's bash 3.2 and on Linux; Git Bash on Windows is untested. On Windows, Git Bash's `~/dev`
is `C:\Users\<you>\dev`; write `/d/dev/...` for `D:\dev`, and use the same folder for linking later.
Then follow RELEASING.md, "First-time setup for a new addon" (rulesets, Actions permissions,
labels, the CurseForge and Wago projects and the secrets). The other developer clones the
addon and the library instead:

```sh
git clone https://github.com/kestrel-studio/Ks_Bags ~/dev/Ks_Bags
cd ~/dev/Ks_Bags
git clone --depth 1 --branch v1.0.0 https://github.com/kestrel-studio/LibKs-1.0 Libs/LibKs-1.0
```

## What was validated (2026-10-16)

- **YAML**: every `.yml` file and both `.pkgmeta` files parse (yq).
- **Schemas** (check-jsonschema 0.38.2): issue forms against `vendor.github-issue-forms`,
  `config.yml` against `vendor.github-issue-config`, workflows against `vendor.github-workflows`,
  `dependabot.yml` against `vendor.dependabot`. Extra issue-form rules from GitHub's docs
  (unique ids and labels, the reserved option "None", quoted Yes/No) checked by script.
- **actionlint 1.7.12** with shellcheck 0.11.0 on both workflows; shellcheck on all scripts.
- **luacheck 1.2.0** and a Lua 5.1 compile of every Lua file; a Lua 5.1 runtime test of
  LibStub/LibTx upgrades, flavor detection, prefix registration and `Core.lua`.
- **BigWigs packager 0f24d21**, offline, on repositories generated by `new-addon-repo.sh`:
  zip names, `## Version`, pinned library, CurseForge release types and game-version IDs
  (captured with a fake `curl`), the project-ID fallback and `move-folders` licenses.
- **`new-addon-repo.sh` and `check-toc.sh`** under bash 3.2.57 and bash 5.2.
- **Re-run after the library and consistency changes (2026-10-16, later the same day)**: all of
  the above again with the same results, plus the third-party externals in `addon-repo/.pkgmeta`
  uncommented and built with the packager from GitHub (Ace3 by commit and `path:`,
  LibDataBroker-1.1 and HereBeDragons by tag: AceDB-3.0 MINOR 39 in the zip, every packaged Lua
  file compiles), the Subversion step's `.pkgmeta` test against 9 cases, and the vendored
  `check_paths.py` on the template and on a generated repository.
- **Integration pass (2026-10-16, evening)**: all of the above again, plus the Forever-only
  game-type gate in `Tx_Example.toc` (the packager keeps it and still tags only 1.60.1;
  `check-toc.sh` gate and `00000`-stub cases under bash 5.2 and 3.2.57), and the
  `CURSEFORGE_UPLOADS` switch in `release.yml`: the unmodified packager against a local mock of
  the upload sites made no CurseForge request while the switch was off and uploaded with it `on`,
  with Wago and the GitHub Release working either way (`integration.md` in the playbook notes).

- **Review-fix pass (2026-10-16, night)**: `tests/test_new_addon.sh` (48 checks): `set-team.sh`
  with token `Ks` (files renamed, nothing old left, a bad token refused without changes),
  `new-addon-repo.sh` (refusals, names, exec bits), the generated addon's CI checks, the packager
  `0f24d21` with uploads off, the zip's contents, `check-toc.sh --packaged` and the Lua 5.1 smoke
  harness on the packaged folder, a vendored `patchwatch/` kept out of luacheck and the zip (with
  controls showing both lines are needed), the reviewers' text-only rename refused by
  `new-addon-repo.sh` and, built anyway, caught by `check-toc.sh --packaged` and by the harness
  ("Cannot find a library instance"), plus a leaked global, a `/command` without handler, a client
  left inactive by `SUPPORTED_FLAVORS` and a missing interface number, each caught by the
  harness. Scripts under bash 5.2 and the template scripts also under Apple's bash 3.2.57, the
  harness under Lua 5.1.5 and LuaJIT. `tests/test_check_toc.sh`: 26 cases (gate, layout B line,
  `SUPPORTED_FLAVORS` warnings, stub, suffix, case, CRLF, `--packaged`) under bash 5.2 and
  3.2.57. The HelloAzeroth sample's settings panel, compartment, combat queue, `Database.lua`
  and German locale copied into a generated addon by the recipe in the sample's README: luacheck,
  TOC and path checks clean, smoke harness 5 of 5 runs.

Not validated: anything that needs GitHub's servers (issue forms rendering, rulesets,
CODEOWNERS errors, real workflow runs), real CurseForge or Wago uploads, fetching LibDBIcon-1.0
or LibSharedMedia-3.0 from WowAce (blocked here), and the game client. The full logs are in the
research notes: `handson_studio.md`, and `finalize.md` in the playbook folder.
