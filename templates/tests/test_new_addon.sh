#!/usr/bin/env bash
# test_new_addon.sh - end-to-end test of the team templates with a team token other than Tx.
#
#   bash templates/tests/test_new_addon.sh [--packager PATH] [--packager-bash PATH] [--bash PATH] [--keep]
#
# In a temporary folder, on copies (the toolkit itself is never changed):
#   1. set-team.sh makes the templates Kestrel Studio's (token Ks, library LibKs-1.0, organization
#      kestrel-studio); a bad token is refused without changing anything.
#   2. LibKs-1.0 is created from shared-lib/ and tagged v1.0.0; new-addon-repo.sh creates Ks_Bags.
#   3. The addon's CI checks run (Lua 5.1 compile, luacheck if installed, check-toc.sh,
#      check_paths.py), the BigWigs packager builds it with -d (no upload; the library comes from
#      the local LibKs-1.0 through git's url.<base>.insteadOf, no network), and the zip is checked.
#   4. The packaged folder passes check-toc.sh --packaged and loads in the Lua 5.1 smoke harness
#      (tests/harness/run.sh) on every client its TOC lists.
#   5. A vendored patchwatch/ folder stays out of luacheck, the compile step and the zip.
#   6. Negative controls: the text-only rename the reviewers tried (LibTx-1.0 replaced in the text,
#      the library files not renamed) is refused by new-addon-repo.sh, and a packaged addon built
#      that way fails check-toc.sh --packaged and the harness ("Cannot find a library instance");
#      the harness also catches a leaked global, a /command without handler and a client the TOC
#      lists but SUPPORTED_FLAVORS leaves inactive.
#
# --packager       release.sh of the BigWigs packager at commit 0f24d21 (default: $PACKAGER, else
#                  ~/dev/packager/release.sh). Clone: git clone https://github.com/BigWigsMods/packager
#                  ~/dev/packager && git -C ~/dev/packager checkout 0f24d2169de3ceb3b79a981311b2ebab4c6160c7
# --packager-bash  bash 4.3 or newer for the packager (default: bash on PATH; macOS: Homebrew's)
# --bash           bash for the template scripts (default: bash on PATH; macOS's /bin/bash 3.2 works)
# --keep           keep the temporary folder and print its path
# LUA (environment) the Lua 5.1 interpreter for the harness (default: lua5.1, lua or luajit on
# PATH); LUACHECK the luacheck command (default: luacheck, skipped when missing).
# Needs git 2.31 or newer, perl, python3 and zip. Exit status: 0 when every check passed.

# Each check is a shell condition in single quotes that ok() evaluates later, so the variables it
# reads ($RC, $OUT, ...) look unused and unexpanded to shellcheck.
# shellcheck disable=SC2016,SC2034

HERE=$(cd "$(dirname "$0")" && pwd)
TEMPLATES=$(cd "$HERE/.." && pwd)
TOOLKIT=$(cd "$TEMPLATES/.." && pwd)

PACKAGER=${PACKAGER:-}
PKG_BASH=bash
SH=bash
KEEP=""
while [ $# -gt 0 ]; do
	case $1 in
		--packager) PACKAGER=$2; shift ;;
		--packager-bash) PKG_BASH=$2; shift ;;
		--bash) SH=$2; shift ;;
		--keep) KEEP=1 ;;
		-h|--help) sed -n '2,31p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
		*) echo "unknown argument: $1" >&2; exit 2 ;;
	esac
	shift
done
if [ -z "$PACKAGER" ] && [ -f "$HOME/dev/packager/release.sh" ]; then PACKAGER="$HOME/dev/packager/release.sh"; fi
[ -n "$PACKAGER" ] && [ -f "$PACKAGER" ] || {
	echo "The BigWigs packager was not found: pass --packager PATH/release.sh or set PACKAGER (see --help)." >&2
	exit 2
}
"$PKG_BASH" -c '[ "${BASH_VERSINFO[0]}" -gt 4 ] || { [ "${BASH_VERSINFO[0]}" -eq 4 ] && [ "${BASH_VERSINFO[1]}" -ge 3 ]; }' 2>/dev/null || {
	echo "The packager needs bash 4.3 or newer; pass --packager-bash PATH (macOS: \"\$(brew --prefix)/bin/bash\")." >&2
	exit 2
}
if [ -z "${LUA:-}" ]; then
	for candidate in lua5.1 lua luajit; do
		if command -v "$candidate" >/dev/null 2>&1; then LUA=$candidate; break; fi
	done
