#!/usr/bin/env bash
# link-addons.sh - link addon folders from a dev checkout into a WoW flavor's
# Interface/AddOns folder with symlinks (macOS; also runs on Linux for CI/Wine).
# Windows users: use link-addons.ps1 (directory junctions) instead.
#
# Works with macOS /bin/bash 3.2 (tested with Apple's bash-144 = 3.2.57 source)
# and bash 5.x. Uses only POSIX tools: ln, rm, mv, mkdir, readlink, od, awk.
#
# Find installs and flavors; symlink into AddOns; show; remove; dry run (-n changes nothing);
# pin what 'forever' means:
#   bash link-addons.sh list
#   bash link-addons.sh link -f forever ~/dev/MyAddon
#   bash link-addons.sh status -f forever ~/dev/MyAddon
#   bash link-addons.sh unlink --restore -f forever ~/dev/MyAddon
#   bash link-addons.sh link -n -f forever ~/dev/MyAddon
#   WOW_FOREVER_FOLDER=_forever_ bash link-addons.sh link -f forever ~/dev/MyAddon
# If more than one folder looks like WoW: Forever (for example the beta folder and the
# stress-test product), '-f forever' stops and lists them: pick one with -f _folder_ or
# pin it with --forever-folder / WOW_FOREVER_FOLDER.
#
# Safety rules: never deletes a real folder (moves it to
# <flavor>/Interface/AddOns-devsetup-backup/<Name>.<timestamp>), only removes
# symlinks it can verify, and every change is printed (or only printed with -n).

VERSION="1.2.0"
PROG=${0##*/}

usage() {
	cat <<EOF
$PROG $VERSION - link addon dev checkouts into World of Warcraft's AddOns folder

Usage: $PROG [list|link|unlink|status] [options] [ADDON_DIR ...]

Commands:
  list     Show detected WoW installs and their flavor folders (default
           when no ADDON_DIR is given).
  link     Symlink each addon into <root>/<flavor>/Interface/AddOns (default
           when ADDON_DIR is given). An existing real folder is moved to
           <flavor>/Interface/AddOns-devsetup-backup/ first.
  unlink   Remove links that point at ADDON_DIR (never deletes real folders).
  status   Show what <AddOns>/<Name> currently is for each ADDON_DIR.

ADDON_DIR is a folder with a .toc file (linked under the TOC's base name, so
~/dev/my-repo with MyAddon.toc becomes AddOns/MyAddon), or a repo whose
sub-folders are addons (each one is linked).

Options:
  -f, --flavor NAME   retail | ptr | xptr | beta | classic (MoP) | era |
                      anniversary | classic_ptr | era_ptr | forever, or a literal
                      folder name such as _classic_beta_. 'forever' picks the
                      folder whose product version (.build.info) is 1.60 or
                      later, or whose WTF/Config.wtf says lastAddonVersion 160xx,
                      or _classic_beta_ (the Forever beta folder). If several
                      folders match, it lists them with product and build and
                      stops: pass -f _folder_ or --forever-folder.
      --forever-folder NAME
                      Make 'forever' mean this folder (a literal _name_ or an
                      alias such as retail). Also read from \$WOW_FOREVER_FOLDER.
                      Use it when several folders look like Forever (the beta
                      and the stress test, Oct 16-19) or if Forever runs from a
                      shared _retail_ folder.
  -r, --wow-root DIR  WoW install root (the folder that contains _retail_ etc.).
                      Also read from \$WOW_ROOT. Skips auto-detection.
      --product-db F  Battle.net product.db to read (default per OS).
  -n, --dry-run       Print what would happen; change nothing.
      --restore       unlink: move the newest backup back into AddOns.
      --force         link: replace a link that points somewhere else without
                      asking; unlink: remove such a link too.
  -h, --help          This help.

Detection order: --wow-root/\$WOW_ROOT; Battle.net product.db
(/Users/Shared/Battle.net/Agent/product.db on macOS; Wine: --product-db);
Spotlight (mdfind) on macOS; default /Applications/World of Warcraft.
EOF
}

# ---------------------------------------------------------------- helpers
DRY_RUN=""
US=$'\037'    # field separator for internal records (tab would collapse empty fields)
NL=$'\n'
say()  { printf '%s\n' "$*"; }
warn() { printf 'warning: %s\n' "$*" >&2; }
die()  { printf 'error: %s\n' "$*" >&2; exit 1; }

# run CMD...: print and execute, or only print in dry-run mode
run() {
	if [ -n "$DRY_RUN" ]; then
		printf '[dry-run] would run:'
	else
		printf '+'
	fi
	printf ' %q' "$@"
	printf '\n'
	[ -n "$DRY_RUN" ] && return 0
	"$@"
}

# physical absolute path of an existing directory (follows symlinks)
phys_dir() { (cd "$1" 2>/dev/null && pwd -P); }

# Test hooks: WOW_DEVSETUP_OS overrides uname (Darwin/Linux); WOW_DEVSETUP_TEST_PREFIX
# is prepended to built-in absolute default paths so fake trees can be used.
OS_NAME=${WOW_DEVSETUP_OS:-$(uname -s)}
TP=${WOW_DEVSETUP_TEST_PREFIX:-}

KNOWN_FLAVORS="_retail_ _ptr_ _xptr_ _beta_ _classic_ _classic_era_ _anniversary_ _classic_ptr_ _classic_era_ptr_ _classic_beta_"

flavor_label() {
	case $1 in
		_retail_)          echo "Retail (Midnight 12.x)" ;;
		_ptr_)             echo "Retail PTR" ;;
		_xptr_)            echo "Retail xPTR" ;;
		_beta_)            echo "Retail beta" ;;
		_classic_)         echo "MoP Classic (5.5.x)" ;;
		_classic_era_)     echo "Classic Era (1.15.x)" ;;
		_anniversary_)     echo "TBC Anniversary (2.5.x)" ;;
		_classic_ptr_)     echo "Classic PTR" ;;
		_classic_era_ptr_) echo "Classic Era PTR" ;;
		_classic_beta_)    echo "WoW: Forever beta (wow_classic_beta)" ;;
		*)                 echo "unknown flavor folder (new product? check for Forever)" ;;
	esac
}

