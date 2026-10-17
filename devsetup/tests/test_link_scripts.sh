#!/usr/bin/env bash
# test_link_scripts.sh - how link-addons.sh and link-addons.ps1 resolve "-f forever" / "-Flavor forever"
# on fake World of Warcraft installs (make_fake_installs.py): one Forever folder, several (the beta
# plus the stress test, launch day with the beta still installed, a shared _retail_), pins, the
# degraded case. No game client and nothing outside a temporary folder is touched.
#
#   bash devsetup/tests/test_link_scripts.sh [--bash PATH]... [--pwsh PATH | --no-pwsh]
#
# --bash runs link-addons.sh with that bash (repeatable; default: bash on PATH). macOS's own
# /bin/bash 3.2 works. --pwsh runs link-addons.ps1 with that PowerShell 7 (default: pwsh on PATH,
# skipped when there is none). Needs python3 (or python) for the fake installs.
# Exit status: 0 when every check passed.

# Each check is a shell condition in single quotes that ok() evaluates later, so the variables it
# reads ($RC, $S2, ...) look unused and unexpanded to shellcheck.
# shellcheck disable=SC2016,SC2034

HERE=$(cd "$(dirname "$0")" && pwd)
DEVSETUP=$(cd "$HERE/.." && pwd)
SH_SCRIPT="$DEVSETUP/link-addons.sh"
PS_SCRIPT="$DEVSETUP/link-addons.ps1"

BASHES=""
PWSH=""
NO_PWSH=""
while [ $# -gt 0 ]; do
	case $1 in
		--bash) BASHES="$BASHES
$2"; shift ;;
		--pwsh) PWSH=$2; shift ;;
		--no-pwsh) NO_PWSH=1 ;;
		-h|--help) sed -n '2,13p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
		*) echo "unknown argument: $1" >&2; exit 2 ;;
	esac
	shift
done
[ -n "$BASHES" ] || BASHES=bash
if [ -z "$PWSH" ] && [ -z "$NO_PWSH" ] && command -v pwsh >/dev/null 2>&1; then PWSH=pwsh; fi
PY=$(command -v python3 || command -v python) || { echo "python3 is required" >&2; exit 2; }

TMP_ROOT=$(mktemp -d "${TMPDIR:-/tmp}/linktest.XXXXXX") || exit 2
case $TMP_ROOT in */linktest.*) ;; *) echo "unexpected temp folder '$TMP_ROOT'" >&2; exit 2 ;; esac
trap 'rm -rf "$TMP_ROOT"' EXIT

PASS=0
FAIL=0
OUT=""
RC=0
ok() { # description, shell condition
	if eval "$2"; then
		PASS=$((PASS + 1)); echo "  PASS: $1"
	else
		FAIL=$((FAIL + 1)); echo "  FAIL: $1"
		printf '%s\n' "$OUT" | sed "s|$TMP_ROOT|<tmp>|g; s/^/        | /"
	fi
}
has() { printf '%s\n' "$OUT" | grep -q -- "$1"; }
hasre() { printf '%s\n' "$OUT" | grep -Eq -- "$1"; }

RUNS=0
fresh() { # new fake installs in $F
	RUNS=$((RUNS + 1))
	F="$TMP_ROOT/run$RUNS"
	"$PY" "$HERE/make_fake_installs.py" "$F" > /dev/null || { echo "make_fake_installs.py failed" >&2; exit 2; }
	DEV="$F/dev/Tx_Bags"
}
mac() { echo "$F/$1/mac/Applications/World of Warcraft"; }
win() { echo "$F/$1/win/C/Program Files (x86)/World of Warcraft"; }

# ----------------------------------------------------------------- link-addons.sh
run_sh() { # bash, scenario (mac layout via product.db), then link-addons.sh arguments
	local b=$1 s=$2; shift 2
	OUT=$(WOW_DEVSETUP_OS=Darwin WOW_DEVSETUP_TEST_PREFIX="$F/$s/mac" "$b" "$SH_SCRIPT" "$@" 2>&1); RC=$?
}
run_sh_root() { # bash, then arguments (Linux mode, use --wow-root)
	local b=$1; shift
	OUT=$(WOW_DEVSETUP_OS=Linux WOW_DEVSETUP_TEST_PREFIX='' "$b" "$SH_SCRIPT" "$@" 2>&1); RC=$?
}

