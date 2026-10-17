#!/usr/bin/env bash
# test_check_toc.sh - cases for templates/addon-repo/.github/scripts/check-toc.sh: the Forever-only
# gate, multi-flavor TOCs, launch layout B, SUPPORTED_FLAVORS, stubs, suffixes, upper/lower case of
# listed files and the --packaged mode. Each case is a small addon in a temporary folder.
#
#   bash templates/tests/test_check_toc.sh [--bash PATH]...
#
# --bash runs check-toc.sh with that bash (repeatable; default: bash on PATH). macOS's own
# /bin/bash 3.2 works. Exit status: 0 when every case passed.

HERE=$(cd "$(dirname "$0")" && pwd)
CHECK="$HERE/../addon-repo/.github/scripts/check-toc.sh"
[ -f "$CHECK" ] || { echo "check-toc.sh not found at $CHECK" >&2; exit 2; }

BASHES=""
while [ $# -gt 0 ]; do
	case $1 in
		--bash) BASHES="$BASHES
$2"; shift ;;
		-h|--help) sed -n '2,9p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
		*) echo "unknown argument: $1" >&2; exit 2 ;;
	esac
	shift
done
[ -n "$BASHES" ] || BASHES=bash

TMP_ROOT=$(mktemp -d "${TMPDIR:-/tmp}/checktoc.XXXXXX") || exit 2
case $TMP_ROOT in */checktoc.*) ;; *) echo "unexpected temp folder '$TMP_ROOT'" >&2; exit 2 ;; esac
trap 'rm -rf "$TMP_ROOT"' EXIT

PASS=0
FAIL=0
N=0
B=bash
# addon NAME: a fresh addon folder with Core.lua and Locales/enUS.lua; D is its path
addon() {
	N=$((N + 1))
	D="$TMP_ROOT/$N/$1"
	mkdir -p "$D/Locales"
	printf 'local _, ns = ...\n' > "$D/Core.lua"
	printf 'local _, ns = ...\n' > "$D/Locales/enUS.lua"
}
# toc FILE HEADER-LINES: a TOC with the given header plus the lines every TOC needs
toc() {
	{
		printf '%s\n' "$2"
		printf '## Title: T\n## Version: @project-version@\n## X-Curse-Project-ID: 0\n\n'
		printf 'Locales\\enUS.lua\nCore.lua\n'
	} > "$D/$1"
}
flavors() { # SUPPORTED_FLAVORS line for Core.lua, as the template writes it
	printf 'local _, ns = ...\n-- Flavors this addon supports.\nlocal SUPPORTED_FLAVORS = { %s }\n' "$1" > "$D/Core.lua"
}
# expect DESCRIPTION RC PATTERN [ARGS]: run check-toc.sh in $D; PATTERN "-" = no output check,
# a leading "!" = must NOT appear
expect() {
	local desc=$1 want=$2 pat=$3 out rc ok=1
	shift 3
	out=$(cd "$D" && "$B" "$CHECK" "$@" 2>&1)
	rc=$?
	[ "$rc" -eq "$want" ] || ok=0
	case $pat in
		-) ;;
		!*) if printf '%s\n' "$out" | grep -q -- "${pat#!}"; then ok=0; fi ;;
		*) printf '%s\n' "$out" | grep -q -- "$pat" || ok=0 ;;
	esac
	if [ "$ok" -eq 1 ]; then
		PASS=$((PASS + 1)); echo "  PASS: $desc"
	else
		FAIL=$((FAIL + 1)); echo "  FAIL: $desc (exit $rc, wanted $want; pattern: $pat)"
		printf '%s\n' "$out" | sed "s|$TMP_ROOT|<tmp>|g; s/^/        | /"
	fi
}

GATE='## AllowLoadGameType: camelot
## ExcludeLoadGameType: standard, classic'
FLAG='# check-toc: allow-gate-with-retail-interface'