# alias -> folder name (forever is resolved per root, see resolve_flavor)
flavor_alias() {
	case $(printf '%s' "$1" | tr '[:upper:]' '[:lower:]') in
		retail|mainline)            echo _retail_ ;;
		ptr)                        echo _ptr_ ;;
		xptr)                       echo _xptr_ ;;
		beta)                       echo _beta_ ;;
		classic|mists|mop)          echo _classic_ ;;
		era|classic_era|vanilla)    echo _classic_era_ ;;
		anniversary|tbc)            echo _anniversary_ ;;
		classic_ptr)                echo _classic_ptr_ ;;
		era_ptr|classic_era_ptr)    echo _classic_era_ptr_ ;;
		forever|camelot)            echo @forever ;;
		_*_)                        printf '%s\n' "$1" ;;
		*)                          return 1 ;;
	esac
}

# SET lastAddonVersion "16001" from <flavor>/WTF/Config.wtf (instawow reads the same line)
last_addon_version() {
	[ -f "$1/WTF/Config.wtf" ] || return 0
	awk '/^SET lastAddonVersion/ { gsub(/[^0-9]/, "", $3); print $3; exit }' "$1/WTF/Config.wtf" 2>/dev/null
}

# flavor folders present in a root: every _name_ directory
flavor_dirs() {
	for d in "$1"/_*_; do
		[ -d "$d" ] && printf '%s\n' "${d##*/}"
	done
}

is_wow_root() {
	local f
	[ -d "$1" ] || return 1
	[ -f "$1/.build.info" ] && return 0
	for f in $KNOWN_FLAVORS; do
		[ -d "$1/$f" ] && return 0
	done
	for f in "$1"/_*_/.flavor.info; do
		[ -f "$f" ] && return 0
	done
	return 1
}

# ------------------------------------------- products, versions, Forever
# WoW: Forever's launch layout (2026-11-04) is unannounced. Three cases are handled:
#   A  its own product and folder (the stress test runs as product 'wowf')
#   B  a game type inside the retail product, sharing _retail_
#   C  the beta slot (product wow_classic_beta, folder _classic_beta_)
# so 'forever' is resolved from evidence instead of a fixed folder name.

PDB_MAP=""    # "<root>\037<folder>\037<product>" lines collected from product.db

# TACT product of a flavor folder: <folder>/.flavor.info (written by the Battle.net
# agent: a "Product Flavor!STRING:0" header line, then the product), else product.db.
flavor_product() { # $1 = root, $2 = folder
	local code="" r s c
	if [ -f "$1/$2/.flavor.info" ]; then
		code=$(LC_ALL=C awk -F'|' 'NR == 1 { sub(/^\357\273\277/, "") } { sub(/\r$/, "") } /!/ || /^#/ || /^[ \t]*$/ { next }
			{ gsub(/[ \t]/, "", $1); print $1; exit }' "$1/$2/.flavor.info" 2>/dev/null)
	fi
	if [ -z "$code" ] && [ -n "$PDB_MAP" ]; then
		while IFS=$US read -r r s c; do
			if [ "$r" = "$1" ] && [ "$s" = "$2" ]; then code=$c; break; fi
		done <<EOF
$PDB_MAP
EOF
	fi
	printf '%s\n' "$code"
}

# Version of product $2 in <root $1>/.build.info (BPSV; prefers an Active row)
build_info_version() {
	[ -n "$2" ] && [ -f "$1/.build.info" ] || return 0
	LC_ALL=C awk -F'|' -v want="$2" '{ sub(/\r$/, "") }
		NR == 1 { for (c = 1; c <= NF; c++) { if ($c ~ /^Product!/) p = c; if ($c ~ /^Version!/) v = c; if ($c ~ /^Active!/) a = c } next }
		p && v && $p == want && $v != "" { if (first == "") first = $v; if (a && $a == "1" && act == "") act = $v }
		END { if (act != "") print act; else if (first != "") print first }' "$1/.build.info" 2>/dev/null
}

# 1.60.x up to 1.99.x is WoW: Forever (Classic Era is 1.15.x); same band as interface 16000-19999
is_forever_build() {
	case $1 in 1.6[0-9].*|1.[7-9][0-9].*) return 0 ;; esac
	return 1
}