test_sh() {
	local B=$1 S2 B_ROOT
	echo "== link-addons.sh with $B ($("$B" -c 'echo $BASH_VERSION'))"
	fresh
	S2=$(mac S2)

	run_sh "$B" S1 link -n -f forever "$DEV"
	ok "S1 (beta only): forever -> _classic_beta_" '[ $RC -eq 0 ] && has "_classic_beta_/Interface/AddOns" && has "forever: product wow_classic_beta 1.60.1.70425"'

	run_sh "$B" S2 list
	ok "S2 list: forever is ambiguous, both candidates listed with product and build" \
		'[ $RC -eq 0 ] && has "-f forever -> ambiguous: _classic_beta_ _forever_" && hasre "_classic_beta_ +product wow_classic_beta 1.60.1.70425" && hasre "_forever_ +product wowf 1.60.1.70245"'
	run_sh "$B" S2 link -f forever "$DEV"
	ok "S2 link -f forever: refused, candidates listed, nothing linked" \
		'[ $RC -ne 0 ] && has "look like WoW: Forever, so .forever. is ambiguous" && hasre "_forever_ +product wowf 1.60.1.70245" && has "nothing was changed" && [ ! -e "$S2/_classic_beta_/Interface/AddOns/Tx_Bags" ] && [ ! -e "$S2/_forever_/Interface/AddOns/Tx_Bags" ]'
	run_sh "$B" S2 link -n -f forever "$DEV"
	ok "S2 dry run is refused the same way" '[ $RC -ne 0 ] && has "is ambiguous"'
	run_sh "$B" S2 status -f forever "$DEV"
	ok "S2 status -f forever is refused too" '[ $RC -ne 0 ] && has "is ambiguous"'
	run_sh "$B" S2 link -f _classic_beta_ "$DEV"
	ok "S2 link -f _classic_beta_ links the beta" '[ $RC -eq 0 ] && [ -L "$S2/_classic_beta_/Interface/AddOns/Tx_Bags" ]'
	run_sh "$B" S2 link -f _forever_ "$DEV"
	ok "S2 link -f _forever_ links the stress test (AddOns created)" '[ $RC -eq 0 ] && [ -L "$S2/_forever_/Interface/AddOns/Tx_Bags" ]'
	OUT=$(WOW_FOREVER_FOLDER=_classic_beta_ WOW_DEVSETUP_OS=Darwin WOW_DEVSETUP_TEST_PREFIX="$F/S2/mac" "$B" "$SH_SCRIPT" status -f forever "$DEV" 2>&1); RC=$?
	ok "S2 WOW_FOREVER_FOLDER=_classic_beta_ pins forever" '[ $RC -eq 0 ] && has "_classic_beta_/Interface/AddOns" && has "pinned by" && has "Tx_Bags: linked"'
	run_sh "$B" S2 unlink -f forever --forever-folder _forever_ "$DEV"
	ok "S2 --forever-folder _forever_ pins forever (unlink)" '[ $RC -eq 0 ] && [ ! -e "$S2/_forever_/Interface/AddOns/Tx_Bags" ] && [ -L "$S2/_classic_beta_/Interface/AddOns/Tx_Bags" ]'
	run_sh "$B" S2 list --forever-folder _classic_beta_
	ok "S2 list with a pin reports it" 'has "-f forever -> _classic_beta_ (pinned by"'

	run_sh "$B" A link -n -f forever "$DEV"
	ok "A (launch, beta still installed): refused, wowf 1.60.2.71000 listed" '[ $RC -ne 0 ] && hasre "_forever_ +product wowf 1.60.2.71000" && hasre "_classic_beta_ +product wow_classic_beta"'
	run_sh "$B" A2 link -n -f forever "$DEV"
	ok "A2 (launch, beta uninstalled): forever -> _forever_" '[ $RC -eq 0 ] && has "_forever_/Interface/AddOns" && has "WoW: Forever (new folder)"'

	B_ROOT=$(mac B)
	run_sh_root "$B" list --wow-root "$B_ROOT"
	ok "B (shared _retail_ + stale beta): ambiguous, _retail_ listed with its evidence" 'hasre "_retail_ +product wow 12.1.7.70500; lastAddonVersion 16001" && has "ambiguous"'
	OUT=$(WOW_FOREVER_FOLDER=_retail_ WOW_DEVSETUP_OS=Linux "$B" "$SH_SCRIPT" link -n -f forever --wow-root "$B_ROOT" "$DEV" 2>&1); RC=$?
	ok "B with WOW_FOREVER_FOLDER=_retail_: target _retail_ and the shared-folder warning" '[ $RC -eq 0 ] && has "_retail_/Interface/AddOns" && has "share "'

	run_sh "$B" C link -n -f forever "$DEV"
	ok "C (beta slot is the live game): forever -> _classic_beta_ 1.60.2" '[ $RC -eq 0 ] && has "_classic_beta_/Interface/AddOns" && has "product wow_classic_beta 1.60.2.71000"'
	run_sh "$B" R list
	ok "R (beta slot reused): only _forever_ qualifies" 'has "-f forever -> _forever_ (product wowf 1.60.2.71000)" && has "Classic beta slot (not running Forever)"'
	run_sh_root "$B" link -n -f forever --wow-root "$(mac U)" "$DEV"
	ok "U (degraded): the beta folder, with a warning about the untied wowf product" '[ $RC -eq 0 ] && has "_classic_beta_/Interface/AddOns" && has "also lists wowf 1.60.1.70245, but"'

	run_sh "$B" S2 link -n -f forever --forever-folder _nope_ "$DEV"
	ok "pin to a folder that does not exist is an error" '[ $RC -ne 0 ] && has "not found"'
	run_sh "$B" S2 link -n -f forever --forever-folder forever "$DEV"
	ok "a pin that names forever itself is rejected" '[ $RC -ne 0 ] && has "must be a folder"'
}

