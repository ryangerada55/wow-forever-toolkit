# patchwatch

patchwatch tells an addon team what a new World of Warcraft build changes for its addons. It was
written for WoW: Forever (launch 2026-11-04) and also works for retail and the Classic flavors.

For every new build it reports:

- **API changes**, parsed from Blizzard's generated API documentation (`Blizzard_APIDocumentationGenerated`):
  - added and removed functions, events and tables (enums, structures, constants)
  - changed arguments, returns, event payloads, enum values and structure fields
  - changed restriction and secret-value annotations, such as `SecretArguments`, `SecretReturns`,
    `SecretWhen*`, `ConditionalSecret`, `NeverSecret`, `HasRestrictions`, `IsProtectedFunction`
    and `Requires*`, each marked tightened or loosened
- **Other build changes:**
  - `Blizzard_Deprecated` shim files added or removed, with the names each shim defines
  - `Blizzard_ProjectConstants` changes (for example `WOW_PROJECT_CAMELOT` appearing in Forever build 70170)
  - the Interface number change
- **Addon impact:**
  - which of those APIs your addon's `.lua`/`.xml` files reference, with `file:line`
  - whether the TOC that client loads (`_Camelot`, `_Mainline`, `_Vanilla`, ... or unsuffixed)
    declares the new Interface number, and the line to use if not
- **Mirror health** (`check`): warnings when the mirror could hide a new build from you. A watched
  branch is missing, or has had no export for N days; the `forever` branch carries a version
  outside WoW: Forever's 1.6x band, or any branch switches to another game; mirror branches appear
  or disappear; the exporter's product list or a branch's export product changes.
- **Output** as Markdown that fits in a GitHub issue, plus JSON. Options make the run exit
  non-zero on breaking changes or on mirror alerts.