fi
[ -n "${LUA:-}" ] || { echo "No Lua found: install Lua 5.1 or LuaJIT, or set LUA" >&2; exit 2; }
export LUA
LUACHECK=${LUACHECK:-luacheck}
PY=$(command -v python3 || command -v python) || { echo "python3 is required" >&2; exit 2; }
for tool in git perl zip; do
	command -v "$tool" >/dev/null 2>&1 || { echo "$tool is required" >&2; exit 2; }
done

TMP_ROOT=$(mktemp -d "${TMPDIR:-/tmp}/newaddon.XXXXXX") || exit 2
case $TMP_ROOT in */newaddon.*) ;; *) echo "unexpected temp folder '$TMP_ROOT'" >&2; exit 2 ;; esac
case $TMP_ROOT in *' '*) echo "the temporary folder must not contain spaces: $TMP_ROOT" >&2; exit 2 ;; esac
cleanup() {
	if [ -n "$KEEP" ]; then echo "kept: $TMP_ROOT"; else rm -rf "$TMP_ROOT"; fi
}
trap cleanup EXIT

PASS=0
FAIL=0
OUT=""
RC=0
ok() { # description, shell condition (evaluated; OUT and RC hold the last command's output and exit status)
	if eval "$2"; then
		PASS=$((PASS + 1)); echo "  PASS: $1"
	else
		FAIL=$((FAIL + 1)); echo "  FAIL: $1"
		printf '%s\n' "$OUT" | tail -n 40 | sed "s|$TMP_ROOT|<tmp>|g; s/^/        | /"
	fi
}
has() { printf '%s\n' "$OUT" | grep -q -- "$1"; }
run() { OUT=$("$@" 2>&1); RC=$?; }
runin() { local d=$1; shift; OUT=$(cd "$d" && "$@" 2>&1); RC=$?; }
gitq() { git -c user.name=test -c user.email=test@example.invalid -c commit.gpgsign=false -c tag.gpgsign=false "$@"; }
zip_list() { "$PY" -c 'import sys, zipfile; print("\n".join(zipfile.ZipFile(sys.argv[1]).namelist()))' "$1"; }
# tree_sum DIR: one checksum over every file name and content (to prove nothing changed)
tree_sum() { (cd "$1" && find . -type f | LC_ALL=C sort | while IFS= read -r f; do printf '%s\n' "$f"; cat "$f"; done) | cksum; }
# packager REPO LIBREPO: build REPO with -d, kestrel-studio/LibKs-1.0 served from LIBREPO
packager() {
	local repo=$1 lib=$2
	OUT=$(cd "$repo" && env -u CF_API_KEY -u CF_API_TOKEN -u GITHUB_OAUTH -u GH_API_TOKEN -u GITHUB_API_TOKEN \
		-u WAGO_API_TOKEN -u WOWI_API_TOKEN -u GITHUB_ACTIONS -u GITHUB_REF -u GITHUB_EVENT_NAME \
		GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0="url.file://$lib.insteadOf" \
		GIT_CONFIG_VALUE_0=https://github.com/kestrel-studio/LibKs-1.0 \
		"$PKG_BASH" "$PACKAGER" -d 2>&1)
	RC=$?
}
lua_compile() { # DIR: compile every .lua file as the Lint workflow does
	(
		cd "$1" || exit 1
		bad=0
		while IFS= read -r f; do
			"$LUA" -e "assert(loadfile([[$f]]))" || bad=1
		done <<EOF
$(find . -name '*.lua' -not -path './.release/*' -not -path './Libs/*' -not -path './.lua*' -not -path './patchwatch/*')
EOF
		exit $bad
	)
}

echo "toolkit: $TOOLKIT"
echo "packager: $PACKAGER ($(git -C "$(dirname "$PACKAGER")" log -1 --format=%h 2>/dev/null || echo 'not a git checkout'))"
# shellcheck disable=SC2016 # the bash versions are printed by the bashes under test
echo "bash for the scripts: $("$SH" -c 'echo $BASH_VERSION'); for the packager: $("$PKG_BASH" -c 'echo $BASH_VERSION'); Lua: $("$LUA" -v 2>&1 | head -n 1)"