# ----------------------------------------------------------------- link-addons.ps1
run_ps() { # scenario (Windows layout via product.db), then link-addons.ps1 arguments
	local s=$1; shift
	OUT=$(WOW_DEVSETUP_OS=Windows WOW_DEVSETUP_TEST_PREFIX="$F/$s/win" "$PWSH" -NoProfile -NonInteractive -File "$PS_SCRIPT" "$@" 2>&1); RC=$?
	OUT=$(printf '%s\n' "$OUT" | sed 's/\x1b\[[0-9;]*m//g')
}

test_ps() {
	local S2 B_ROOT
	echo "== link-addons.ps1 with $PWSH ($("$PWSH" -NoProfile -Command '$PSVersionTable.PSVersion.ToString()'))"
	fresh
	S2=$(win S2)
	run_ps S1 link -Flavor forever -DryRun "$DEV"
	ok "S1 (beta only): forever -> _classic_beta_" '[ $RC -eq 0 ] && has "_classic_beta_" && has "forever: product wow_classic_beta 1.60.1.70425"'
	run_ps S2 list
	ok "S2 list: ambiguous, both candidates listed with product and build" \
		'[ $RC -eq 0 ] && has "-Flavor forever -> ambiguous: _classic_beta_ _forever_" && hasre "_classic_beta_ +product wow_classic_beta 1.60.1.70425" && hasre "_forever_ +product wowf 1.60.1.70245"'
	run_ps S2 link -Flavor forever "$DEV"
	ok "S2 link -Flavor forever: refused, nothing linked" \
		'[ $RC -ne 0 ] && has "is ambiguous" && has "nothing was changed" && [ ! -e "$S2/_classic_beta_/Interface/AddOns/Tx_Bags" ] && [ ! -e "$S2/_forever_/Interface/AddOns/Tx_Bags" ]'
	run_ps S2 link -Flavor _forever_ "$DEV"
	ok "S2 link -Flavor _forever_ links the stress test" '[ $RC -eq 0 ] && [ -L "$S2/_forever_/Interface/AddOns/Tx_Bags" ]'
	OUT=$(WOW_FOREVER_FOLDER=_forever_ WOW_DEVSETUP_OS=Windows WOW_DEVSETUP_TEST_PREFIX="$F/S2/win" "$PWSH" -NoProfile -NonInteractive -File "$PS_SCRIPT" status -Flavor forever "$DEV" 2>&1); RC=$?
	ok "S2 WOW_FOREVER_FOLDER=_forever_ pins forever" '[ $RC -eq 0 ] && has "pinned by" && has "Tx_Bags: linked"'
	run_ps S2 unlink -Flavor forever -ForeverFolder _forever_ "$DEV"
	ok "S2 -ForeverFolder _forever_ pins forever (unlink)" '[ $RC -eq 0 ] && [ ! -e "$S2/_forever_/Interface/AddOns/Tx_Bags" ]'
	run_ps A link -Flavor forever -DryRun "$DEV"
	ok "A (launch, beta still installed): refused" '[ $RC -ne 0 ] && hasre "_forever_ +product wowf 1.60.2.71000"'
	run_ps A2 link -Flavor forever -DryRun "$DEV"
	ok "A2 (launch, beta uninstalled): forever -> _forever_" '[ $RC -eq 0 ] && has "_forever_" && has "WoW: Forever (new folder)"'
	B_ROOT=$(win B)
	OUT=$(WOW_DEVSETUP_OS=Linux WOW_DEVSETUP_TEST_PREFIX='' "$PWSH" -NoProfile -NonInteractive -File "$PS_SCRIPT" list -WowRoot "$B_ROOT" 2>&1 | sed 's/\x1b\[[0-9;]*m//g'); RC=$?
	ok "B (shared _retail_ + stale beta): ambiguous" 'has "ambiguous" && hasre "_retail_ +product wow 12.1.7.70500; lastAddonVersion 16001"'
	OUT=$(WOW_DEVSETUP_OS=Linux WOW_DEVSETUP_TEST_PREFIX='' "$PWSH" -NoProfile -NonInteractive -File "$PS_SCRIPT" link -WowRoot "$B_ROOT" -Flavor forever -ForeverFolder retail -DryRun "$DEV" 2>&1 | sed 's/\x1b\[[0-9;]*m//g'); RC=$?
	ok "B with -ForeverFolder retail: _retail_ and the shared-folder warning" '[ $RC -eq 0 ] && has "_retail_" && has "share "'
	OUT=$(WOW_DEVSETUP_OS=Linux WOW_DEVSETUP_TEST_PREFIX='' "$PWSH" -NoProfile -NonInteractive -File "$PS_SCRIPT" link -WowRoot "$(win U)" -Flavor forever -DryRun "$DEV" 2>&1 | sed 's/\x1b\[[0-9;]*m//g'); RC=$?
	ok "U (degraded): the beta folder, with a warning about the untied wowf product" '[ $RC -eq 0 ] && has "_classic_beta_" && has "also lists wowf 1.60.1.70245, but"'
	run_ps S2 link -Flavor forever -ForeverFolder forever -DryRun "$DEV"
	ok "a pin that names forever itself is rejected" '[ $RC -ne 0 ] && has "must be a folder"'
}

printf '%s\n' "$BASHES" | while IFS= read -r b; do [ -n "$b" ] && echo "$b"; done > "$TMP_ROOT/bashes"
while IFS= read -r b; do
	test_sh "$b"
done < "$TMP_ROOT/bashes"
if [ -n "$PWSH" ]; then
	test_ps
else
	echo "== link-addons.ps1: skipped (no pwsh; pass --pwsh PATH)"
fi
echo
echo "RESULT: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