# beta, PTR and internal products: never the live game
is_test_product() {
	case $1 in
		*beta*|*ptr*|*alpha*|*dev*|*livetest*|wowt|wowz|wowv|wowv[0-9]*|wowe[0-9]*) return 0 ;;
	esac
	return 1
}

# Why folder $2 of root $1 looks like WoW: Forever; prints nothing if it does not
forever_evidence() {
	local prod bver v
	prod=$(flavor_product "$1" "$2")
	bver=$(build_info_version "$1" "$prod")
	if [ -n "$bver" ] && is_forever_build "$bver"; then
		printf 'product %s %s\n' "$prod" "$bver"
		return 0
	fi
	# A folder whose product is known to run another game is not Forever, whatever an old
	# Config.wtf says. _retail_ is the exception: Forever may share it (case B).
	if [ -n "$bver" ] && [ "$2" != _retail_ ]; then return 0; fi
	v=$(last_addon_version "$1/$2")
	if [ -n "$v" ] && [ "$v" -ge 16000 ] && [ "$v" -lt 20000 ]; then
		printf 'lastAddonVersion %s\n' "$v"
		return 0
	fi
	[ "$2" = _classic_beta_ ] && printf 'Forever beta folder\n'
	return 0
}

# flavor_label, corrected by what the folder actually holds (folder $2 of root $1)
folder_label() {
	local label why
	label=$(flavor_label "$2")
	why=$(forever_evidence "$1" "$2")
	case $2 in
		_retail_)       [ -n "$why" ] && label="Retail + WoW: Forever (shared folder?)" ;;
		_classic_beta_) [ -n "$why" ] || label="Classic beta slot (not running Forever)" ;;
		*)              if [ -n "$why" ]; then case $label in unknown*) label="WoW: Forever (new folder)" ;; esac; fi ;;
	esac
	printf '%s\n' "$label"
}

# Live products in <root $1>/.build.info with a Forever version that no folder could be
# tied to (no .flavor.info, not in product.db); prints "product version" lines
untied_forever_products() {
	local prod ver d tied
	[ -f "$1/.build.info" ] || return 0
	while IFS=$US read -r prod ver; do
		if [ -z "$prod" ] || ! is_forever_build "$ver" || is_test_product "$prod"; then continue; fi
		tied=""
		for d in $(flavor_dirs "$1"); do
			[ "$(flavor_product "$1" "$d")" = "$prod" ] && tied=1
		done
		[ -n "$tied" ] || printf '%s %s\n' "$prod" "$ver"
	done <<EOF
$(LC_ALL=C awk -F'|' -v us="$US" '{ sub(/\r$/, "") }
	NR == 1 { for (c = 1; c <= NF; c++) { if ($c ~ /^Product!/) p = c; if ($c ~ /^Version!/) v = c } next }
	p && v && $p != "" { print $p us $v }' "$1/.build.info" 2>/dev/null)
EOF
}

# Forever candidates in root $1, one "<folder>\037<evidence>\037<product>" line each
forever_candidates() {
	local d why
	for d in $(flavor_dirs "$1"); do
		why=$(forever_evidence "$1" "$d")
		[ -n "$why" ] && printf '%s%s%s%s%s\n' "$d" "$US" "$why" "$US" "$(flavor_product "$1" "$d")"
	done
}

# One line per Forever candidate in root $1: folder, product and build, and the evidence when
# it is not the product version (for the "pick one" messages)
describe_candidates() {
	local d why prod bver text
	while IFS=$US read -r d why prod; do
		[ -n "$d" ] || continue
		bver=$(build_info_version "$1" "$prod")
		if [ -n "$prod" ]; then
			text="product $prod ${bver:-(not in .build.info)}"
		else
			text="product unknown"
		fi
		case $why in product*) ;; *) text="$text; $why" ;; esac
		printf '      %-18s %s\n' "$d" "$text"
	done <<EOF
$(forever_candidates "$1")
EOF
}