# ------------------------------------------------------------------ 1. set-team.sh
echo "== 1. set-team.sh"
T="$TMP_ROOT/toolkit/templates"
mkdir -p "$TMP_ROOT/toolkit"
cp -R "$TEMPLATES" "$T"
rm -f "$T/team.conf"
before=$(tree_sum "$T")
run "$SH" "$T/set-team.sh" ks "Kestrel Studio" kestrel-studio abcd1234
ok "a token that is not one capital and 1-3 small letters is refused" '[ $RC -eq 2 ] && has "TOKEN must be one capital letter"'
run "$SH" "$T/set-team.sh" Ks "Kestrel Studio" "kestrel studio" abcd1234
ok "an organization name with a space is refused" '[ $RC -eq 2 ] && has "GITHUB_ORG must be"'
ok "... and nothing was changed" '[ "$(tree_sum "$T")" = "$before" ]'
run "$SH" "$T/set-team.sh" Ks "Kestrel Studio" kestrel-studio abcd1234
ok "set-team.sh Ks \"Kestrel Studio\" kestrel-studio abcd1234 succeeds" '[ $RC -eq 0 ] && has "token Ks (LibKs-1.0, Ks_Example)"'
ok "library files renamed: shared-lib/LibKs-1.0.lua and .toc" '[ -f "$T/shared-lib/LibKs-1.0.lua" ] && [ -f "$T/shared-lib/LibKs-1.0.toc" ] && [ ! -e "$T/shared-lib/LibTx-1.0.lua" ]'
ok "addon template renamed: addon-repo/Ks_Example.toc" '[ -f "$T/addon-repo/Ks_Example.toc" ] && [ ! -e "$T/addon-repo/Tx_Example.toc" ]'
OUT=$(grep -rn -e LibTx -e Tx_Example -e TxExample -e TXEXAMPLE -e txexample -e 'Tx Studio' -e YOUR-ORG -e YOUR-INVITE "$T/addon-repo" "$T/shared-lib" 2>&1)
ok "no team placeholder is left in addon-repo/ and shared-lib/" '[ -z "$OUT" ]'
ok "the library and the addon use the new names" 'grep -q "^Libs\\\\LibKs-1.0\\\\LibKs-1.0.lua" "$T/addon-repo/Ks_Example.toc" && grep -q "\"LibKs-1.0\", 1" "$T/shared-lib/LibKs-1.0.lua" && grep -q "url: https://github.com/kestrel-studio/LibKs-1.0" "$T/addon-repo/.pkgmeta" && grep -q "SLASH_KSEXAMPLE1 = \"/ksexample\"" "$T/addon-repo/Core.lua"'
ok "team.conf records the values" 'grep -q "^TEAM_TOKEN=Ks$" "$T/team.conf" && grep -q "^GITHUB_ORG=kestrel-studio$" "$T/team.conf"'
run "$SH" "$T/set-team.sh" Ks "Kestrel Studio" kestrel-studio abcd1234
ok "running it again with the same values changes nothing" '[ $RC -eq 0 ] && has "Nothing to change"'

