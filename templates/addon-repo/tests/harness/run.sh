#!/usr/bin/env bash
# run.sh - run smoke.lua on WoW: Forever (current and pre-70170 beta builds), retail and Classic
# Era, and in German when Locales/deDE.lua exists.
#
#   bash tests/harness/run.sh [ADDON_DIR]
#
# ADDON_DIR defaults to the repository root (clone the libraries into Libs/ first; README.md,
# "Developing"). The Lint workflow runs it on the packaged folder, .release/<Name>. LUA picks the
# interpreter (default: the first of lua5.1, lua, luajit on PATH that is Lua 5.1 or LuaJIT); CI
# uses real Lua 5.1. SMOKE_SLASH and SMOKE_COMBAT are passed on to smoke.lua. On a client the TOC
# does not list, the game-type gate must keep the addon off (Forever-only addons). Tested with
# macOS's bash 3.2 and on Linux (Git Bash on Windows is untested). Exit status 0 when every run
# passed.
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
addon=$(cd "${1:-$HERE/../..}" 2>/dev/null && pwd) || { echo "No such folder: $1" >&2; exit 2; }
# WoW runs Lua 5.1: take the first interpreter that reports _VERSION "Lua 5.1" (LuaJIT does too),
# never a Lua 5.4 that happens to be called "lua".
is51() { [ "$("$1" -e 'io.write(_VERSION)' 2>/dev/null)" = "Lua 5.1" ]; }
if [ -n "${LUA:-}" ]; then
	is51 "$LUA" || { echo "LUA=$LUA is not Lua 5.1 or LuaJIT" >&2; exit 2; }
else
	for candidate in lua5.1 lua luajit; do
		if command -v "$candidate" >/dev/null 2>&1 && is51 "$candidate"; then LUA=$candidate; break; fi
	done
fi
[ -n "${LUA:-}" ] || { echo "No Lua 5.1 found: install Lua 5.1 or LuaJIT, or set LUA=/path/to/lua5.1" >&2; exit 2; }

toc=""
for t in "$addon"/*.toc; do
	[ -f "$t" ] && { toc=$t; break; }
done
[ -n "$toc" ] || { echo "No .toc file in $addon" >&2; exit 2; }
name=${toc##*/}
name=${name%.toc}
case $name in
	*_Camelot | *_Forever | *_Mainline | *_Standard | *_Vanilla | *_Classic) name=${name%_*} ;;
esac
interfaces=$(tr -d '\r' < "$toc" | sed -n 's/^## Interface:[[:space:]]*//p' | head -n 1)
gated=$(tr -d '\r' < "$toc" | grep -Ec '^## (Allow|Exclude)LoadGameType:')

runs="forever forever_pre70170"
lists() { echo " $(echo "$interfaces" | tr ',' ' ') " | grep -Eq " $1 "; }
if lists '[0-9]{6}' || [ "$gated" -gt 0 ]; then runs="$runs retail"; else echo "skip   retail: not in ## Interface (the client would show the addon as out of date)"; fi
if lists '11[0-9]{3}' || [ "$gated" -gt 0 ]; then runs="$runs classic_era"; else echo "skip   classic_era: not in ## Interface"; fi

echo "harness: $("$LUA" -v 2>&1 | head -n 1); addon: $name in $addon"
total=0
bad=0
one() { # flavor locale
	local out code
	out=$(SMOKE_ADDON=$name "$LUA" "$HERE/smoke.lua" "$addon" "$1" "$2" 2>&1)
	code=$?
	total=$((total + 1))
	if [ $code -ne 0 ]; then
		bad=$((bad + 1))
		printf 'FAILED %-18s %s\n' "$1" "$2"
		printf '%s\n' "$out" | grep -v '^PASS' | sed 's/^/    /'
	else
		printf 'ok     %-18s %-5s %s\n' "$1" "$2" "$(printf '%s\n' "$out" | tail -n 1)"
	fi
}
for flavor in $runs; do
	one "$flavor" enUS
done
if [ -f "$addon/Locales/deDE.lua" ]; then
	one forever deDE
fi
echo "runs: $total, failed runs: $bad"
[ $bad -eq 0 ]
