#!/usr/bin/env bash
# check-toc.sh - sanity checks for the addon's TOC files, run by the Lint workflow.
# Run it locally from the repository root before you push:  bash .github/scripts/check-toc.sh
# Tested with macOS's bash 3.2 and on Linux (Git Bash on Windows is untested).
#
# Checks every *.toc in the repository root:
#   - "## Interface:" exists and holds only 5-6 digit numbers, and no 00000 "unsupported
#     client" stub (the packager would read it as retail and tag the upload for retail)
#   - the Forever-only game-type gate ("## AllowLoadGameType: camelot" and
#     "## ExcludeLoadGameType: standard, classic") is not combined with retail or Classic
#     interface numbers; a Forever-only TOC without it gets a warning (PATCH_DAY.md, TOC rule).
#     Exception, launch layout B only (PATCH_DAY.md, "Launch day"): when WoW: Forever runs inside
#     the retail client and reports retail's interface number, its TOC needs the gate AND that
#     number. Allow it explicitly with this line in the TOC:
#       # check-toc: allow-gate-with-retail-interface
#   - every flavor whose interface number the TOC lists is in SUPPORTED_FLAVORS (Core.lua), and
#     the other way round (warnings): otherwise the addon loads on that client and stays inactive
#   - "## Version: @project-version@" (the packager fills in the git tag)
#   - "## X-Curse-Project-ID:" line exists (0 until the CurseForge project exists)
#   - no _Forever.toc (the BigWigs packager does not know that suffix; use _Camelot.toc)
#   - every file the TOC lists exists with exactly that spelling (Libs\ lines are skipped:
#     the packager fetches them), so a wrong upper/lower case is caught on any OS
#
#   bash .github/scripts/check-toc.sh --packaged .release/<Name>
# checks a folder the packager built instead: every file its TOC lists, Libs\ lines included,
# must be in it with exactly that spelling (a library renamed in the TOC but not in the library
# repository fails here; in game it fails with "Cannot find a library instance").

status=0
fail() {
	echo "::error file=$1::$2"
	status=1
}

# check_files TOC DIR SKIP_LIBS: every listed file exists under DIR with exactly that spelling
check_files() {
	local toc=$1 base=$2 skip_libs=$3
	tr -d '\r' < "$toc" | grep -v '^#' |
		sed -e 's/[[:space:]][[:space:]]*\[[A-Za-z][^]]*\].*$//' -e 's/[[:space:]]*$//' | {
		missing=0
		while IFS= read -r line; do
			[ -n "$line" ] || continue
			path=${line//\\//}
			case "$path" in
				Libs/*) [ "$skip_libs" = 1 ] && continue ;; # fetched by the packager
			esac
			case "$path" in
				*'['*) continue ;; # [Family], [Game], [TextLocale] path variables
			esac
			dir=$(dirname "$path")
			name=${path##*/}
			# Compare against the names the folder really holds, so a wrong upper/lower case is
			# caught even on the case-insensitive disks macOS and Windows use by default.
			match=0
			for entry in "$base/$dir"/*; do
				if [ "${entry##*/}" = "$name" ]; then
					match=1
					break
				fi
			done
			if [ "$match" -eq 0 ]; then
				where=$base
				[ "$base" = . ] && where="the repository"
				echo "::error file=$toc::Listed file '$line' does not exist in $where (check upper/lower case)."
				missing=1
			fi
		done
		exit "$missing"
	}
}

if [ "${1:-}" = "--packaged" ]; then
	pkg=${2:-}
	[ -n "$pkg" ] && [ -d "$pkg" ] || { echo "::error::--packaged needs the packaged addon folder, for example .release/Tx_Example"; exit 1; }
	found=0
	for toc in "$pkg"/*.toc; do
		[ -f "$toc" ] || continue
		found=1
		check_files "$toc" "$pkg" 0 || status=1
	done
	[ "$found" -eq 1 ] || { echo "::error::No .toc file in $pkg"; exit 1; }
	[ "$status" -eq 0 ] && echo "Packaged TOC checks passed: every listed file is in $pkg."
	exit "$status"
fi

# Lua flavor name (LibTx:GetFlavor) of an interface number, as the BigWigs packager maps them
flavor_of() {
	case "$1" in
		1[6-9][0-9][0-9][0-9]) echo forever ;;
		11[0-9][0-9][0-9]) echo classic_era ;;
		[2-5][0-9][0-9][0-9][0-9]) echo classic ;;
		*) echo retail ;;
	esac
}

# SUPPORTED_FLAVORS = { forever = true, ... } in the addon's Lua files (the template's Core.lua)
supported=""
sf_file=$(grep -l 'SUPPORTED_FLAVORS[[:space:]]*=[[:space:]]*{' ./*.lua 2>/dev/null | head -n 1)
if [ -n "$sf_file" ]; then
	supported=" $(tr -d '\r' < "$sf_file" | tr '\n' ' ' |
		sed -n 's/.*SUPPORTED_FLAVORS[[:space:]]*=[[:space:]]*{\([^}]*\)}.*/\1/p' |
		grep -o '[a-z_][a-z_]*[[:space:]]*=[[:space:]]*true' | sed 's/[[:space:]]*=.*//' | tr '\n' ' ')"
fi