# ------------------------------------------------------------------ 2. library and addon repositories
echo "== 2. LibKs-1.0 and new-addon-repo.sh"
LIB="$TMP_ROOT/LibKs-1.0"
cp -R "$T/shared-lib" "$LIB"
(cd "$LIB" && git init -q -b main && gitq add -A && gitq commit -qm "LibKs-1.0 v1.0.0" && gitq tag -a v1.0.0 -m v1.0.0)
ok "LibKs-1.0 repository tagged v1.0.0" '[ "$(git -C "$LIB" tag)" = v1.0.0 ]'
DEV="$TMP_ROOT/dev"
run "$SH" "$T/new-addon-repo.sh" "$DEV/Ks_Bags" Ks_Bags other-org "Ks Bags"
ok "new-addon-repo.sh refuses an organization other than team.conf's" '[ $RC -eq 2 ] && has "differs from team.conf" && [ ! -e "$DEV/Ks_Bags" ]'
run "$SH" "$T/new-addon-repo.sh" "$DEV/Ks_Bags_Camelot" Ks_Bags_Camelot kestrel-studio
ok "new-addon-repo.sh refuses a game-flavor suffix in the name" '[ $RC -eq 2 ] && [ ! -e "$DEV/Ks_Bags_Camelot" ]'
run "$SH" "$T/new-addon-repo.sh" "$DEV/Ks_Bags" Ks_Bags kestrel-studio "Ks Bags"
A="$DEV/Ks_Bags"
ok "new-addon-repo.sh Ks_Bags succeeds" '[ $RC -eq 0 ] && [ -f "$A/Ks_Bags.toc" ]'
ok "it lists what to fill in by hand (invite placeholder gone, Notes line, IDs)" 'has "Fill in by hand" && has "## Notes: One sentence" && ! has "YOUR-INVITE"'
ok "names in the new addon: KsBagsDB, SLASH_KSBAGS1 /ksbags, package-as Ks_Bags, LibKs-1.0" 'grep -q "^## SavedVariables: KsBagsDB" "$A/Ks_Bags.toc" && grep -q "SLASH_KSBAGS1 = \"/ksbags\"" "$A/Core.lua" && grep -q "^package-as: Ks_Bags$" "$A/.pkgmeta" && grep -q "LibStub(\"LibKs-1.0\")" "$A/Core.lua"'
OUT=$(grep -rn -e Ks_Example -e KsExample -e KSEXAMPLE -e ksexample -e 'Ks Example' -e YOUR-ORG "$A" 2>&1)
ok "no per-addon placeholder is left" '[ -z "$OUT" ]'
ok "scripts keep their executable bit" '[ -x "$A/.github/scripts/check-toc.sh" ] && [ -x "$A/tests/harness/run.sh" ]'
run "$SH" "$T/new-addon-repo.sh" "$A" Ks_Bags kestrel-studio
ok "an existing DEST is refused" '[ $RC -eq 1 ] && has "DEST already exists"'
ls -a "$DEV" > "$TMP_ROOT/dev.list"
ok "failed runs left no temporary folder behind" '! grep -q new-addon-repo "$TMP_ROOT/dev.list"'

(cd "$A" && git init -q -b main && gitq add -A && gitq commit -qm "Start Ks_Bags" && gitq tag -a v1.0.0 -m v1.0.0)

# ------------------------------------------------------------------ 3. CI checks, packager, zip
echo "== 3. CI checks, packager -d, zip"
OUT=$(lua_compile "$A" 2>&1); RC=$?
ok "Lua 5.1 compile of every Lua file" '[ $RC -eq 0 ]'
if command -v "$LUACHECK" >/dev/null 2>&1; then
	runin "$A" "$LUACHECK" . --no-color --codes
	ok "luacheck . --no-color --codes" '[ $RC -eq 0 ]'
else
	echo "  skip: luacheck not found (set LUACHECK)"
fi
runin "$A" "$SH" .github/scripts/check-toc.sh
ok "check-toc.sh" '[ $RC -eq 0 ] && has "TOC checks passed"'
runin "$A" "$PY" .github/scripts/check_paths.py .
ok "check_paths.py ." '[ $RC -eq 0 ]'
packager "$A" "$LIB"
ok "packager -d exits 0" '[ $RC -eq 0 ] && [ -f "$A/.release/Ks_Bags-v1.0.0-forever.zip" ]'
ok "packager fetched LibKs-1.0 at v1.0.0 and tagged Forever only" 'has "Checked out v1.0.0" && has "Game version: 1.60.1"'
zip_list "$A/.release/Ks_Bags-v1.0.0-forever.zip" > "$TMP_ROOT/zip1.txt" 2>&1
OUT=$(cat "$TMP_ROOT/zip1.txt")
ok "zip holds the TOC, the code and the renamed library files" 'has "^Ks_Bags/Ks_Bags.toc$" && has "^Ks_Bags/Core.lua$" && has "^Ks_Bags/Libs/LibKs-1.0/LibKs-1.0.lua$" && has "^Ks_Bags/Libs/LibKs-1.0/LibStub/LibStub.lua$"'
ok "zip holds no tests/, no README.md and nothing named LibTx" '! has "/tests/" && ! has "^Ks_Bags/README.md$" && ! has LibTx'