# ------------------------------------------------- product.db (protobuf)
# Battle.net product.db is a protobuf: repeated field 1 = product install
# { 2: product code, 3: settings { 1: install path, 13: game subfolder }, 6: family }.
# Field numbers as decoded by WowUp (src/common/wowup/product-db.ts).
# Prints code, subfolder and install path (separated by \037) for wow products.
read_product_db() {
	LC_ALL=C od -An -v -tu1 "$1" 2>/dev/null | LC_ALL=C awk '
	{ for (i = 1; i <= NF; i++) b[n++] = $i + 0 }
	function varint(   v, m, c) {
		v = 0; m = 1
		do { c = b[pos++]; v += (c % 128) * m; m *= 128 } while (c >= 128 && pos < n)
		return v
	}
	function bytes(s, e,   o, j) { o = ""; for (j = s; j < e; j++) o = o sprintf("%c", b[j]); return o }
	function skip(wt,   l) {
		if (wt == 0) varint()
		else if (wt == 1) pos += 8
		else if (wt == 2) { l = varint(); pos += l }
		else if (wt == 5) pos += 4
		else { bad = 1; pos = n }
	}
	END {
		pos = 0
		while (pos < n && !bad) {
			key = varint(); f = int(key / 8); wt = key % 8
			if (f != 1 || wt != 2) { skip(wt); continue }
			pend = varint(); pend += pos
			code = ""; fam = ""; loc = ""; subf = ""
			while (pos < pend && !bad) {
				k2 = varint(); f2 = int(k2 / 8); w2 = k2 % 8
				if (w2 != 2) { skip(w2); continue }
				e2 = varint(); s2 = pos; e2 += pos
				if (f2 == 2) code = bytes(s2, e2)
				else if (f2 == 6) fam = bytes(s2, e2)
				else if (f2 == 3) {
					while (pos < e2 && !bad) {
						k3 = varint(); f3 = int(k3 / 8); w3 = k3 % 8
						if (w3 != 2) { skip(w3); continue }
						l3 = varint()
						if (f3 == 1) loc = bytes(pos, pos + l3)
						else if (f3 == 13) subf = bytes(pos, pos + l3)
						pos += l3
					}
				}
				pos = e2
			}
			pos = pend
			if (fam == "wow" || code ~ /^wow/) printf "%s\037%s\037%s\n", code, subf, loc
		}
	}'
}

# Map a Windows install path (C:/... or C:\...) from a product.db that lives
# inside a Wine prefix (.../drive_c/ProgramData/...) to the prefix's drive_c.
map_wine_path() { # $1 = install path, $2 = product.db path
	case $1 in [A-Za-z]:[\\/]*) ;; *) return 1 ;; esac
	case $2 in */drive_c/*) ;; *) return 1 ;; esac
	printf '%s/%s\n' "${2%%/drive_c/*}/drive_c" "$(printf '%s' "${1#???}" | tr '\134' '/')"
}

# ------------------------------------------------------- root detection
ROOTS=()      # physical paths
ROOT_SRC=()   # where each was found

add_root() { # $1 = path, $2 = source label
	local p i
	is_wow_root "$1" || return 0
	p=$(phys_dir "$1") || return 0
	i=0
	while [ $i -lt ${#ROOTS[@]} ]; do
		if [ "${ROOTS[$i]}" = "$p" ]; then
			case ${ROOT_SRC[i]} in *"$2"*) ;; *) ROOT_SRC[i]="${ROOT_SRC[i]}, $2" ;; esac
			return 0
		fi
		i=$((i + 1))
	done
	ROOTS[${#ROOTS[@]}]=$p
	ROOT_SRC[${#ROOT_SRC[@]}]=$2
}

detect_roots() {
	local db loc mapped app _code _sub p
	if [ -n "$OPT_ROOT" ]; then
		is_wow_root "$OPT_ROOT" || die "--wow-root '$OPT_ROOT' does not look like a WoW install (no .build.info or _retail_/_classic_*_ folders)"
		add_root "$OPT_ROOT" "--wow-root"
		return
	fi
	db=$OPT_DB
	if [ -z "$db" ] && [ "$OS_NAME" = Darwin ]; then
		db="$TP/Users/Shared/Battle.net/Agent/product.db"
	fi
	if [ -n "$db" ]; then
		if [ -f "$db" ]; then
			while IFS=$'\037' read -r _code _sub loc; do
				[ -n "$loc" ] || continue
				case $loc in
					/*) mapped="$TP$loc" ;;
					*) mapped=$(map_wine_path "$loc" "$db") || { warn "cannot map product.db path '$loc'"; continue; } ;;
				esac
				add_root "$mapped" "product.db"
				# remember which product owns which folder (labels and 'forever' resolution)
				if [ -n "$_code" ] && [ -n "$_sub" ] && p=$(phys_dir "$mapped"); then
					PDB_MAP="$PDB_MAP$p$US$_sub$US$_code$NL"
				fi
			done <<EOF
$(read_product_db "$db")
EOF
		elif [ -n "$OPT_DB" ]; then
			warn "product.db not found: $db"
		fi
	fi
	if [ "$OS_NAME" = Darwin ] && [ -z "$TP" ] && command -v mdfind >/dev/null 2>&1; then
		# the .app bundle sits inside the flavor folder: <root>/<flavor>/World of Warcraft*.app
		while IFS= read -r app; do
			[ -n "$app" ] && add_root "${app%/*/*}" "Spotlight"
		done <<EOF