found=0
for toc in *.toc; do
	[ -f "$toc" ] || continue
	found=1
	case "$toc" in
		*[-_][Ff]orever.toc) fail "$toc" "Rename to ${toc%[-_][Ff]orever.toc}_Camelot.toc: the packager does not recognize the _Forever suffix." ;;
	esac

	interface=$(tr -d '\r' < "$toc" | sed -n 's/^## Interface:[[:space:]]*//p' | head -n 1)
	other_flavor=""
	flavors=""
	if [ -z "$interface" ]; then
		fail "$toc" "Missing '## Interface:' line."
	else
		for value in $(echo "$interface" | tr ',' ' '); do
			case "$value" in
				0*) fail "$toc" "'## Interface:' value '$value' is a 'client not supported' stub. The packager reads it as a retail version and tags the CurseForge and Wago uploads for retail too. Delete the stub TOC." ;;
				16[0-9][0-9][0-9]) flavors="$flavors forever" ;;
				[0-9][0-9][0-9][0-9][0-9] | [0-9][0-9][0-9][0-9][0-9][0-9])
					other_flavor="$other_flavor $value"
					flavors="$flavors $(flavor_of "$value")" ;;
				*) fail "$toc" "'## Interface:' value '$value' is not a 5 or 6 digit interface number." ;;
			esac
		done
	fi

	# Forever-only gate: the Allow line names camelot, the Exclude line names standard and classic.
	allow=$(tr -d '\r' < "$toc" | sed -n 's/^## AllowLoadGameType:[[:space:]]*//p' | head -n 1)
	exclude=$(tr -d '\r' < "$toc" | sed -n 's/^## ExcludeLoadGameType:[[:space:]]*//p' | head -n 1)
	layout_b=0
	if tr -d '\r' < "$toc" | grep -q '^# check-toc: allow-gate-with-retail-interface'; then
		layout_b=1
	fi
	gated=0
	if echo "$allow" | grep -qiw camelot; then
		gated=1
	fi
	if echo "$exclude" | grep -qiw standard && echo "$exclude" | grep -qiw classic; then
		gated=1
	fi
	if [ "$gated" -eq 1 ] && [ -n "$other_flavor" ]; then
		classic_numbers=""
		for value in $other_flavor; do
			[ "$(flavor_of "$value")" = retail ] || classic_numbers="$classic_numbers $value"
		done
		if [ "$layout_b" -eq 1 ] && [ -z "$classic_numbers" ]; then
			echo "::notice file=$toc::Gate with retail interface number(s)$other_flavor allowed by '# check-toc: allow-gate-with-retail-interface' (launch layout B: Forever inside the retail client). Remove that line and the number once Forever has its own client."
			flavors=" forever"
		elif [ "$layout_b" -eq 1 ]; then
			fail "$toc" "'# check-toc: allow-gate-with-retail-interface' covers retail numbers only; the gate blocks the Classic client(s) of$classic_numbers."
		else
			fail "$toc" "The Forever-only game-type gate (## AllowLoadGameType / ## ExcludeLoadGameType) blocks retail and Classic, but '## Interface:' also lists$other_flavor. Delete the two gate lines for a multi-flavor TOC, and add those flavors to SUPPORTED_FLAVORS in Core.lua. (Launch layout B only: see the line '# check-toc: allow-gate-with-retail-interface' in this script's header and PATCH_DAY.md.)"
		fi
	elif [ "$layout_b" -eq 1 ]; then
		echo "::warning file=$toc::'# check-toc: allow-gate-with-retail-interface' is set but the TOC has no Forever-only gate with a retail number; remove the line."
	fi
	if [ -n "$interface" ] && [ -z "$other_flavor" ]; then
		case "$toc" in
			*[-_][Cc]amelot.toc) ;; # only Forever reads a _Camelot TOC
			*)
				if ! { echo "$exclude" | grep -qiw standard && echo "$exclude" | grep -qiw classic; }; then
					echo "::warning file=$toc::Forever-only TOC without '## ExcludeLoadGameType: standard, classic' (and '## AllowLoadGameType: camelot'): retail and Classic clients may load it where they share an AddOns folder with Forever."
				fi
				;;
		esac
	fi

	# The TOC's flavors and SUPPORTED_FLAVORS must agree, or the addon loads and stays inactive.
	if [ -n "$sf_file" ]; then
		for f in $(echo "$flavors" | tr ' ' '\n' | sort -u); do
			case "$supported" in
				*" $f "*) ;;
				*) echo "::warning file=$toc::'## Interface:' lists a $f client, but SUPPORTED_FLAVORS in $sf_file does not include $f: the addon would load there and stay inactive. Add '$f = true' to SUPPORTED_FLAVORS (or remove the number)." ;;
			esac
		done
		for f in $supported; do
			case " $flavors " in
				*" $f "*) ;;
				*) echo "::warning file=$sf_file::SUPPORTED_FLAVORS includes $f, but $toc lists no $f interface number: the client shows the addon as out of date there." ;;
			esac
		done
	fi

	if ! tr -d '\r' < "$toc" | grep -q '^## Version: @project-version@$'; then
		fail "$toc" "Use '## Version: @project-version@' so the packager writes the git tag."
	fi
	if ! grep -q '^## X-Curse-Project-ID:' "$toc"; then
		fail "$toc" "Missing '## X-Curse-Project-ID:' line (write 0 until the project exists)."
	fi

	check_files "$toc" . 1 || status=1
done

if [ "$found" -eq 0 ]; then
	echo "::error::No .toc file in the repository root."
	status=1
fi
[ "$status" -eq 0 ] && echo "TOC checks passed."
exit "$status"