# ------------------------------------------------------------------ 4. packaged folder: TOC check and smoke harness
echo "== 4. packaged folder"
P="$A/.release/Ks_Bags"
runin "$A" "$SH" .github/scripts/check-toc.sh --packaged .release/Ks_Bags
ok "check-toc.sh --packaged .release/Ks_Bags" '[ $RC -eq 0 ] && has "every listed file is in"'
runin "$A" "$SH" tests/harness/run.sh .release/Ks_Bags
ok "smoke harness on the packaged addon: Forever (current and pre-70170), gate keeps retail and Classic Era off" '[ $RC -eq 0 ] && has "runs: 4, failed runs: 0"'
printf '%s\n' "$OUT" | sed 's/^/        /'

# ------------------------------------------------------------------ 5. vendored patchwatch
echo "== 5. vendored patchwatch (not recommended, but it must not break lint or the zip)"
mkdir -p "$A/patchwatch"
(cd "$TOOLKIT/patchwatch" && find . -type f ! -path '*/__pycache__/*' ! -path './.pytest_cache/*' ! -path '*.egg-info/*' ! -path './build/*' |
	while IFS= read -r f; do mkdir -p "$A/patchwatch/$(dirname "$f")" && cp "$f" "$A/patchwatch/$f"; done)
(cd "$A" && gitq add -A && gitq commit -qm "Vendor patchwatch" && gitq tag -a v1.0.1 -m v1.0.1)
ok "patchwatch/ vendored with its Lua test fixtures" '[ -n "$(find "$A/patchwatch" -name "*.lua" | head -n 1)" ]'
if command -v "$LUACHECK" >/dev/null 2>&1; then
	runin "$A" "$LUACHECK" . --no-color --codes
	ok "luacheck still clean (.luacheckrc excludes patchwatch/)" '[ $RC -eq 0 ] && ! has patchwatch'
	grep -v '"patchwatch/"' "$A/.luacheckrc" > "$TMP_ROOT/luacheckrc-without-exclude"
	runin "$A" "$LUACHECK" . --no-color --codes --config "$TMP_ROOT/luacheckrc-without-exclude"
	ok "control: without that exclude luacheck fails on patchwatch's fixtures" '[ $RC -ne 0 ] && has "patchwatch/tests/fixtures"'
fi
OUT=$(lua_compile "$A" 2>&1); RC=$?
ok "compile step skips ./patchwatch" '[ $RC -eq 0 ]'
packager "$A" "$LIB"
ok "packager -d exits 0" '[ $RC -eq 0 ] && [ -f "$A/.release/Ks_Bags-v1.0.1-forever.zip" ]'
OUT=$(zip_list "$A/.release/Ks_Bags-v1.0.1-forever.zip" 2>&1)
ok "zip has no patchwatch files (.pkgmeta ignores patchwatch)" '! has patchwatch && has "^Ks_Bags/Ks_Bags.toc$"'
perl -ni -e 'print unless /^  - patchwatch$/' "$A/.pkgmeta"
(cd "$A" && gitq commit -qam "control: do not ignore patchwatch" && gitq tag -a v1.0.2 -m v1.0.2)
packager "$A" "$LIB"
OUT=$(zip_list "$A/.release/Ks_Bags-v1.0.2-forever.zip" 2>&1)
ok "control: without that ignore line the zip ships patchwatch" '[ "$(printf "%s\n" "$OUT" | grep -c "^Ks_Bags/patchwatch/")" -gt 10 ]'

# ------------------------------------------------------------------ 6. negative controls
echo "== 6. negative controls"
N="$TMP_ROOT/naive/templates"
mkdir -p "$TMP_ROOT/naive"
cp -R "$TEMPLATES" "$N"
rm -f "$N/team.conf"
# The reviewers' text-only replacement (review_walkthrough issue 2), file names untouched:
(cd "$TMP_ROOT/naive" && find templates -type f ! -name new-addon-repo.sh ! -name README.md -print0 |
	xargs -0 perl -pi -e 's/Tx Studio/Kestrel Studio/g; s/LibTx-1\.0/LibKs-1.0/g; s/YOUR-ORG/kestrel-studio/g; s/YOUR-INVITE/abcd1234/g')
