# Patch-day runbook

How we keep every Tx Studio addon working when Blizzard ships a new client build. Applies to
WoW: Forever first, and to retail and Classic for addons that ship there. Background and sources:
the team's patch-operations research notes (`patching.md`, `forever.md`).

## What changes, and how often

| Kind | Cadence (observed) | Risk for addons |
|---|---|---|
| **Engine patch** (retail patch train: 12.1.5, 12.1.7, ...) | a new retail version every 7-9 weeks, first on the PTR 40-54 days ahead (12.0.1 was on the beta 60 days ahead, but on its PTR only 6) | high: API additions and removals, secret-value rules, Blizzard UI changes |
| **Hotfix build** of the same version | about 1.4 rebuilds a week between patches on retail (79 distinct live builds in the past year, 7 of them patch-day builds) | low, but restriction flags have changed mid-patch (retail build 69404, nine days after 12.1.0) |
| **Forever content update** (raids 2026-12-09; "major updates" spring and summer 2027, as reported) | seasonal | data and zone/quest addons |
| **Server-side hotfix** | any time | invisible in client code; only bug reports show it |

Forever-specific facts to keep in mind:

- Forever is built from the **same client code as retail's next patch**. Of the 217 functions the
  retail 12.1.7 PTR adds over live 12.1.5, 176 were already in Forever beta build 70425. Expect
  retail engine changes to reach Forever, probably in step (inference; Blizzard has not published
  Forever's client cadence).
- The **Forever interface number stayed 16001** (version 1.60.1) through all 16 beta builds while
  the code moved from the 12.1.5 era to the 12.1.7 era. A build can break addons **without**
  a new interface number. Watch builds, not only version numbers.
- The beta changed APIs about weekly: functions were renamed or removed, and `WOW_PROJECT_ID`
  changed from 1 to 18 in build 70170 (2026-10-01).
- There is **no Forever PTR**. The retail PTR carries Forever's code (`Camelot` folders, API docs),
  so read it for early warning, but it runs the retail game type: you cannot test Forever there.
- Retail 12.1.7's PTR opened 2026-10-15. At the usual 40-54 day lead it would go live around
  2026-11-24 to 2026-12-08, within weeks of Forever's launch (inference).

## Early warning: patchwatch

`patchwatch` (in the toolkit repository, `patchwatch/`; still in progress, see its README for the
current state) reads the Gethe/wow-ui-source mirror of Blizzard's UI code and reports, for each
new build: added and removed API functions and events, tightened or loosened restriction and
secret-value annotations, `Blizzard_Deprecated` shims, project-constant changes, the interface
number, and which of those your addon's files reference.

**In CI (set up once per addon repository):** copy `patchwatch/workflows/patchwatch.yml` from the
toolkit to `.github/workflows/patchwatch.yml` (do not copy the `patchwatch` folder itself). The
workflow installs patchwatch with pip from the team's public `wow-forever-toolkit` repository at
the tag `v0.2.0`, so publish and tag the toolkit first (toolkit README, "Publish the toolkit");
set the repository variable `PATCHWATCH_PIP_SPEC` only for another repository name or version,
for example `git+https://github.com/YOUR-ORG/wow-forever-toolkit@v0.2.0#subdirectory=patchwatch`.
Run it once by hand with `since` empty to record the baseline. It runs every 3 hours and keeps one
issue per watched branch (label `patchwatch`), updated when a new build appears. Watch `forever,live,ptr` (default); add
`classic_era` if the addon ships there. It also raises **mirror alerts** (one "[patchwatch] mirror
alerts" issue, commented once per new alert): a watched branch missing from the mirror (the run
fails), `forever` without a new export for 10 days, `forever` carrying a non-1.6x version, a new or
removed mirror branch, a new product in the mirror's exporter, or a branch exporting another
product. Tune them with `PATCHWATCH_STALE_DAYS` and `PATCHWATCH_FAIL_ON_ALERT` (patchwatch README).

**By hand**, from the addon folder, with patchwatch installed (toolkit README, "patchwatch on your
machine"):

```sh
patchwatch fetch
patchwatch builds --branches forever --files
patchwatch diff forever@-1 forever --addon . --md ~/report.md
patchwatch scan . --build forever
patchwatch scan . --build forever --compare live
```

In order: update the local mirror cache; list the newest builds and what they touched; compare the
last build with the newest, with the impact on this addon (the report goes to your home folder,
outside the repository; on Windows write `$HOME\report.md`); check the TOC and the restricted
APIs the addon uses; list the APIs the addon uses that Forever lacks.

Limits to remember: the mirror is exported on demand. On recent patch days that happened the
same day (14:16-15:47 UTC), but one batch on 2025-11-03 carried builds from two weeks earlier, so
treat mirror dates as approximate and also check the game launcher. Undocumented globals, XML
templates and CVars are not covered; server-side hotfixes leave no trace. A clean report is a
hint, not a guarantee.

The mirror's `forever` branch exports product `wow_classic_beta`, and only that product. If
Forever moves to another product at launch (the stress test already runs as `wowf`), the branch
stops getting builds. patchwatch then warns: a stale `forever` after 10 days, and a new branch, a
new exporter product or a changed export product as soon as the mirror adds the new product. It
cannot see the new product before the mirror exports it; for that, use the CDN lookup under
"Launch day" (also in the patchwatch README, "Manual check").

**People still read** the WoWUIDev Discord and the Warcraft Wiki "Patch X/API changes" and
"Planned API changes" pages once a week (the patch captain, below). Blizzard announces
restriction changes there before they ship.

## Roles

- **Patch captain** (rotates per patch): owns this runbook for one patch, opens the tracking
  issue, decides go/no-go for releases, writes the player announcement.
- **Addon owners**: fix and smoke-test their addons, tag releases (release managers).

## Timeline

### When a PTR or test build appears (about 6 weeks ahead)

- [ ] patchwatch issue appears for `ptr` (or `forever`). Captain opens a tracking issue
      "Patch 12.1.7" in the organization and links the reports.
- [ ] Each owner reads the impact section for their addon: removed APIs, tightened restrictions,
      changed events. Create one issue per real problem.
- [ ] Retail-shipping addons: add the PTR interface number to the TOC now (BigWigs does this
      within days). Gate code that needs the new build at runtime with a **feature test**
      (`if C_Foo and C_Foo.NewThing then`). Interface-number gates do not cross flavors:
      `select(4, GetBuildInfo()) >= 120107` is false on Forever (16001) even when Forever has
      the same code.
- [ ] Update library pins if a library (LibTx-1.0, Ace3, ...) ships fixes for the new build.

### A week before

- [ ] Fixes merged and in a beta release (`vX.Y.Z-beta.N`) for testers.
- [ ] Smoke test on the test client if one exists; for Forever, on the newest Forever build.

### Patch day

Blizzard patches usually go live on a Tuesday (US).

- [ ] `patchwatch check` (or the CI issue) shows the new live/forever build. Read its report.
- [ ] Log in to the patched client: `/dump (select(4, GetBuildInfo()))`. Is that number in every TOC?
      If not: add it (keep the old number until the patch is live everywhere), commit, tag a PATCH
      release. Players otherwise see the addon as out of date.
- [ ] Load each addon with only BugSack: no errors after `/reload`, in and out of combat.
- [ ] Tag releases within hours. In the Release log, look for
      `WARNING: No CurseForge game version match for "1.60.2", using "1.60.1"`: CurseForge
      does not know the new game version yet, so the file got another version's label (tested).
      The packager picks by text order, so the label can even be a newer version. Re-check the
      file's game version on CurseForge a day later and correct it there if needed.
- [ ] Check the packager pin: `git ls-remote https://github.com/BigWigsMods/packager refs/heads/master`.
      If master moved and the change matters (Forever fixes), bump the SHA in `lint.yml` and
      `release.yml` (Dependabot is told to leave it alone). Before you move to a new commit or a
      tag, re-check what it does when the CurseForge upload fails (RELEASING.md, "Packager version").

### Day 1 to 3

- [ ] Triage BugSack reports daily (SUPPORT.md). Fix, tag `vX.Y.(Z+1)`. Rolling forward beats
      reverting: BigWigs shipped 7 tags in 2 days for 12.1.5.
- [ ] Pin a "Known issues: patch X" issue in each affected repository and link it on Discord.
- [ ] Close the tracking issue with a short note: what broke, what we would watch earlier next time.

## Launch day, WoW: Forever, 2026-11-04 (15:00 PST, 23:00 UTC)

Blizzard has not said where Forever installs at launch. Three layouts are possible:

- **A. Its own product and folder.** For example `_forever_`. Most likely: the "WoW: Forever -
  Stress Test" already runs as its own Battle.net product, `wowf`.
- **B. A game type inside retail.** Forever and Midnight share `_retail_`, as Plunderstorm did.
  Unlikely.
- **C. The beta slot.** Product `wow_classic_beta`, folder `_classic_beta_`. Unlikely: the beta
  goes offline on Oct 19.

Evidence and sources: `research_notes/WoW Forever addon project playbook/gap_1.md`.

The beta (since build 70170) and the Forever code on the retail 12.1.7 PTR use the game type
`camelot`. If the launch client keeps it, `_Camelot.toc`, the game-type gate from the TOC rule
below and `WOW_PROJECT_ID == WOW_PROJECT_CAMELOT` (18) work the same in every layout; that launch
keeps the name is an inference, and "Internal label" below covers a rename. What changes is the
folder, the addon managers, the upload tags and patch monitoring.

### Before launch: watch the early signs

| When | Check | Who |
|---|---|---|
| now to Oct 19 | Battle.net > World of Warcraft > Game Version > "WoW: Forever - Stress Test" (In Development) > Install. Run `bash devsetup/link-addons.sh list` (macOS) and `link-addons.ps1 list` (Windows) in the toolkit. Note the folder, the `.build.info` product and version, and the app or exe name. A new folder there is the A folder for the stress test. While the beta is installed too, `list` shows `-f forever -> ambiguous` with both folders: link by folder name (`-f _classic_beta_`, `-f _forever_`). | both |
| Oct 19 | Stress test. The beta goes offline that day (Blizzard forum, as reported). Smoke-test each addon on the stress-test client if you can log in. | both |
| Oct 21/22 | Beta ends. From here until Oct 27 there may be no Forever client. | |
| Oct 27 to Nov 3 | Early name reservation: pack owners can start the client and create characters. Repeat the `list` check; this is probably the launch install. | pack owner |
| any day | Has Gethe's mirror added the new product? patchwatch's mirror alerts report a new branch, a new product in `ExportInterfaceFiles.ps1` (`automation` branch) and a branch that exports another product; by hand: `git ls-remote --heads https://github.com/Gethe/wow-ui-source`. Until the product is added, the `forever` branch (product `wow_classic_beta`) stays frozen at 1.60.1.70425 and patchwatch raises a stale-branch alert after 10 days. When a branch for the launch product appears, add it to `PATCHWATCH_BRANCHES`. | captain |
| any day | Ask Blizzard's CDN which folder a product installs to, without installing it (see the commands below). | captain |

The folder lookup is the method instawow uses to build its product table: `/v2/summary` lists the
products, and the product config's `shared_container_default_subfolder` names the folder.
**[untested]** The Blizzard hosts were blocked from the research container; the commands were run
only against canned responses. Run them on your own machine. The first line lists every WoW
product (look for new `wow*` names such as the stress test's `wowf`); the next three print the
install folder of the product in `p`. `curl -f` prints an error when a request fails; an empty
result without an error means the product config names no folder.

macOS (bash or zsh, `jq` from Homebrew), Linux or WSL, or Git Bash with Scoop's `jq`:

```sh
curl -fsS https://us.version.battle.net/v2/summary | awk -F'|' 'NR > 2 && $1 ~ /^wow/ { print $1 }' | sort -u
p=wowf
cfg=$(curl -fsS "https://us.version.battle.net/$p/versions" | awk -F'|' '$1 == "us" { print $NF }' | tr -d '\r')
curl -fsS "https://us.cdn.blizzard.com/tpr/configs/data/${cfg:0:2}/${cfg:2:2}/$cfg" | jq -r '.all.config.shared_container_default_subfolder'
```

Windows (PowerShell 5.1 or 7; `curl.exe` ships with Windows 10 and 11, and no `jq` is needed):

```powershell
curl.exe -fsS https://us.version.battle.net/v2/summary | ForEach-Object { ($_ -split '\|')[0] } | Where-Object { $_ -like 'wow*' } | Sort-Object -Unique
$p = 'wowf'
$cfg = (curl.exe -fsS "https://us.version.battle.net/$p/versions" | Where-Object { $_ -like 'us|*' } | Select-Object -First 1).Trim().Split('|')[-1]
((curl.exe -fsS "https://us.cdn.blizzard.com/tpr/configs/data/$($cfg.Substring(0,2))/$($cfg.Substring(2,2))/$cfg") -join "`n" | ConvertFrom-Json).all.config.shared_container_default_subfolder
```

The same commands, with notes, are in the patchwatch README ("Manual check").

### First hour: which layout is it?

1. Battle.net > World of Warcraft > Game Version "World of Warcraft: Forever" > gear >
   Show in Explorer/Finder, and run `bash devsetup/link-addons.sh list` (Windows: `link-addons.ps1 list`):
   - **a new folder** (not `_retail_`, not `_classic_beta_`): layout **A**
   - **`_classic_beta_`**: layout **C**
   - **no Forever entry of its own**, with Forever picked inside the retail client or opened from
     `_retail_`: layout **B**
2. In game on Forever: `/dump WOW_PROJECT_ID, WOW_PROJECT_CAMELOT, (select(4, GetBuildInfo()))`.
   Expected: `18, 18, 16001` (or a newer 160xx). The parentheses keep only the interface number;
   without them `/dump` also prints the last two values of `GetBuildInfo()`.
   - A retail number such as 120107 in the third value means B with a shared build. See B below.
3. Post the folder in the team channel and update the folder table in SUPPORT.md.

### What to do in each layout

**A. Own product and folder (expected)**
- [ ] **Dev links.** While the old `_classic_beta_` is still installed, `-f forever` /
      `-Flavor forever` finds two Forever folders, lists both with product and build, and stops.
      Link with the new folder's name (`-f _forever_`, or pin `WOW_FOREVER_FOLDER`) and re-run
      `link` for every checkout on both machines. Uninstall the beta in Battle.net once nobody
      needs it; `forever` then resolves to the new folder by itself.
- [ ] **TOCs.** No change unless step 2 showed a new interface number. If it did, add the number
      to every TOC and release.
- [ ] **Addon managers.**
  - **WowUp 2.24.x** skips product.db entries in folders it does not know ("Invalid client
    type"), so it will not show the Forever install until it is updated. For the Anniversary
    folder that took 1 to 2 days.
  - Do **not** add the Forever install to WowUp by hand: WowUp classifies a manual install by
    exe name, so `Wow.exe` is labelled Retail.
  - **instawow** works after the client has started once: it reads `lastAddonVersion` from
    `WTF/Config.wtf`.
  - **CurseForge app**: unknown. Post the manual-install message below.
- [ ] **Uploads.** No change: CurseForge type 88568, Wago `forever`.
- [ ] **Monitoring.** The mirror's `forever` branch is stalled until the new product is added (see
      above). Meanwhile, diff `ptr` (Forever code ships there under `Camelot\`) and read the client
      itself.
- [ ] **SavedVariables.** The new folder has its own `WTF`. Beta characters are deleted anyway, so
      there is nothing to migrate.

**B. Game type inside retail (shared `_retail_`)**
- [ ] **Dev links.** Set `WOW_FOREVER_FOLDER=_retail_` on both machines: shell profile on macOS, a
      user environment variable on Windows, or `-ForeverFolder _retail_`. Without it, `forever` is
      ambiguous while the stale beta folder is installed, or falls back to it whenever Midnight was
      the last game run. Every link now loads in both game types, and the tools warn about this.
- [ ] **TOCs.** Forever reads `_Camelot.toc`, then `_Mainline.toc`, then the bare TOC. Midnight
      reads `_Standard.toc`, then `_Mainline.toc`, then the bare TOC. Release before players install,
      following the TOC rule below:
  - Forever-only addons need the gate `## AllowLoadGameType: camelot` plus
    `## ExcludeLoadGameType: standard, classic` (already in the template's TOC).
  - Retail-only `_Mainline.toc` files need `## AllowLoadGameType: standard`. Otherwise Forever loads
    them.
  - If step 2 showed a retail interface number, list it in the Forever TOC too, for example
    `## Interface: 16001, 120107`. The BigWigs packager then also tags the upload as Retail, because it
    maps any 1201xx to retail. That is what managers need in B. The template's `check-toc.sh`
    normally refuses the Forever-only gate next to a retail number; for layout B add this line to
    the TOC, and remove it together with the retail number once Forever has its own client:
    `# check-toc: allow-gate-with-retail-interface`. The check then passes with a notice (Classic
    numbers next to the gate still fail). Keep `SUPPORTED_FLAVORS = { forever = true }`: in B the
    client reports `WOW_PROJECT_ID` 18, so LibTx still says `forever`.
- [ ] **Addon managers.** The CurseForge app, WowUp and instawow will see only a Retail install and
      only offer Retail-tagged files. Post the manual-install message. As a stopgap, upload the
      Forever file with a Retail game version too: the TOC gate keeps it from loading on Midnight.
- [ ] **Code.** Detect Forever with `WOW_PROJECT_ID == WOW_PROJECT_CAMELOT`. Interface-band checks
      (16000-19999) fail if Forever reports retail's number.
- [ ] **SavedVariables.** One `WTF` folder probably serves both game types (unverified). Check
      `WTF/Account/<ACCOUNT>/SavedVariables/<Addon>.lua` after a Forever session. If an addon loads in
      both, key its account-wide data by `WOW_PROJECT_ID`.
- [ ] **Monitoring.** Forever code then arrives on the mirror's `live` and `ptr` branches; `forever`
      stalls. Watch `Camelot\` paths and `camelot` TOC lines in the `live` diffs.

**C. Beta slot kept (`_classic_beta_`)**
- [ ] Nothing changes for dev links: `forever` still resolves to `_classic_beta_` (if the stress-test
      folder is still installed, `forever` is ambiguous: link with `-f _classic_beta_`). WowUp 2.24.0 or
      later and instawow 7.2.0 or later already map this folder to Forever. The CurseForge app
      behaves as it did in the beta. The mirror keeps exporting `wow_classic_beta` to `forever`, on
      demand.

**Every layout, first hour**
- [ ] **Interface number:** step 2. If it changed (for example 16002), update every TOC and tag
      releases. Expect the CurseForge game-version warning above.
- [ ] **Internal label:** does `WOW_PROJECT_CAMELOT` still exist, and do `_Camelot.toc` and
      `camelot`-gated addons still load (the AddOn List marks none of them, for example "Wrong game
      type")? If Blizzard renamed it:
  1. fix `LibTx:GetFlavor()` once and release LibTx;
  2. bump the pin in every addon;
  3. rename any `_Camelot.toc`, and add the new name to every `## AllowLoadGameType:` gate
     (`forever` is the likely one: the beta client already accepts it as an alias);
  4. release.
- [ ] **Smoke test.** Each addon loads, saves settings across `/reload` *and* a full client
      restart, and works in and out of combat.

### TOC rule that works in A, B and C

| Addon | What to ship |
|---|---|
| **Forever-only** | One bare `<Name>.toc` with `## Interface: 16001`, `## AllowLoadGameType: camelot` and `## ExcludeLoadGameType: standard, classic` (the template's `Tx_Example.toc`). |
| **Several flavors** | One bare TOC listing every interface (for example `11509, 16001, 120105`) and no header gate, with Forever-only *files* gated `[AllowLoadGameType camelot][ExcludeLoadGameType standard, classic]`. |

**Use only `camelot`, `standard` and `classic` in these gates.** What a client does with a
game-type word was tested on real clients by the wowless project (all nine products it models on
2026-09-24; the Forever beta client again on 2026-10-09 and 2026-10-13, the TBC Anniversary client
on 2026-10-13):
- A condition whose words the client does not know at all is ignored. An unknown word never makes
  a condition pass when the client knows another word in the list.
- Retail and the Classic clients do **not** know `camelot`. So `[AllowLoadGameType camelot]`, or
  `camelot, forever`, on its own loads on every client.
- Every tested client knows `standard` (active on retail only) and `classic` (active on the Classic
  flavors only). The Exclude line therefore keeps the addon off retail and Classic whatever a
  client does with an Allow line it cannot match. No source says how the client treats an
  addon-level `## AllowLoadGameType:` header whose words are all unknown, and with the Exclude line
  that question no longer matters.
- `forever` works as an alias on the Forever beta client, but no Blizzard TOC uses it (forever,
  live and ptr branches), the real TBC Anniversary client treats it as an unknown word, and nobody
  has tested it on retail or Classic Era. Leave it out; add it to the Allow line only if the launch
  client drops "camelot" ("Internal label" above).

**Forever-only.** The gate changes nothing on Forever. It keeps the addon out of Midnight if B ever
shares the folder, and out of retail or Classic if a player unzips it into the wrong folder.

| Tool | Result |
|---|---|
| Packager | reads neither gate line; tags 1.60.1 only and keeps both lines in the zip (master `0f24d21`, dry run) |
| WowUp, instawow | do not read the gate; they fall back to the bare TOC |
| A client that excludes the addon | probably lists it as "Wrong game type" (`ADDON_WRONG_GAME_TYPE` in the Forever 70338 strings; not seen in game) |
| Hypothetical "camelot" rename | the Exclude line still works; the Allow line needs the new name (step 3 of "Internal label") |

**Several flavors.** Split TOCs only when the file lists differ:
- Forever gets `<Name>_Camelot.toc`, never `_Forever.toc`.
- A retail `<Name>_Mainline.toc` carries `## AllowLoadGameType: standard`. Forever falls back to
  `_Mainline.toc` when it has no `_Camelot.toc` (wowless, tested on the Forever beta client).

**Never ship an `## Interface: 00000` "unsupported client" stub with the BigWigs packager.** It reads
the stub as retail version 0.0.0, and the CurseForge and Wago uploads then fall back to the newest
retail version. Simulated against a local mock of both sites (twice, the last time on 2026-10-16 with
the packager at `0f24d21`): the file was tagged retail 12.1.5 next to Forever 1.60.1, so it would be
offered to Midnight players. The template's `check-toc.sh` rejects such a TOC.

## Out-of-date addons, and what to tell players

The client marks an addon whose TOC interface it does not accept as out of date
(`C_AddOns.GetAddOnInfo` reason `INTERFACE_VERSION`) and offers "Disable" or "Load". The AddOn
list's "Load out of date AddOns" box switches the check off
(`C_AddOns.SetAddonVersionCheck(false)`). Which numbers count as out of date (exact match, or
older than x.y.0) is engine code and documented inconsistently; the Warcraft Wiki says the box is
cleared at every client patch. Our rule: **ship the exact current number for every client, and
tell players to update rather than tick the box.**

## Deprecations

Blizzard keeps removed functions alive for a while as `Blizzard_Deprecated` shims that load only
with the CVar `loadDeprecationFallbacks`. Shims disappear at expansion pre-patches (all 11.x shims
vanished in 12.0.0) **and** at point patches (12.1.5 removed ten shim addons). patchwatch flags a
removed function that a shim still provides as a warning: fix it then, not when the shim goes.
Develop with `/console loadDeprecationFallbacks 0`.

## Libraries are part of the blast radius

When LibTx-1.0, Ace3 or another embedded library ships a fix for a patch, it reaches players only
when **every** addon that embeds it updates its `.pkgmeta` pin and releases. The captain lists the
affected addons in the tracking issue.

## Message templates

Known-issues issue (pin it):

```markdown
**Patch 12.1.7 / Forever build NNNNN: known issues**
- [x] Lua error when opening the bag window (fixed in v1.4.1, update your addon)
- [ ] Tooltip lines missing in combat: Blizzard restriction, no workaround yet
Seeing something else? Open a bug report with your BugSack text: <link to the issue form>
```

Discord:

```text
Tx Bags v1.4.1 is out for WoW: Forever build NNNNN. It fixes <one line>.
Update in your addon manager. Still broken? Report it: <link>
```

Manual install while an addon manager does not know the Forever install yet (launch day). Post it
on Discord; SUPPORT.md ("Your addon manager doesn't show WoW: Forever yet?") has the same steps.
Fill in the folder from "First hour" above:

```markdown
**Your addon manager doesn't show WoW: Forever yet?** Install by hand until it updates:
1. Download the newest file marked **WoW: Forever** from <CurseForge Files tab or GitHub Releases link>.
2. In the Battle.net app pick **World of Warcraft: Forever**, click the gear next to Play, choose
   **Show in Explorer** (Windows) or **Show in Finder** (Mac), and open `<FOREVER FOLDER>\Interface\AddOns`
   (create `Interface` and `AddOns` if they are missing).
3. Unzip so that you get `AddOns\Tx_Bags\Tx_Bags.toc`, not `AddOns\Tx_Bags\Tx_Bags\...`.
4. Restart the game and check the AddOns button on the character screen.
Don't add the Forever folder to your addon manager as a "Retail" install: it would install the wrong files.
```