$(mdfind "kMDItemCFBundleIdentifier == 'com.blizzard.worldofwarcraft'" 2>/dev/null)
EOF
	fi
	if [ "$OS_NAME" = Darwin ]; then
		add_root "$TP/Applications/World of Warcraft" "default path"
	fi
	if [ -n "${WINEPREFIX:-}" ]; then
		add_root "$WINEPREFIX/drive_c/Program Files (x86)/World of Warcraft" "WINEPREFIX default path"
	fi
}

# --forever-folder / WOW_FOREVER_FOLDER as a folder name; fails on a bad value
forever_pin() {
	local f
	if f=$(flavor_alias "$OPT_FOREVER_DIR") && [ "$f" != @forever ]; then
		printf '%s\n' "$f"
		return 0
	fi
	warn "--forever-folder/WOW_FOREVER_FOLDER '$OPT_FOREVER_DIR' must be a folder such as _forever_ or an alias such as retail"
	return 1
}

# resolve requested flavor to a folder name inside root $1; prints the folder. Returns 1 when
# no folder qualifies and 2 when several look like WoW: Forever. It never picks one of those
# by itself: from Oct 16 to Oct 19 the beta and the stress test are both installed and either
# may be the client you mean, and at launch the old beta folder may still be there.
resolve_flavor() { # $1 = root, $2 = alias result
	local root=$1 want=$2 d why prod cands="" n=0
	if [ "$want" != @forever ]; then
		printf '%s\n' "$want"
		return 0
	fi
	if [ -n "$OPT_FOREVER_DIR" ]; then
		forever_pin
		return
	fi
	while IFS=$US read -r d why prod; do
		[ -n "$d" ] || continue
		cands="$cands $d"; n=$((n + 1))
	done <<EOF
$(forever_candidates "$root")
EOF
	if [ $n -eq 1 ]; then
		printf '%s\n' "${cands# }"
		return 0
	fi
	[ $n -gt 1 ] || return 1
	warn "several folders in $root look like WoW: Forever, so 'forever' is ambiguous:"
	describe_candidates "$root" >&2
	printf '%s\n' "  Pick one: -f _folder_ for this command, or --forever-folder _folder_ (or WOW_FOREVER_FOLDER=_folder_)" \
		"  so that 'forever' means that folder. Uninstalling a client you no longer test on (the beta" \
		"  after Oct 19) makes 'forever' unambiguous again." >&2
	return 2
}

# ------------------------------------------------------ addon discovery
# Base name of a TOC file without a client suffix (MyAddon_Camelot.toc -> MyAddon)
toc_base() {
	printf '%s\n' "${1%.toc}" | sed -E 's/[-_]([Mm]ainline|[Ss]tandard|[Cc]lassic|[Vv]anilla|TBC|[Tt]bc|BCC|[Bb]cc|[Ww]rath|WOTLKC|[Cc]ata|[Mm]ists|[Cc]amelot|[Ff]orever)$//'
}

ADDON_SRC=()
ADDON_NAME=()

