# Tx Example

One sentence that says what Tx Example does, for whom, and on which game client.

- **Download:** [CurseForge](https://www.curseforge.com/wow/addons/tx-example) · [Wago](https://addons.wago.io/) · [GitHub Releases](https://github.com/YOUR-ORG/Tx_Example/releases)
- **Game clients:** WoW: Forever 1.60.1 (Interface 16001)
- **Commands:** `/txexample` (help), `/txexample version`
- **Help and bug reports:** [SUPPORT.md](https://github.com/YOUR-ORG/.github/blob/main/SUPPORT.md) · [open an issue](https://github.com/YOUR-ORG/Tx_Example/issues/new/choose) · [Discord](https://discord.gg/YOUR-INVITE)

The rest of this file is for people who work on the addon. Team rules live in the organization's
`.github` repository: [CONTRIBUTING.md](https://github.com/YOUR-ORG/.github/blob/main/CONTRIBUTING.md),
[RELEASING.md](https://github.com/YOUR-ORG/.github/blob/main/RELEASING.md),
[PATCH_DAY.md](https://github.com/YOUR-ORG/.github/blob/main/PATCH_DAY.md) and
[IDEA_VIABILITY.md](https://github.com/YOUR-ORG/.github/blob/main/IDEA_VIABILITY.md) (what Forever's
restrictions allow, with the in-game tests).

## Repository layout

One repository is one addon folder, one CurseForge project, one Wago project and one zip.

```text
Tx_Example/                  repository root = the addon folder in Interface/AddOns
├── Tx_Example.toc           the only TOC: ## Interface: 16001 and the Forever-only game-type gate
├── Core.lua                 startup, saved variables, slash command
├── Locales/enUS.lua         English strings; other locales overwrite keys
├── Libs/                    fetched by the packager, git-ignored (never commit libraries)
│   └── LibTx-1.0/           team library, pinned by tag in .pkgmeta
├── .pkgmeta                 packaging: externals, changelog, ignore list
├── .luacheckrc              lint settings and the allow-list of globals
├── .gitattributes           LF in the repository and every checkout (macOS and Windows)
├── .editorconfig            UTF-8 without BOM, LF, final newline (editors that support it)
├── .luarc.json              Lua language server: Lua 5.1, WOW_PROJECT_CAMELOT known
├── .vscode/extensions.json  recommended VS Code extensions (commit no other .vscode file)
├── CHANGELOG.md             release notes uploaded with every release (players read all of it)
├── LICENSE
├── tests/harness/           smoke test: loads the addon in plain Lua 5.1 (never packaged)
│   ├── smoke.lua
│   └── run.sh               runs smoke.lua for every client the TOC lists
└── .github/
    ├── ISSUE_TEMPLATE/      bug and feature forms; questions go to Discord
    ├── PULL_REQUEST_TEMPLATE.md
    ├── CODEOWNERS           release managers review .github/, .pkgmeta, the TOC
    ├── dependabot.yml       weekly bumps of the pinned GitHub Actions
    ├── scripts/
    │   ├── check-toc.sh     TOC sanity checks (also run it locally)
    │   └── check_paths.py   path lint, a copy of the toolkit's devsetup/check_paths.py
    └── workflows/
        ├── lint.yml         exec bits, Lua 5.1 compile, luacheck, TOC and path checks; test zip,
        │                    checked against its TOC and smoke-loaded
        └── release.yml      on a v* tag: the same, then the BigWigs packager uploads the zip
```

## Game flavors and the TOC

The addon targets **WoW: Forever** first. The client's internal name for Forever is
`camelot`: `WOW_PROJECT_CAMELOT` (18), the `_Camelot` TOC suffix and `[AllowLoadGameType camelot]`.

| Goal | What to do |
|---|---|
| Forever only (default) | `Tx_Example.toc` as shipped: `## Interface: 16001` plus the game-type gate `## AllowLoadGameType: camelot` and `## ExcludeLoadGameType: standard, classic`; `SUPPORTED_FLAVORS = { forever = true }` in `Core.lua` |
| Also retail and/or Classic Era | **delete the two gate lines**, write `## Interface: 16001, 120105, 11509` in the same TOC, add `retail` / `classic_era` to `SUPPORTED_FLAVORS` in `Core.lua` (otherwise the addon loads there and stays inactive: `check-toc.sh` warns and the smoke test fails), gate flavor-only files with `[AllowLoadGameType standard]` (retail) or `[AllowLoadGameType vanilla]` (Classic Era) |
| Forever-only file inside a multi-flavor TOC | `Forever\Thing.lua [AllowLoadGameType camelot][ExcludeLoadGameType standard, classic]` |
| Different file lists per client | only then split: `Tx_Example_Camelot.toc` for Forever (never `_Forever.toc`: the packager ignores that suffix) and `Tx_Example_Mainline.toc` with `## AllowLoadGameType: standard` for retail. Forever loads a `_Mainline.toc` when it finds no `_Camelot.toc` |
| Never | a stub TOC with `## Interface: 00000` ("client not supported", as Questie ships). The packager reads 00000 as a retail version and tags the CurseForge and Wago uploads for retail as well (simulated against a mock of both sites: retail 12.1.5 next to Forever 1.60.1). `check-toc.sh` rejects it |

**Why the gate looks like this** (evidence: research notes, `WoW Forever addon project
playbook/integration.md`, item 1):
- The wowless project tested real clients (all nine products it models on 2026-09-24; the Forever
  beta client again on 2026-10-09 and 2026-10-13, the TBC Anniversary client on 2026-10-13): a
  game-type condition whose words the
  client does not know at all is ignored, and an unknown word cannot make a condition pass.
  Retail and the Classic clients do not know `camelot`, so `[AllowLoadGameType camelot]` on its
  own loads everywhere.
- `standard` and `classic` are known to every client wowless tested (retail live and PTRs, the
  Forever beta, Classic Era, MoP Classic, TBC Anniversary and their PTRs) and are not active on
  Forever. So `## ExcludeLoadGameType: standard, classic` keeps the addon off retail and Classic,
  whatever a client does with an `## AllowLoadGameType:` line it cannot match.
- `camelot`, `standard` and `classic` are the words Blizzard's own TOCs and the BigWigs packager's
  README use for this. `forever` is accepted by the Forever beta client as an alias, but no
  Blizzard TOC uses it, the real TBC Anniversary client treats it as an unknown word, and nobody
  has tested it on retail or Classic Era, so the template leaves it out.
  If the launch client ever drops "camelot" (PATCH_DAY.md, "Internal label"), add `forever` to the
  Allow line then.
- The packager reads neither line: it still tags the upload 1.60.1 only and keeps both lines in
  the zip (dry run with the packager at `0f24d21`). WowUp and instawow do not read them either.

Why one TOC: on patch day there is one line to update. The packager reads every number on the
line, names a Forever-only zip `Tx_Example-v1.2.0-forever.zip`, and tags the CurseForge file
with each flavor's game version (tested: 16001 → "1.60.1"; 16001, 120105, 11509 → three versions).
An unsuffixed TOC also keeps loading if Blizzard renames "camelot"; a `_Camelot.toc` would not.

`Core.lua` also checks the flavor at runtime and stays inactive on clients it does not list,
because the rules a client applies to interface numbers from other flavors are not documented.

Flavor detection lives in **one place**, `LibTx:GetFlavor()`. If Blizzard renames "camelot" or
changes the project ID, fix the library and re-release; do not test `WOW_PROJECT_ID` numbers in
addon code.

## Shared code

**Default: the embedded team library `LibTx-1.0`.** It has its own repository and is pulled into
`Libs/LibTx-1.0` by `.pkgmeta`, pinned with `tag:`. Players install nothing extra. LibStub serves
the copy with the highest MINOR to every addon in the session, so the library must bump MINOR on
every release and never break its public functions (rules in the library's README). To take a
new library version: change `tag:` in `.pkgmeta`, refresh `Libs/` (below), test, release.

**Alternative: a shared core addon** (for example `Tx_Core`) when several addons need the same
live state or a large data set. Players must install it, so use it only when the embedded
library cannot do the job:

```text
# Tx_Example.toc
## Dependencies: Tx_Core
## X-TxCore-Contract: 1
```

```yaml
# .pkgmeta: CurseForge then lists Tx_Core as a required dependency
required-dependencies:
  - tx-core
```

```lua
-- Core.lua: refuse to run against a core that does not support our contract
local need = tonumber(C_AddOns.GetAddOnMetadata(addonName, "X-TxCore-Contract"))
if not (Tx_Core_API and Tx_Core_API.SupportsContract(need)) then return end
```

Questie (`## X-QuestieDB-Contract`) and DBM (`## X-DBM-Mod-MinCoreRevision`) use this pattern.

A third option, `## AllowAddOnTableAccess: 1` in the provider's TOC plus
`C_AddOns.GetAddOnLocalTable("Tx_Core")` in the consumer, shares the provider's private table
without globals. It is documented on Forever, retail and Classic, but no major addon uses it yet:
test it on the Forever client before you rely on it.

## Third-party libraries on WoW: Forever

Pins checked on 2026-10-16 against Forever 1.60.1 build 70425. The `.pkgmeta` has them ready to
uncomment. Evidence: the research notes, `WoW Forever addon project playbook/gap_4.md`.

| Library | Pin | Source | Why this one |
|---|---|---|---|
| Ace3 (AceAddon, AceDB, AceDBOptions, AceConfig, AceGUI, AceComm, AceEvent, AceTimer, ...) | `commit: 40f4cc1356ae7fcc0cf71fc0a19dc7d50d6ae6c2` (master, 2026-10-02), one `path:` per folder | github.com/WoWUIDev/Ace3 | The newest release, Release-r1403 (2026-08-12), lacks every Forever fix: AceDB-3.0 is MINOR 33 there and 39 on master, Ace3.toc has no 16001, the AceGUI color picker inverts alpha on Forever. BigWigs v427.6 ships the same AceDB (MINOR 39). |
| LibStub, CallbackHandler-1.0 | the same Ace3 commit, `path: LibStub` / `path: CallbackHandler-1.0` | Ace3 | Unchanged since r1403 (LibStub MINOR 2, CallbackHandler MINOR 8). |
| ChatThrottleLib | comes with `path: AceComm-3.0` (version 32) | Ace3 | Unchanged since r1403. Every API it calls is documented on Forever. It retries only throttled sends: a message refused during chat-messaging lockdown (`AddOnMessageLockdown`, 11) is dropped. |
| LibDataBroker-1.1 | `tag: v1.1.4` (commit 1a63ede, the newest, 2008) | github.com/tekkub/libdatabroker-1-1 | Pure Lua. The repository has no license file; name it in your README. |
| HereBeDragons-2.0 | `tag: 2.18-release` (commit 90a7b2d, 2026-10-03) | github.com/Nevcairiel/HereBeDragons | First release with Forever map data (HBD-2.0 MINOR 35). Load LibStub and CallbackHandler-1.0 before it. |
| LibDBIcon-1.0 | WowAce `/trunk` URL + `tag:`; MINOR 57 or newer | repos.wowace.com, Subversion only | MINOR 57 (in BigWigs v427.6, 2026-10-14) sizes the button like retail whenever the addon compartment exists, which it does on Forever; MINOR 55 and 56 size it like Classic there. |
| LibSharedMedia-3.0 | WowAce `/trunk` URL + `tag:`; 12000004 is current | repos.wowace.com, Subversion only | No flavor-specific code; its one namespaced call, `C_UIFileAsset.IsKnownFile`, is documented on Forever. |

Rules that follow from how these libraries load:

- **Your pin decides only while your copy is the newest one loaded.** LibStub keeps the highest
  MINOR of a library that any addon loads. An addon that embeds AceDB r1403 therefore keys its
  data one way when it runs alone and another way when BigWigs, DBM or ElvUI (which embed master)
  load before it. Embed master, and your addon behaves the same either way.
- **Do not depend on the standalone "Ace3" CurseForge project** for Forever: it most likely installs
  the newest release, r1403 (inference; what the CurseForge project serves was not checked).
- **Subversion.** LibDBIcon-1.0 and LibSharedMedia-3.0 have no git repository. The workflows
  install Subversion when `.pkgmeta` names a WowAce, CurseForge or `svn://` URL; local builds on a
  Mac need `brew install subversion`. List a library's tags with
  `svn ls https://repos.wowace.com/wow/libdbicon-1-0/tags`. BigWigs, DBM, WeakAuras and ElvUI use
  unpinned `/trunk` URLs, which build whatever trunk holds that day.
- **Minimap button or addon compartment.** Forever has the addon compartment (retail's code with a
  Forever skin since build 70425). Registering through the TOC (`## AddonCompartmentFunc`, as the
  HelloAzeroth sample does) needs no library and no Subversion. Add a LibDBIcon button only if
  players ask for one; it also needs LibDataBroker-1.1, and nobody has checked its look on the
  Forever minimap in the game yet.
- **Licenses.** `path:` copies one folder, so Ace3's `LICENSE.txt` (root of the repository) is not
  in the zip. Ace3's license asks you to keep its copyright notice: name Ace3 and its license in
  your README or LICENSE.

TOC lines for the libraries above, in load order (the paths are the `.pkgmeta` folder names):

```text
#@no-lib-strip@
Libs\LibStub\LibStub.lua
Libs\CallbackHandler-1.0\CallbackHandler-1.0.xml
Libs\AceDB-3.0\AceDB-3.0.xml
Libs\AceComm-3.0\AceComm-3.0.xml
Libs\LibDataBroker-1.1\LibDataBroker-1.1.lua
Libs\HereBeDragons\HereBeDragons-2.0.lua
#@end-no-lib-strip@
```

### AceDB-3.0 data on Forever

AceDB builds its keys when it loads. On Forever (regional unique names with surnames, realms
grouped by ruleset) the versions disagree. For a character "Aelinor Dawnstrider" on a PvE realm
"Nightslayer" (Lua 5.1 test of the real AceDB files):

| AceDB-3.0 MINOR | `db.char` key | `db.realm` key |
|---|---|---|
| 33 (Release-r1403) | `Aelinor - Nightslayer` (no surname: two Aelinors on one realm share it) | `Nightslayer` |
| 36 (trunk 2026-09-18) | `Aelinor - PvE` | `PvE` |
| 37 (trunk 2026-09-25) | `Aelinor Dawnstrider - PvE` | `PvE` |
| 38, 39 (master) | `Aelinor Dawnstrider` | `PvE` (`Hardcore`, `RP`, `PvP` on those realms) |

Retail and Classic get `Name - Realm` from both 33 and 39. Profiles (`db.profile`) and `db.global`
are not affected, only the per-character choice of profile and the char, realm and factionrealm
sections. If the addon embeds master from its first Forever release, nothing needs migrating. If a
release with an older AceDB ever reached Forever players, copy their data to the new keys once,
before `AceDB:New`:

<details>
<summary>Migration (tested under Lua 5.1 with AceDB r1403 data and master)</summary>

```lua
local function MigrateForeverAceDBKeys(sv)
	if type(sv) ~= "table" or not (RegionalUniqueNamesEnabled and RegionalUniqueNamesEnabled()) then return end
	local name, surname = UnitNameUnmodified("player")
	local fullName = surname and (name .. " " .. surname) or name
	local realm = GetRealmName()
	local ruleset = "PvE"
	if C_GameRules.IsGameRuleActive(Enum.GameRule.HardcoreRuleset) then
		ruleset = "Hardcore"
	elseif C_GameRules.IsGameRuleActive(Enum.GameRule.RPRuleset) then
		ruleset = "RP"
	elseif C_GameRules.IsGameRuleActive(Enum.GameRule.PvPRuleset) then
		ruleset = "PvP"
	end
	local faction = UnitFactionGroup("player")
	local function copy(section, oldKeys, newKey)
		local t = sv[section]
		if type(t) ~= "table" or t[newKey] ~= nil then return end
		for _, old in ipairs(oldKeys) do
			if t[old] ~= nil then
				t[newKey] = t[old] -- copy, do not move: with r1403 two characters could share one key
				return
			end
		end
	end
	local oldCharKeys = { fullName .. " - " .. ruleset, name .. " - " .. ruleset, name .. " - " .. realm }
	copy("profileKeys", oldCharKeys, fullName)
	copy("char", oldCharKeys, fullName)
	copy("realm", { realm }, ruleset)
	if faction then
		copy("factionrealm", { faction .. " - " .. realm }, faction .. " - " .. ruleset)
	end
end

-- in ADDON_LOADED (or OnInitialize), before the database is created:
MigrateForeverAceDBKeys(TxExampleDB)
ns.db = LibStub("AceDB-3.0"):New("TxExampleDB", defaults, true)
```

</details>

Without AceDB, key per-character data by `UnitGUID("player")`: Forever names carry a surname,
and the per-character WTF folders changed during the beta.

## Developing

1. **Get the libraries** once, and again whenever the pin in `.pkgmeta` changes
   (`Libs/` is git-ignored):

   ```sh
   git clone --depth 1 --branch v1.0.0 https://github.com/YOUR-ORG/LibTx-1.0 Libs/LibTx-1.0
   ```

2. **Link the repository into the game** with the toolkit's `devsetup` scripts
   (`link-addons.sh` on macOS with a symlink, `link-addons.ps1` on Windows with a directory
   junction). Until the Forever beta goes offline on 2026-10-19 it lives in `_classic_beta_`; run
   `list` first to see the folders (toolkit `devsetup/README.md`, section 3). macOS:

   ```sh
   bash ~/dev/wow-forever-toolkit/devsetup/link-addons.sh link -f _classic_beta_ ~/dev/Tx_Example
   ```

   Windows (PowerShell):

   ```powershell
   powershell -ExecutionPolicy Bypass -File D:\dev\wow-forever-toolkit\devsetup\link-addons.ps1 link -Flavor _classic_beta_ D:\dev\Tx_Example
   ```

   The folder in `Interface/AddOns` must be named exactly `Tx_Example`, like the TOC.
3. In game: `/reload` after every change; install BugGrabber + BugSack to see errors.
4. Before you push, from the repository root (macOS Terminal or Git Bash; on the Mac write `luajit`
   for `lua`, and on Windows `py` for `python3`):

   ```sh
   find . -name '*.lua' -not -path './Libs/*' -not -path './.release/*' -print0 | xargs -0 -I{} lua -e "assert(loadfile([[{}]]))"
   luacheck .
   bash .github/scripts/check-toc.sh
   python3 .github/scripts/check_paths.py .
   bash tests/harness/run.sh
   ```

   Every pull request also gets a test zip: open the PR's **Lint** run and download the
   `test-package` artifact.

### Smoke test (`tests/harness`)

`tests/harness/run.sh` loads the addon the way a game client does, in plain Lua 5.1 with stub
WoW APIs: it picks the TOC the client would read and applies its game-type gate, runs every listed
file in order (libraries included, so a missing or misnamed library fails with "Cannot find a
library instance"), fires `ADDON_LOADED` and `PLAYER_LOGIN`, checks the SavedVariables, looks for
globals that `.luacheckrc` does not list, runs every `/command` with `help` and `version`, and calls
the addon compartment functions. It does this for Forever (the current and a pre-70170 beta build),
for retail and Classic Era (where the gate must keep a Forever-only addon off, or where
`SUPPORTED_FLAVORS` must include the client), and in German when `Locales/deDE.lua` exists. It is
no substitute for the game: Blizzard's own UI code is not loaded.

It needs Lua 5.1 or LuaJIT (macOS: `brew install luajit`; Windows: `scoop install lua-for-windows`
and Git Bash) and the libraries in `Libs/` (step 1):

```sh
bash tests/harness/run.sh
SMOKE_SLASH=toggle,options,reset SMOKE_COMBAT=options bash tests/harness/run.sh
```

The second form also runs the listed `/command` subcommands and, for an addon with the
HelloAzeroth sample's combat queue, checks that `options` waits until combat ends. The Lint
workflow runs `run.sh` on the packaged folder of every test zip (`.release/Tx_Example`), after
`check-toc.sh --packaged` has checked that the zip holds every file the TOC lists.

### Scripts and the executable bit

CI fails when a `.sh` file is not stored as executable (mode 100755). Git for Windows does not
record the bit, so a script added from Windows needs it set by hand before the commit:

```sh
git update-index --chmod=+x path/to/script.sh
```

### Editor

`.vscode/extensions.json` recommends the WoW API, TOC and EditorConfig extensions, and `.luarc.json`
tells the Lua language server that this is Lua 5.1 and that `WOW_PROJECT_CAMELOT` exists. Turn on
the WoW API extension's FrameXML annotations (`wowAPI.luals.frameXML`) in your own user settings,
or `Settings` and other Blizzard globals show as undefined. Do not commit `.vscode/settings.json`:
the extension writes machine-specific paths into it.

## Releasing

Push a tag; CI does the rest. Details, checklist and first-time setup: RELEASING.md.

```sh
git tag -a v1.0.0 -m v1.0.0 && git push origin v1.0.0
```

The packager uploads the whole `CHANGELOG.md` as the release notes, so it holds only text for
players: newest version first, the version's heading renamed from "Unreleased" before the tag,
and the next "Unreleased" heading added only after the tag is pushed.

CurseForge uploads stay off until a release manager sets the repository variable
`CURSEFORGE_UPLOADS` to `on`, after CurseForge has approved the project; the first CurseForge
file is uploaded by hand (RELEASING.md, "First publication on CurseForge"). Wago and the GitHub
Release do not depend on the variable.

## This template and the HelloAzeroth sample

The starter addon `wow-addon-sample` (HelloAzeroth) and this template use the same mechanisms
(one unsuffixed TOC, the BigWigs packager pinned to `0f24d21`, tag-driven releases, Lua 5.1
compile plus luacheck, the same `.gitattributes`, `.editorconfig` and path lint). Where they
differ, both ways work; this is which one to copy:

| Topic | This template | HelloAzeroth sample | Copy |
|---|---|---|---|
| `## Interface` and game-type gate | `16001` with `## AllowLoadGameType: camelot` and `## ExcludeLoadGameType: standard, classic`; to support retail or Classic Era, add `120105`, `11509` and delete the gate | `11509, 16001, 120105`, no gate | the template's for a Forever-only addon; the sample's line when one zip serves Forever, retail and Classic Era |
| Flavor detection | `LibTx:GetFlavor()` in the shared library, `SUPPORTED_FLAVORS` guard in `Core.lua` | `Flavor.lua` inside the addon | the template's: one place to fix for every addon if Blizzard renames "camelot" |
| SavedVariables | `TxExampleDB` with `dbVersion`, defaults filled in place | `HelloAzerothDB` with `schemaVersion`, `DEFAULTS` and `MIGRATIONS` (migrations run before defaults are filled) | the sample's `Database.lua` once the layout changes; keep the field name `dbVersion` (CONTRIBUTING.md) |
| Slash command | `/txexample` with `version` (addon version, flavor, interface, build, OS for bug reports) | `/helloazeroth` and `/hazeroth` with a subcommand table | both follow the rule of one unique key and command per addon; keep the template's `version` command |
| Settings, compartment, combat queue | not included | Settings API panel, addon compartment entry from the TOC, out-of-combat queue | the sample's files with the changes its README lists ("Copying features into a team addon"): they depend on each other and on the sample's `Flavor.lua` |
| Libraries | LibTx-1.0 external, third-party pins ready to uncomment | none; three commented example forms | the template's `.pkgmeta` |
| `.gitignore` | `Libs/` ignored (there is always an external) | `Libs/` commented out until the first external | either |
| Lint workflow | actions pinned by commit SHA with `persist-credentials: false`, Dependabot, timeouts, exec-bit check, `check-toc.sh`, path lint, test zip on every pull request, checked against its TOC and loaded in the smoke test | actions pinned by major tag (`@v7`), compile check, luacheck, path lint, exec-bit check, the mock-load harness with Blizzard's UI code | the template's (and the sample's harness when you need Blizzard's widgets and data) |
| Release workflow | refuses tags other than `vX.Y.Z[-beta.N/-alpha.N]` (an `-rc` tag would publish a Release), fork guard, checks that every upload ID has its token, runs the test zip checks before publishing, one release at a time | lint, then the packager | the template's |
| Packager tokens, Subversion step, CurseForge switch | `GH_API_TOKEN` and `GITHUB_OAUTH`, Subversion installed for svn externals, `-p 0` until the repository variable `CURSEFORGE_UPLOADS` is `on` | the same | either |

## License

MIT, see [LICENSE](LICENSE). `LibStub` is in the public domain.