run_cases() {
	addon T; toc T.toc "## Interface: 16001
$GATE"
	expect "Forever-only TOC with the gate passes" 0 "TOC checks passed"
	expect "... without any warning" 0 '!::warning'

	addon T; toc T.toc "## Interface: 16001"
	expect "Forever-only TOC without the gate passes with a warning" 0 "::warning file=T.toc::Forever-only TOC without"

	addon T; toc T.toc "## Interface: 16001
## AllowLoadGameType: camelot"
	expect "Allow line alone still warns (retail and Classic ignore an unknown word)" 0 "Forever-only TOC without"

	addon T; toc T_Camelot.toc "## Interface: 16001"
	expect "_Camelot.toc needs no gate" 0 '!::warning'

	addon T; toc T.toc "## Interface: 16001, 120105
$GATE"
	expect "gate plus a retail number fails" 1 "Delete the two gate lines"

	addon T; toc T.toc "## Interface: 11509, 16001, 120105"
	expect "multi-flavor TOC without the gate passes" 0 "TOC checks passed"

	addon T; toc T.toc "## Interface: 16001, 120105
$GATE
$FLAG"
	expect "layout B: gate plus retail number allowed by the flag line" 0 "::notice file=T.toc::Gate with retail interface number(s) 120105 allowed"

	addon T; toc T.toc "## Interface: 16001, 120105, 11509
$GATE
$FLAG"
	expect "layout B flag does not cover Classic numbers" 1 "covers retail numbers only"

	addon T; toc T.toc "## Interface: 16001
$GATE
$FLAG"
	expect "layout B flag without a retail number warns" 0 "is set but the TOC has no Forever-only gate with a retail number"

	addon T; toc T.toc "## Interface: 11509, 16001, 120105"; flavors "forever = true"
	expect "TOC lists retail, SUPPORTED_FLAVORS does not: warning" 0 "SUPPORTED_FLAVORS in ./Core.lua does not include retail"
	expect "... and Classic Era" 0 "does not include classic_era"

	addon T; toc T.toc "## Interface: 16001
$GATE"; flavors "forever = true, retail = true"
	expect "SUPPORTED_FLAVORS has retail, the TOC lists no retail number: warning" 0 "SUPPORTED_FLAVORS includes retail, but T.toc lists no retail"

	addon T; toc T.toc "## Interface: 11509, 16001, 120105"
	printf 'local _, ns = ...\nlocal SUPPORTED_FLAVORS = {\n\tforever = true, -- Forever\n\tretail = true,\n\tclassic_era = true,\n}\n' > "$D/Core.lua"
	expect "multi-line SUPPORTED_FLAVORS that matches the TOC: no warning" 0 '!::warning'

	addon T; toc T.toc "## Interface: 16001, 16002
$GATE"; flavors "forever = true"
	expect "two Forever numbers (patch day) pass without warning" 0 '!::warning'

	addon T; toc T_Camelot.toc "## Interface: 16001"; toc T.toc "## Interface: 00000"
	expect "00000 stub TOC fails" 1 "client not supported' stub"

	addon T; toc T_Forever.toc "## Interface: 16001
$GATE"
	expect "_Forever.toc fails" 1 "Rename to T_Camelot.toc"

	addon T; toc T.toc "## Interface: 16001, 1.60.1
$GATE"
	expect "a version string in ## Interface fails" 1 "is not a 5 or 6 digit interface number"

	addon T; toc T.toc "## Interface: 16001
$GATE"; mv "$D/Core.lua" "$D/core.lua"
	expect "a listed file with the wrong upper/lower case fails" 1 "Listed file 'Core.lua' does not exist"

	addon T; toc T.toc "## Interface: 16001
$GATE"; sed 's/^## Version: .*/## Version: 1.0/' "$D/T.toc" > "$D/t" && mv "$D/t" "$D/T.toc"
	expect "## Version other than @project-version@ fails" 1 "Use '## Version: @project-version@'"

	addon T; toc T.toc "## Interface: 16001
$GATE"; grep -v '^## X-Curse-Project-ID' "$D/T.toc" > "$D/t" && mv "$D/t" "$D/T.toc"
	expect "missing X-Curse-Project-ID line fails" 1 "Missing '## X-Curse-Project-ID:' line"

	addon T; toc T.toc "## Interface: 16001
$GATE"; printf '%s\r\n' '## Interface: 16001' '## Title: T' '## Version: @project-version@' '## X-Curse-Project-ID: 0' 'Core.lua' > "$D/T.toc"
	expect "a CRLF TOC is read like an LF one" 0 "TOC checks passed"

	addon T; toc T.toc "## Interface: 16001
$GATE"; printf 'Libs\\LibKs-1.0\\LibKs-1.0.lua\n' >> "$D/T.toc"
	expect "Libs\\ lines are skipped in the repository (the packager fetches them)" 0 "TOC checks passed"
	mkdir -p "$D/Libs/LibKs-1.0"; printf '\n' > "$D/Libs/LibKs-1.0/LibTx-1.0.lua"
	expect "--packaged: a library file renamed in the TOC only fails" 1 "Listed file 'Libs.LibKs-1.0.LibKs-1.0.lua' does not exist" --packaged .
	mv "$D/Libs/LibKs-1.0/LibTx-1.0.lua" "$D/Libs/LibKs-1.0/LibKs-1.0.lua"
	expect "--packaged: every listed file present passes" 0 "Packaged TOC checks passed" --packaged .
	expect "--packaged without a folder fails" 1 "needs the packaged addon folder" --packaged
}

for B in $BASHES; do
	# shellcheck disable=SC2016 # $BASH_VERSION of the bash under test
	echo "== check-toc.sh with $B ($("$B" -c 'echo $BASH_VERSION'))"
	run_cases
done
echo "== $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