The source of truth is the [Gethe/wow-ui-source](https://github.com/Gethe/wow-ui-source) mirror of
Blizzard's UI code. The tool reads it over git, so you do not need the game installed.

## Requirements

- Python 3.9 or newer. It uses only the standard library.
- Git 2.29 or newer on `PATH`. It must support partial clone and `git fetch --stdin`.
- Network access to `github.com`.

| | macOS | Windows |
|---|---|---|
| Python | `python3`: the Xcode Command Line Tools ship 3.9; python.org or Homebrew give newer versions | `py` launcher from the python.org installer, or `python` from the Microsoft Store |
| Git | `xcode-select --install` or `brew install git` | [Git for Windows](https://git-scm.com/download/win), with the "Git from the command line" option |

## Install

Run these from the folder that contains `patchwatch/`, for example the toolkit repository root.

macOS / Linux (Terminal):

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install ./patchwatch
patchwatch --version
```

Windows (PowerShell). If PowerShell refuses to run `Activate.ps1`, run
`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once and try again.

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install .\patchwatch
patchwatch --version
```

Windows (cmd.exe): `py -3 -m venv .venv`, then `.venv\Scripts\activate.bat`, then
`python -m pip install .\patchwatch`.

You can also skip installing. From inside the `patchwatch/` folder, run `python3 -m patchwatch ...`
on macOS or `py -m patchwatch ...` on Windows.

Once a venv is active, `python` means the venv's interpreter on every OS. Without one, use `python3`
on macOS and `py` on Windows. On Windows, `python` can open the Microsoft Store stub instead of
running Python.

### Paths with spaces

Quote every path that contains spaces. WoW install paths usually do. macOS:

```sh
patchwatch scan "/Applications/World of Warcraft/_classic_beta_/Interface/AddOns/MyAddon" --build forever
```

Windows (PowerShell or cmd.exe):

```powershell
patchwatch scan "C:\Program Files (x86)\World of Warcraft\_classic_beta_\Interface\AddOns\MyAddon" --build forever
```

On Windows, **do not end a quoted path with a backslash**. Windows argument parsing reads `"C:\My Addons\"`
as `C:\My Addons"`. Write `"C:\My Addons"` instead. Forward slashes also work on Windows:
`"C:/My Addons/MyAddon"`.

During the beta, Forever's addon folder is `_classic_beta_`. It may change at launch, so pass your
addon folder explicitly and do not rely on a fixed path.

## Where data is kept

patchwatch keeps a cache folder that holds a bare, blobless clone of the mirror (`wow-ui-source.git`)
and gzipped parsed snapshots (`snapshots/`). Its default location:

| OS | Default cache folder |
|---|---|
| macOS | `~/Library/Caches/patchwatch` |
| Windows | `%LOCALAPPDATA%\patchwatch\Cache` |
| Linux | `$XDG_CACHE_HOME/patchwatch`, or `~/.cache/patchwatch` |

Set `PATCHWATCH_CACHE_DIR` or pass `--cache-dir` to use another folder. The first fetch of the seven
default branches downloads commits and trees only, about 7 MB, in a few seconds. File contents are
fetched in one batch per build, and only for the folders patchwatch reads (about 0.5 MB per build).

## Usage

| Command | What it does |
|---|---|
| `patchwatch fetch` | create or update the cache (default branches) |
| `patchwatch builds --branches forever --files` | list builds, with the files and API-doc files each changed |
| `patchwatch diff forever@first forever` | the first Forever beta build against the newest |
| `patchwatch diff live@12.1.0 live@12.1.5 --addon ./MyAddon --md ~/report.md` | two builds, with the impact on an addon, as Markdown |
| `patchwatch scan ./MyAddon --build forever` | TOC check and the restricted APIs the addon uses |
| `patchwatch scan ./MyAddon --build forever --compare live` | APIs the addon uses that Forever lacks |
| `patchwatch check --state state.json --branches forever,live --addon ./MyAddon --out-dir out` | CI mode (below) |
| `patchwatch dump forever --summary` | parsed counts, deprecated shims, project constants |

Write reports (`--md`, `--json`) outside your repositories, for example into your home folder:
a `report.md` left in an addon repository would be packaged into the zip if someone commits it.

```sh
patchwatch fetch
patchwatch builds --branches forever --files
patchwatch diff forever@-1 forever --addon ~/dev/Tx_Bags --md ~/report.md
patchwatch scan ~/dev/Tx_Bags --build forever --compare live
patchwatch check --state ~/patchwatch-state.json --branches forever,live --stale-days forever=7 --fail-on-alert missing
```

**Build specs.** Commands that take a build accept these forms:

| Spec | Meaning |
|---|---|
| `forever`, `forever@latest` | newest build on the branch |
| `forever@first` | oldest build on the branch |
| `forever@-1` | the build before the newest (`-N` goes N builds back) |
| `live@12.1.0` | newest build of that version on the branch |
| `forever@69876`, `forever@1.60.1.69876` | that build |
| `live@2026-08-20` | newest build on or before that date (UTC) |
| `tag:12.1.0` | a mirror tag (see Limitations) |
| a commit id | that commit |
| `dir:PATH` | a local checkout, or a `Blizzard_APIDocumentationGenerated` folder |

**Branches.** The default set is `forever`, `live`, `ptr`, `beta`, `classic_era`, `classic` and
`classic_anniversary`. Add `ptr2`, `classic_era_ptr` or others with `--branches`. Watch only the
branches you ship for: a Classic-only addon checked against `live` gets a "not declared" TOC result.

**`check` (CI mode).**
1. It reads the state file and fetches the branches.
2. For each branch with a new build, it compares the last seen build with the newest one and scans
   the addons.
3. It writes `out/<branch>.md`, `out/<branch>.json` and `out/summary.json`, then updates the state.

On the first run with no state, it only records the current build (`--first-run previous` compares
the newest build with the one before it instead). `--since first|-N|YYYY-MM-DD` ignores the state
for one run; a branch that has too few builds for it (a branch the mirror just created has one)
gets its current build recorded as the baseline, with a note, instead of failing the run.
`--notify-on any|api|breaking|impact` decides which new builds count as report-worthy in
`summary.json`.

**Mirror alerts (`check`).** A quiet report is only as good as the mirror. Gethe's mirror exports
on demand, and its `forever` branch follows exactly one product, `wow_classic_beta`; if WoW:
Forever moves to another product at launch, that branch simply stops. So every `check` run also
looks at the mirror itself and prints a `WARNING:` line for each problem:

| Alert | When | Key |
|---|---|---|
| missing branch | a watched branch is not in the mirror (or not in the cache with `--no-fetch`/`--offline`). The other branches are still checked | `missing:<branch>` |
| stale branch | the newest export on a watched branch is older than its limit. `--stale-days N` (every branch) or `--stale-days forever=7,ptr=60` (per branch; repeatable; 0 = off). Default: `forever` 10 days, other branches off. The longest gaps between exports up to 2026-10-16: just under 5 days on `forever` (4.9, since the beta started on 2026-09-16), and over the year before, 22 days on `live`, 45 on `ptr` and 85 on `classic_era` | `stale:<branch>` |
| Forever version band | the newest build on `forever` (or one since the last run) is not 1.60-1.69: the beta product now carries another game, or Forever left the 16xxx interface band the BigWigs packager maps to Forever | `forever-band:<band>` |
| version band change | a branch's builds moved to another game since the last run (for example `classic_era_ptr` going from 1.15 to 2.5) | `band-change:<branch>:<old>-><new>` |
| new or removed branch | the mirror's branch list (`git ls-remote --heads`) differs from the last run | `new-branch:<name>`, `removed-branch:<name>` |
| exporter products | the product list the mirror's exporter accepts (`ValidateSet` of `$Product` in `ExportInterfaceFiles.ps1` on the `automation` branch) gained or lost a product; `--no-exporter-check` skips it | `exporter-added:...`, `exporter-removed:...` |
| export product | a watched branch's `.github/workflows/export.yml` now exports another product (for `forever`: the launch switch) | `export-product:<branch>:<product>` |

Alerts go to stderr, to `summary.json` (`alerts`, and `new_alerts` for the ones the previous run
did not have) and to `out/alerts.md` (a Markdown body with the hidden marker
`<!-- patchwatch:alerts -->`). The state file keeps the current alert keys, so CI can notify once
per new alert. By default alerts do not change the exit code; `--fail-on-alert missing` exits 4
while a watched branch is missing, `--fail-on-alert any` on every alert. `--now ISO-TIME` replays a
run as if it were that time (for tests). Tested with unit tests, a fake git mirror, a copy of the
real mirror (13 branches, the 12-product exporter list) and the GitHub mirror itself.

**Exit codes:**

| Code | Meaning |
|---|---|
| `0` | success |
| `1` | error (git missing, network, bad state file) |
| `2` | bad command line |
| `3` | the `--fail-on` condition was met |
| `4` | `check` only: the `--fail-on-alert` condition was met (mirror alerts) |

`--fail-on` takes three values:
- `never` (default)
- `breaking`: any breaking API change, or an addon problem
- `impact`: only a breaking change that hits a scanned addon, or a TOC that does not declare the new
  Interface number

### Severity

| Severity | Meaning |
|---|---|
| breaking | One of: a removed function, event, table, enum value or field; a new required argument; a removed return or payload value; a tightened restriction (for example a new `SecretReturns` or `SecretWhen*`, or `SecretArguments` going from `AllowedWhenTainted` to `AllowedWhenUntainted`). |
| warning | A change that may break callers. Examples: a changed argument type, a return that may now be `nil`, a function removed from the docs but still provided by a `Blizzard_Deprecated` shim (which loads only with the CVar `loadDeprecationFallbacks`), or any finding on a widget method. |
| info | An addition, a loosened restriction, or a change in documentation attributes only. |

## GitHub Actions

`workflows/patchwatch.yml` is a ready-to-copy workflow. It installs patchwatch with pip from the
team's toolkit repository **at a tag**, so every run uses the same, reviewed version:

```text
git+https://github.com/<owner of the addon repository>/wow-forever-toolkit@v0.2.0#subdirectory=patchwatch
```

To use it:

1. **Once per team: publish the toolkit and tag it.** The toolkit has no tag yet. Push it to your
   GitHub organization as a **public** repository named `wow-forever-toolkit` (the workflow
   installs without credentials, so a private repository fails) and tag the commit that holds
   patchwatch 0.2.0: `git tag -a v0.2.0 -m v0.2.0 && git push origin v0.2.0` (toolkit README,
   "Publish the toolkit"). Protect `v*` tags with a tag ruleset, as for the shared library.
2. Copy the workflow to `.github/workflows/patchwatch.yml` in your addon repository. Do **not**
   copy the `patchwatch` folder into the addon repository (see "Vendoring" below).
3. Only if the toolkit lives under another name or you want another version: set the repository
   variable `PATCHWATCH_PIP_SPEC`, for example to
   `git+https://github.com/your-org/wow-forever-toolkit@v0.2.0#subdirectory=patchwatch`. A commit
   SHA in place of `v0.2.0` pins even harder. Without a pin (`...wow-forever-toolkit#subdirectory=...`)
   every run installs whatever `main` holds that day.
4. Optionally set the repository variables `PATCHWATCH_BRANCHES` (default `forever,live,ptr`),
   `PATCHWATCH_ADDON_PATH` (default `.`), `PATCHWATCH_FAIL_ON` (default `never`),
   `PATCHWATCH_STALE_DAYS` (default: forever 10 days, others off) and `PATCHWATCH_FAIL_ON_ALERT`
   (default `missing`: the run fails while a watched branch is missing from the mirror).
5. Run it once by hand (Actions > patchwatch > Run workflow) with `since` empty: that records the
   baseline. Use `since` (for example `-1`) only to get a report right away; a branch with too few
   builds for it (a branch the mirror created recently) just gets its baseline recorded.

The pip spec was tested here against a local git copy of the toolkit tagged `v0.2.0`
(`pip install "git+file://.../wow-forever-toolkit@v0.2.0#subdirectory=patchwatch"` installs
patchwatch 0.2.0 under Python 3.9 and 3.13, without warnings); a real GitHub run was not possible.

What the workflow does:
- It runs every 3 hours and on demand.
- It keeps `.patchwatch/` (state plus mirror cache) with `actions/cache`.
- It uploads the reports as an artifact.
- For each branch with a new build, it opens an issue labelled `patchwatch`, or updates the open
  one. It finds the existing issue by a hidden `<!-- patchwatch:branch=NAME -->` marker, replaces
  the body with the newest report and adds a comment.
- Mirror alerts show as warnings on the run and in its summary. When a new alert appears, the
  workflow opens or updates one "[patchwatch] mirror alerts" issue (marker
  `<!-- patchwatch:alerts -->`) and comments on it; an alert that persists does not comment again.
- When the mirror creates a branch for WoW: Forever's launch product (a `new-branch` or
  `export-product` alert), add it to `PATCHWATCH_BRANCHES`; see `templates/PATCH_DAY.md`, "Launch day".
- The token needs `issues: write`.

If the cache is evicted, which GitHub does after 7 days without use, the next run records a new
baseline instead of reporting.

### Vendoring patchwatch (not recommended)

Copying this folder into an addon repository as `./patchwatch` (and setting
`PATCHWATCH_PIP_SPEC` to `./patchwatch`) works for the workflow, but breaks the addon unless you
also change three files, because patchwatch brings Lua test fixtures and Python code:

| File | Add | Without it |
|---|---|---|
| `.luacheckrc` | `"patchwatch/",` under `exclude_files` | `luacheck .` reports about 40 warnings in the fixtures and Lint fails; the release workflow needs Lint, so no tag publishes |
| `.pkgmeta` | `- patchwatch` under `ignore:` | the packager puts the whole tool (Python modules, tests, fixture TOCs) into every zip |
| `.github/workflows/lint.yml` | `-not -path './patchwatch/*'` in the compile step's `find` | the compile step compiles the fixtures too (they compile, so this one only costs time) |

The addon template (`templates/addon-repo`) already has all three, and its test
(`templates/tests/test_new_addon.sh`) checks with a vendored copy that luacheck stays clean and the
zip holds no patchwatch file; the workflow above keeps the folder out of patchwatch's own scan.
Prefer the pip spec: it needs none of this.

## Limitations

- **The docs do not cover everything.** The generated API docs do not list every global function
  (many FrameXML-era globals are undocumented), Blizzard's Lua mixins and templates, XML templates,
  or CVars. If patchwatch reports no impact, treat that as a hint, not a guarantee.
- **The scan is static.** Aliased namespaces (`local S = C_Spell; S.GetSpellInfo()`), names built
  at runtime and code paths guarded by flavor checks are not understood. A removed API that your
  code only calls behind `if C_Foo then` is still reported.
- **Widget methods are matched by name only.** For example, `cd:SetCooldown(...)` matches
  `FrameAPICooldown:SetCooldown`, so these findings are capped at "warning" and can be false
  positives for common names such as `Clear` or `SetParent`.
- **The mirror can lag.** It is exported on demand: its export workflow has had no cron since
  2025-11-03. The mirror lags Blizzard's CDN by however long it takes someone to trigger an export.
  On recent patch days that was the same day. The stale-branch alert tells you when a branch has
  been quiet for too long; it cannot tell a quiet game from a mirror that stopped exporting it.
- **Server-side changes are invisible.** Hotfixes that change no client files leave no trace.
- **Mirror tags are not live builds.** Version tags in the mirror (`12.1.0`) are lightweight and
  mark the last export of that version on *any* branch, often `ptr`. Use `live@12.1.0` to get the
  newest live build of a version.
- **Renames count twice.** "Files changed" counts a renamed file as two paths, so it can be slightly
  higher than GitHub's count (357 vs 355 for Forever build 70425).
- **Which TOC a client loads follows the wowless project's real-client tests** (2026-10-09/13):
  Forever loads `_Camelot`, then `_Forever` (an alias the client accepts; the BigWigs packager does
  not know it), then `_Mainline`, then the unsuffixed TOC; retail loads `_Standard`, then
  `_Mainline`, then the unsuffixed TOC. The scan also flags game-type gates that do not keep
  retail and Classic out (they do not know `camelot` or `forever`; see `templates/PATCH_DAY.md`,
  "TOC rule") and `## Interface: 00000` stub TOCs.
- **The out-of-date rule is unverified.** The exact rule the client uses to flag an addon as out of
  date (exact match, or older x.y.0) is not in the Lua mirror. patchwatch asks for the exact number.
- **Not run on Windows or macOS yet.** The test suite ran on Linux with Python 3.9 and 3.13. The
  code avoids OS-specific paths, shell calls and console encodings, but it has not been run on
  Windows or macOS yet.

## Manual check: Blizzard's own product list

The alerts above watch the mirror. Blizzard's version servers announce a new product, and the
folder it installs into, before the mirror exports it, and without a game client. This could run
in CI (GitHub-hosted runners can probably reach the servers), but it is **untested**: the hosts
were blocked from the machine that wrote patchwatch. Run it by hand on your own machine, for
example once a day in the launch week. The URLs are the ones instawow uses to build its product
table (`/v2/summary`, then `/<product>/versions` and the product config on the CDN).

**macOS** (Terminal, bash or zsh; `brew install jq`), or Linux/WSL. The first command lists every
WoW product Blizzard serves: look for new `wow*` names, such as the stress test's `wowf`. The next
three print the install folder of one product (set `p` to the product). `curl -f` prints an error
when a request fails; an empty result without an error means the product config has no folder.

```sh
curl -fsS https://us.version.battle.net/v2/summary | awk -F'|' 'NR > 2 && $1 ~ /^wow/ { print $1 }' | sort -u
p=wowf
cfg=$(curl -fsS "https://us.version.battle.net/$p/versions" | awk -F'|' '$1 == "us" { print $NF }' | tr -d '\r')
curl -fsS "https://us.cdn.blizzard.com/tpr/configs/data/${cfg:0:2}/${cfg:2:2}/$cfg" | jq -r '.all.config.shared_container_default_subfolder'
```

**Windows** (PowerShell 5.1 or 7). It uses `curl.exe`, which Windows 10 and 11 include (in
Windows PowerShell plain `curl` means `Invoke-WebRequest`), and PowerShell's own JSON parser, so no
`jq` is needed (Git Bash has none unless you installed it with Scoop). The same three steps:

```powershell
curl.exe -fsS https://us.version.battle.net/v2/summary | ForEach-Object { ($_ -split '\|')[0] } | Where-Object { $_ -like 'wow*' } | Sort-Object -Unique
$p = 'wowf'
$cfg = (curl.exe -fsS "https://us.version.battle.net/$p/versions" | Where-Object { $_ -like 'us|*' } | Select-Object -First 1).Trim().Split('|')[-1]
((curl.exe -fsS "https://us.cdn.blizzard.com/tpr/configs/data/$($cfg.Substring(0,2))/$($cfg.Substring(2,2))/$cfg") -join "`n" | ConvertFrom-Json).all.config.shared_container_default_subfolder
```

Both versions were run here only against canned responses (the parsing, not Blizzard's servers).
A new product with its own folder is layout A in `templates/PATCH_DAY.md`, "Launch day".

## Development

Install the test tools (`lupa` is optional: it cross-checks the parser against real Lua 5.1), run
the tests, and optionally cross-check the parser on real API documentation files:

```sh
python -m pip install pytest lupa
python -m pytest -q
PATCHWATCH_LUPA_DOCS_DIR=/path/to/Interface/AddOns/Blizzard_APIDocumentationGenerated python -m pytest -q tests/test_lupa_crosscheck.py
```

The parser is plain Python: a tolerant Lua lexer plus a table-constructor parser. Unevaluated
expressions such as `Enum.ForbiddenAspect.ScriptBindings` are kept as text.