add_addon_dir() { # $1 = dir that contains toc files
	local dir=$1 base names="" n count=0 name="" t
	for t in "$dir"/*.toc; do
		[ -f "$t" ] || continue
		base=$(toc_base "${t##*/}")
		case " $names " in *" $base "*) ;; *) names="$names $base"; count=$((count + 1)) ;; esac
	done
	[ $count -gt 0 ] || return 1
	for n in $names; do
		[ "$n" = "${dir##*/}" ] && name=$n
	done
	if [ -z "$name" ]; then
		[ $count -eq 1 ] || die "$dir has TOCs for several addon names ($names ) - pass the addon sub-folder instead"
		name=${names# }
		say "note: ${dir##*/} contains $name.toc, so it will be linked as AddOns/$name"
	fi
	ADDON_SRC[${#ADDON_SRC[@]}]=$dir
	ADDON_NAME[${#ADDON_NAME[@]}]=$name
}

collect_addons() {
	local arg dir sub found
	for arg in "$@"; do
		dir=$(phys_dir "$arg") || die "not a directory: $arg"
		add_addon_dir "$dir" && continue
		found=""
		for sub in "$dir"/*/; do
			sub=${sub%/}
			[ -d "$sub" ] || continue
			case ${sub##*/} in .*) continue ;; esac  # .git, .release, ...
			ls "$sub"/"${sub##*/}"*.toc >/dev/null 2>&1 || continue
			add_addon_dir "$sub" && found=1
		done
		[ -n "$found" ] || die "no .toc file in $arg or its sub-folders"
	done
}

# ----------------------------------------------------------- link state
# prints: missing | link-ok | link-other:<target> | dangling:<target> | dir | file
target_state() { # $1 = target path, $2 = source physical path
	local t=$1 src=$2 dest p
	if [ -L "$t" ]; then
		dest=$(readlink "$t")
		p=$(phys_dir "$t") || { echo "dangling:$dest"; return; }
		if [ "$p" = "$src" ]; then echo link-ok; else echo "link-other:$dest"; fi
	elif [ -d "$t" ]; then
		echo dir
	elif [ -e "$t" ]; then
		echo file
	else
		echo missing
	fi
}

backup_path() { # $1 = AddOns dir, $2 = name
	local base stamp b
	base="${1%/*}/AddOns-devsetup-backup"
	stamp=$(date +%Y%m%d-%H%M%S)
	b="$base/$2.$stamp"
	[ -e "$b" ] && b="$b.$$"
	printf '%s\n' "$b"
}

# ------------------------------------------------------------- commands
cmd_list() {
	local i root d v label addons links a flt="" bi prod bver info r fc names x rest
	[ -n "$OPT_FLAVOR" ] && flt=$(flavor_alias "$OPT_FLAVOR")
	if [ ${#ROOTS[@]} -eq 0 ]; then
		say "No WoW install found. Pass --wow-root \"/path/to/World of Warcraft\"."
		return 1
	fi
	i=0
	while [ $i -lt ${#ROOTS[@]} ]; do
		root=${ROOTS[$i]}
		say "WoW install: $root   (found via: ${ROOT_SRC[$i]})"
		bi="$root/.build.info"
		if [ -f "$bi" ]; then
			awk -F'|' '{ sub(/\r$/, "") } NR == 1 { for (c = 1; c <= NF; c++) { if ($c ~ /^Product!/) p = c; if ($c ~ /^Version!/) v = c } next }
				p && v && $p != "" { printf "    .build.info product %-22s version %s\n", $p, $v }' "$bi" 2>/dev/null
		fi
		for d in $(flavor_dirs "$root"); do
			if [ -n "$flt" ] && [ "$flt" != @forever ] && [ "$flt" != "$d" ]; then continue; fi
			label=$(folder_label "$root" "$d")
			v=$(last_addon_version "$root/$d")
			prod=$(flavor_product "$root" "$d")
			bver=$(build_info_version "$root" "$prod")
			info="${prod:+, product $prod${bver:+ $bver}}"
			addons=0; links=""
			if [ -d "$root/$d/Interface/AddOns" ]; then
				for a in "$root/$d/Interface/AddOns"/*; do
					[ -e "$a" ] || [ -L "$a" ] || continue
					addons=$((addons + 1))
					[ -L "$a" ] && links="$links ${a##*/}"
				done
				printf '  %-18s %-40s AddOns: %s folder(s)%s%s%s\n' "$d" "$label" "$addons" \
					"${v:+, lastAddonVersion $v}" "$info" "${links:+, dev links:$links}"
			else
				printf '  %-18s %-40s (no Interface/AddOns yet)%s%s\n' "$d" "$label" "${v:+, lastAddonVersion $v}" "$info"
			fi
		done
		# what '-f forever' would pick in this install, and why
		fc=$(forever_candidates "$root")
		if r=$(resolve_flavor "$root" @forever 2>/dev/null); then
			if [ -n "$OPT_FOREVER_DIR" ]; then
				x="pinned by --forever-folder/WOW_FOREVER_FOLDER"
				[ -d "$root/$r" ] || x="$x; no such folder in this install"
			else
				x=$(forever_evidence "$root" "$r")
			fi
			say "  -f forever -> $r ($x)"
			[ "$r" = _retail_ ] && say "     _retail_ is shared: addons linked there load in WoW: Forever and in retail (README, launch day)"
		elif [ -n "$fc" ]; then
			names=""
			while IFS=$US read -r x rest; do [ -n "$x" ] && names="$names $x"; done <<EOF
$fc
EOF
			say "  -f forever -> ambiguous:$names (several folders look like WoW: Forever):"
			describe_candidates "$root"
			say "     pick one: -f _folder_, or --forever-folder _folder_ / WOW_FOREVER_FOLDER=_folder_"
		else
			say "  -f forever -> no WoW: Forever folder found in this install"
		fi
		i=$((i + 1))
	done
	say "Note: WoW: Forever's launch layout (2026-11-04) is unannounced: the beta uses _classic_beta_,"
	say "the stress test is product wowf (its own folder). With both installed, link into each one by"
	say "folder name (-f _classic_beta_, -f _forever_). If Forever runs from _retail_, use WOW_FOREVER_FOLDER=_retail_."
}

# pick root + flavor folder for link/unlink/status; sets ROOT, FLAVOR_DIR, ADDONS_DIR
pick_target() {
	local want i root f rc hits=0 ambiguous="" why
	[ -n "$OPT_FLAVOR" ] || die "--flavor is required (e.g. -f forever, -f retail, -f _classic_beta_). Run '$PROG list' to see folders."
	want=$(flavor_alias "$OPT_FLAVOR") || die "unknown flavor '$OPT_FLAVOR'"
	[ ${#ROOTS[@]} -gt 0 ] || die "no WoW install found; pass --wow-root \"/path/to/World of Warcraft\""
	i=0
	while [ $i -lt ${#ROOTS[@]} ]; do
		root=${ROOTS[$i]}
		f=$(resolve_flavor "$root" "$want"); rc=$?
		if [ $rc -eq 2 ]; then
			ambiguous="$ambiguous $root"
		elif [ $rc -eq 0 ] && [ -d "$root/$f" ]; then
			hits=$((hits + 1)); ROOT=$root; FLAVOR_DIR=$f
		fi
		i=$((i + 1))
	done
	[ -z "$ambiguous" ] || die "'$OPT_FLAVOR' is ambiguous (the folders are listed above); nothing was changed. Pass -f _folder_, or --forever-folder _folder_ / WOW_FOREVER_FOLDER=_folder_."
	[ $hits -gt 0 ] || die "flavor '$OPT_FLAVOR' not found in: ${ROOTS[*]} (run '$PROG list'; install/launch that client once, or pass --flavor _folder_)"
	[ $hits -eq 1 ] || die "flavor '$OPT_FLAVOR' exists in several installs; pick one with --wow-root"
	ADDONS_DIR="$ROOT/$FLAVOR_DIR/Interface/AddOns"
	why=$(forever_evidence "$ROOT" "$FLAVOR_DIR")
	if [ "$want" = @forever ]; then
		if [ -n "$OPT_FOREVER_DIR" ]; then
			why="pinned by --forever-folder/WOW_FOREVER_FOLDER"
		else
			f=$(untied_forever_products "$ROOT" | awk 'NR > 1 { printf ", " } { printf "%s", $0 }')
			case $why in
				product*) ;;
				*) [ -n "$f" ] && warn ".build.info also lists $f, but no folder could be tied to it; if that is WoW: Forever, pass --flavor _its_folder_" ;;
			esac
		fi
		say "Target: $ADDONS_DIR  [$(folder_label "$ROOT" "$FLAVOR_DIR")] (forever: ${why:-no Forever evidence})"
	else
		say "Target: $ADDONS_DIR  [$(folder_label "$ROOT" "$FLAVOR_DIR")]"
	fi
	# case B: one AddOns folder for two game types
	if [ "$FLAVOR_DIR" = _retail_ ] && { [ "$want" = @forever ] || [ -n "$why" ]; }; then
		warn "WoW: Forever and retail share $ADDONS_DIR: an addon linked here loads in both game types unless its TOC gates them (## AllowLoadGameType and ## ExcludeLoadGameType; PATCH_DAY.md, TOC rule)"
	fi
}

cmd_link() {
	local i src name t state bk rc=0 addons_phys
	pick_target
	if [ ! -d "$ADDONS_DIR" ]; then
		run mkdir -p "$ADDONS_DIR" || die "cannot create $ADDONS_DIR"
	fi
	addons_phys=$(phys_dir "$ADDONS_DIR")
	i=0
	while [ $i -lt ${#ADDON_SRC[@]} ]; do
		src=${ADDON_SRC[$i]}; name=${ADDON_NAME[$i]}; t="$ADDONS_DIR/$name"
		i=$((i + 1))
		case "$src/" in "${addons_phys:-$ADDONS_DIR}/"*)
			warn "$src is inside the AddOns folder; refusing to link it to itself"; rc=1; continue ;;
		esac
		state=$(target_state "$t" "$src")
		case $state in
			link-ok)
				say "ok: $name already linked -> $src" ;;
			missing)
				run ln -s "$src" "$t" || { warn "could not create link $t"; rc=1; } ;;
			dangling:*|link-other:*)
				if [ "${state%%:*}" = link-other ] && [ -z "$OPT_FORCE" ]; then
					warn "$t links to ${state#*:}, not $src; re-run with --force to re-point it"; rc=1; continue
				fi
				say "re-pointing $name (was -> ${state#*:})"
				if ! { run rm "$t" && run ln -s "$src" "$t"; }; then warn "could not re-point $t"; rc=1; fi ;;
			dir|file)
				bk=$(backup_path "$ADDONS_DIR" "$name")
				say "$t is a real $state (installed copy?) - moving it to $bk"
				if ! { run mkdir -p "${bk%/*}" && run mv "$t" "$bk" && run ln -s "$src" "$t"; }; then
					warn "could not back up and link $t"; rc=1
				fi ;;
		esac
	done
	if [ $rc -eq 0 ] && [ -z "$DRY_RUN" ]; then
		say "Done. Restart the game client after adding or renaming a .toc file; /reload is enough for Lua/XML edits."
	fi
	return $rc
}

cmd_unlink() {
	local i src name t state bdir newest b rc=0
	pick_target
	i=0
	while [ $i -lt ${#ADDON_SRC[@]} ]; do
		src=${ADDON_SRC[$i]}; name=${ADDON_NAME[$i]}; t="$ADDONS_DIR/$name"
		i=$((i + 1))
		state=$(target_state "$t" "$src")
		case $state in
			link-ok|dangling:*)
				run rm "$t" || { warn "could not remove link $t"; rc=1; continue; } ;;
			link-other:*)
				if [ -z "$OPT_FORCE" ]; then
					warn "$t links to ${state#*:}, not $src; left alone (use --force to remove the link anyway)"; rc=1; continue
				fi
				run rm "$t" || { warn "could not remove link $t"; rc=1; continue; } ;;
			missing)
				say "ok: nothing at $t" ;;
			dir|file)
				warn "$t is a real $state, not a link; left alone"; rc=1; continue ;;
		esac
		if [ -n "$OPT_RESTORE" ]; then
			bdir="${ADDONS_DIR%/*}/AddOns-devsetup-backup"
			newest=""
			for b in "$bdir/$name".[0-9]*; do
				[ -e "$b" ] && newest=$b   # glob sorts by timestamp suffix
			done
			if [ -n "$newest" ]; then
				run mv "$newest" "$t" || { warn "could not restore $newest"; rc=1; }
			else
				say "no backup of $name to restore"
			fi
		fi
	done
	return $rc
}

cmd_status() {
	local i src name t state
	pick_target
	i=0
	while [ $i -lt ${#ADDON_SRC[@]} ]; do
		src=${ADDON_SRC[$i]}; name=${ADDON_NAME[$i]}; t="$ADDONS_DIR/$name"
		i=$((i + 1))
		state=$(target_state "$t" "$src")
		case $state in
			link-ok)      say "$name: linked -> $src" ;;
			link-other:*) say "$name: link to another checkout -> ${state#*:}" ;;
			dangling:*)   say "$name: BROKEN link -> ${state#*:}" ;;
			dir)          say "$name: real folder (installed copy, not linked)" ;;
			file)         say "$name: a file is in the way" ;;
			missing)      say "$name: not present" ;;
		esac
	done
}