ok "naive rename: shared-lib still holds LibTx-1.0.lua, its TOC lists LibKs-1.0.lua" '[ -f "$N/shared-lib/LibTx-1.0.lua" ] && grep -q "^LibKs-1.0.lua" "$N/shared-lib/LibTx-1.0.toc"'
run "$SH" "$N/new-addon-repo.sh" "$TMP_ROOT/naive/Ks_Bags" Ks_Bags kestrel-studio
ok "new-addon-repo.sh refuses the half-renamed templates and creates nothing" '[ $RC -eq 2 ] && has "renamed by hand" && [ ! -e "$TMP_ROOT/naive/Ks_Bags" ]'
# The reviewers' end state: an addon that lists LibKs-1.0.lua, built against that library repository.
NLIB="$TMP_ROOT/naive/LibKs-1.0"
cp -R "$N/shared-lib" "$NLIB"
(cd "$NLIB" && git init -q -b main && gitq add -A && gitq commit -qm "LibKs-1.0 v1.0.0 (files not renamed)" && gitq tag -a v1.0.0 -m v1.0.0)
NA="$TMP_ROOT/naive/Ks_Bags"
git clone -q "$A" "$NA" && git -C "$NA" checkout -q v1.0.0
packager "$NA" "$NLIB"
ok "packager -d still exits 0 (nothing in the build notices)" '[ $RC -eq 0 ]'
OUT=$(zip_list "$NA/.release/Ks_Bags-v1.0.0-forever.zip" 2>&1)
ok "the zip ships Libs/LibKs-1.0/LibTx-1.0.lua instead of LibKs-1.0.lua" 'has "^Ks_Bags/Libs/LibKs-1.0/LibTx-1.0.lua$" && ! has "^Ks_Bags/Libs/LibKs-1.0/LibKs-1.0.lua$"'
runin "$NA" "$SH" .github/scripts/check-toc.sh --packaged .release/Ks_Bags
ok "check-toc.sh --packaged fails: the listed library file is missing" '[ $RC -eq 1 ] && has "Listed file .Libs.LibKs-1.0.LibKs-1.0.lua. does not exist"'
runin "$NA" "$SH" tests/harness/run.sh .release/Ks_Bags
ok "the smoke harness fails with \"Cannot find a library instance\"" '[ $RC -ne 0 ] && has "Cannot find a library instance of \"LibKs-1.0\""'

# Seeded mistakes in copies of the good packaged folder: the harness must catch each one.
mutant() { # NAME: fresh copy of the packaged addon in $M
	M="$TMP_ROOT/mutants/$1/Ks_Bags"
	mkdir -p "$TMP_ROOT/mutants/$1"
	cp -R "$P" "$M"
}
mutant leak
printf '\nKsBagsCache = {}\n' >> "$M/Core.lua"
runin "$A" "$SH" tests/harness/run.sh "$M"
ok "harness: a new global the .luacheckrc does not list" '[ $RC -ne 0 ] && has "no global outside" && has KsBagsCache'
mutant slash
printf '\nSLASH_KSBAGSX1 = "/ksbx"\n' >> "$M/Core.lua"
runin "$A" "$SH" tests/harness/run.sh "$M"
ok "harness: a /command without its SlashCmdList handler" '[ $RC -ne 0 ] && has "SLASH_KSBAGSX1 has its handler"'
mutant flavors
perl -ni -e 'print unless /^## (Allow|Exclude)LoadGameType:/; ' "$M/Ks_Bags.toc"
perl -pi -e 's/^## Interface: .*/## Interface: 16001, 120105, 11509/' "$M/Ks_Bags.toc"
runin "$A" "$SH" tests/harness/run.sh "$M"
ok "harness: retail and Classic Era in ## Interface but not in SUPPORTED_FLAVORS" '[ $RC -ne 0 ] && has "SUPPORTED_FLAVORS includes retail" && has "SUPPORTED_FLAVORS includes classic_era"'
perl -pi -e 's/^local SUPPORTED_FLAVORS = .*/local SUPPORTED_FLAVORS = { forever = true, retail = true, classic_era = true }/' "$M/Core.lua"
runin "$A" "$SH" tests/harness/run.sh "$M"
ok "harness: the same TOC passes once SUPPORTED_FLAVORS lists the three flavors" '[ $RC -eq 0 ] && has "runs: 4, failed runs: 0"'
mutant interface
perl -pi -e 's/^## Interface: .*/## Interface: 16002/' "$M/Ks_Bags.toc"
runin "$A" "$SH" tests/harness/run.sh "$M"
ok "harness: a TOC without the client's interface number (16002 only)" '[ $RC -ne 0 ] && has "## Interface lists 16001"'

echo "== $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