# ----------------------------------------------------------------- main
CMD=""; OPT_FLAVOR=${WOW_FLAVOR:-}; OPT_ROOT=${WOW_ROOT:-}; OPT_DB=""; OPT_RESTORE=""; OPT_FORCE=""
OPT_FOREVER_DIR=${WOW_FOREVER_FOLDER:-}
ARGS=()
while [ $# -gt 0 ]; do
	case $1 in
		list|link|unlink|status)
			if [ -z "$CMD" ] && [ ${#ARGS[@]} -eq 0 ]; then CMD=$1; else ARGS[${#ARGS[@]}]=$1; fi ;;
		-f|--flavor)   [ $# -ge 2 ] || die "$1 needs a value"; OPT_FLAVOR=$2; shift ;;
		--flavor=*)    OPT_FLAVOR=${1#*=} ;;
		-r|--wow-root) [ $# -ge 2 ] || die "$1 needs a value"; OPT_ROOT=$2; shift ;;
		--wow-root=*)  OPT_ROOT=${1#*=} ;;
		--product-db)  [ $# -ge 2 ] || die "$1 needs a value"; OPT_DB=$2; shift ;;
		--forever-folder) [ $# -ge 2 ] || die "$1 needs a value"; OPT_FOREVER_DIR=$2; shift ;;
		--forever-folder=*) OPT_FOREVER_DIR=${1#*=} ;;
		-n|--dry-run)  DRY_RUN=1 ;;
		--restore)     OPT_RESTORE=1 ;;
		--force)       OPT_FORCE=1 ;;
		-h|--help)     usage; exit 0 ;;
		--version)     say "$PROG $VERSION"; exit 0 ;;
		--)            shift; while [ $# -gt 0 ]; do ARGS[${#ARGS[@]}]=$1; shift; done; break ;;
		-*)            usage >&2; die "unknown option $1" ;;
		*)             ARGS[${#ARGS[@]}]=$1 ;;
	esac
	shift
done
if [ -z "$CMD" ]; then
	if [ ${#ARGS[@]} -gt 0 ]; then CMD="link"; else CMD="list"; fi
fi
[ -n "$DRY_RUN" ] && say "Dry run: nothing will be changed."

detect_roots
case $CMD in
	list) cmd_list ;;
	link|unlink|status)
		[ ${#ARGS[@]} -gt 0 ] || die "$CMD needs at least one ADDON_DIR"
		collect_addons "${ARGS[@]}"
		"cmd_$CMD" ;;
esac
