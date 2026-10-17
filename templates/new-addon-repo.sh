#!/usr/bin/env bash
# new-addon-repo.sh - start a new addon repository from templates/addon-repo.
#
#   bash new-addon-repo.sh DEST ADDON_NAME GITHUB_ORG ["Display Title"]
#   bash new-addon-repo.sh ~/dev/Ks_Bags Ks_Bags kestrel-studio "Ks Bags"
#
# Copies addon-repo/ to DEST and replaces the per-addon placeholders. They start with the team
# token: Tx before set-team.sh ran, your token after it (Ks in this example):
#   Ks_Example -> ADDON_NAME     folder, TOC file name, package-as, repository name
#   KsExample  -> ADDON_NAME without "_" (SavedVariables KsBagsDB, globals)
#   KSEXAMPLE / ksexample -> upper / lower case of that (SlashCmdList key, /command)
#   ks-example -> ADDON_NAME in lower case with "-" for "_" (CurseForge slug placeholder)
#   Ks Example -> Display Title (default: ADDON_NAME with "_" as spaces)
#   YOUR-ORG   -> GITHUB_ORG (set-team.sh already wrote the organization; it must then match
#                 team.conf)
# Files and folders whose names carry a placeholder are renamed as well.
#
# Everything is checked before DEST is touched, including that the team library's files in
# shared-lib/ carry the names its TOC and the addon TOC list (a text-only rename of LibTx-1.0 does
# not rename the files). The copy is built in a temporary folder next to DEST and moved into place
# only when no placeholder is left and every library the TOC loads is a .pkgmeta external, so a
# failed run leaves nothing behind. Tested with macOS's bash 3.2 and on Linux; Git Bash on Windows
# is untested. It does not run git; the next steps are printed at the end.

set -eu

usage() {
	sed -n '2,24p' "$0" | sed 's/^# \{0,1\}//' >&2
	exit 2
}
fail() { echo "error: $*" >&2; exit 2; }
if [ "$#" -lt 3 ] || [ "$#" -gt 4 ]; then usage; fi

dest=$1
name=$2
org=$3
title=${4:-$(echo "$name" | tr '_' ' ')}
here=$(cd "$(dirname "$0")" && pwd)
src="$here/addon-repo"

# ------------------------------------------------------------------ check everything first
[ -n "$dest" ] || fail "DEST must not be empty"
case "$name" in
	[A-Za-z]*) ;;
	*) fail "ADDON_NAME must start with a letter: $name" ;;
esac
if echo "$name" | grep -q '[^A-Za-z0-9_]'; then fail "ADDON_NAME may contain only letters, digits and _: $name"; fi
if echo "$name" | grep -Eqi '[-_](mainline|standard|classic|vanilla|bcc|tbc|wrath|wotlkc|cata|mists|camelot|forever)$'; then
	fail "ADDON_NAME must not end in a game-flavor suffix such as _Camelot: $name"
fi
echo "$org" | grep -Eq '^[A-Za-z0-9]([A-Za-z0-9]|-[A-Za-z0-9])*$' || fail "GITHUB_ORG may contain only letters, digits and single hyphens: $org"
case "$title" in
	'' | *'|'* | *\\* | *'&'*) fail "The title must not be empty or contain |, \\ or &: $title" ;;
esac
[ ! -e "$dest" ] || { echo "DEST already exists: $dest" >&2; exit 1; }

# The placeholder stem is whatever the template uses now: package-as in .pkgmeta and the TOC
# file name must agree (they do not after a half-done search and replace by hand).
stem=$(tr -d '\r' < "$src/.pkgmeta" | sed -n 's/^package-as:[[:space:]]*\([A-Za-z]*\)_Example[[:space:]]*$/\1/p' | head -n 1)
[ -n "$stem" ] || fail "addon-repo/.pkgmeta has no 'package-as: <Token>_Example' line; the template was edited by hand. Restore it (git checkout -- templates) and use set-team.sh."
echo "$stem" | grep -Eq '^[A-Z][a-z]{1,3}$' || fail "the template's token '$stem' is not one capital and 1 to 3 small letters; run set-team.sh"
[ -f "$src/${stem}_Example.toc" ] ||
	fail "addon-repo/${stem}_Example.toc is missing although .pkgmeta says ${stem}_Example: the template was renamed by hand. Restore it (git checkout -- templates) and run set-team.sh."

# The team library's template must agree with its own TOC and with the addon TOC. A text-only
# rename leaves shared-lib/LibTx-1.0.lua behind while the TOCs list LibKs-1.0.lua; the packaged
# addon then fails in game with "Cannot find a library instance".
exists_exact() { # DIR RELATIVE-PATH: the file exists with exactly this upper/lower case
	local entry
	for entry in "$1/$(dirname "$2")"/*; do
		[ "${entry##*/}" = "${2##*/}" ] && return 0
	done
	return 1
}
for libtoc in "$here"/shared-lib/*.toc; do
	[ -f "$libtoc" ] || continue
	lib=$(basename "$libtoc" .toc)
	for f in $(tr -d '\r' < "$libtoc" | grep -v '^#' | grep -v '^[[:space:]]*$' | sed 's|\\|/|g'); do
		exists_exact "$here/shared-lib" "$f" ||
			fail "shared-lib/$lib.toc lists $f, which is not in shared-lib/: the library was renamed by hand. Restore the templates (git checkout -- templates) and use set-team.sh."
	done
	for f in $(tr -d '\r' < "$src/${stem}_Example.toc" | sed -n "s/^Libs\\\\$lib\\\\//p" | sed 's|\\|/|g'); do
		exists_exact "$here/shared-lib" "$f" ||
			fail "addon-repo/${stem}_Example.toc loads Libs\\$lib\\$f, which is not in shared-lib/: the library was renamed by hand. Restore the templates (git checkout -- templates) and use set-team.sh."
	done
done

conf="$here/team.conf"
team_org=""
if [ -f "$conf" ]; then
	conf_token=$(sed -n 's/^TEAM_TOKEN=//p' "$conf" | tr -d '\r' | head -n 1)
	team_org=$(sed -n 's/^GITHUB_ORG=//p' "$conf" | tr -d '\r' | head -n 1)
	[ "$conf_token" = "$stem" ] || fail "team.conf says token $conf_token, the template uses $stem: run set-team.sh again"
	[ "$org" = "$team_org" ] || fail "GITHUB_ORG '$org' differs from team.conf ($team_org), which the templates already use"
fi
case "$name" in
	"${stem}_"?*) ;;
	*) echo "note: the team naming rule (CONTRIBUTING.md) is ${stem}_<Name>; '$name' does not follow it" >&2 ;;
esac

ident=$(echo "$name" | tr -d '_')
upper=$(echo "$ident" | tr '[:lower:]' '[:upper:]')
lower=$(echo "$ident" | tr '[:upper:]' '[:lower:]')
slug=$(echo "$name" | tr '[:upper:]_' '[:lower:]-')
s_upper=$(echo "$stem" | tr '[:lower:]' '[:upper:]')
s_lower=$(echo "$stem" | tr '[:upper:]' '[:lower:]')

# ------------------------------------------------------------------ build in a temporary folder
parent=$(dirname "$dest")
mkdir -p "$parent"
work=$(mktemp -d "$parent/.new-addon-repo.XXXXXX")
case $work in */.new-addon-repo.*) ;; *) fail "could not create a temporary folder in $parent" ;; esac
list=$(mktemp "${TMPDIR:-/tmp}/new-addon-repo.XXXXXX")
tmp=$(mktemp "${TMPDIR:-/tmp}/new-addon-repo.XXXXXX")
cleanup() {
	rm -f "$list" "$tmp"
	if [ -n "$work" ] && [ -d "$work" ]; then rm -rf "$work"; fi
}
trap cleanup EXIT

# Copy including dot-files (.github, .pkgmeta, ...). "cp -R src/. dest" works on BSD and GNU cp.
cp -R "$src/." "$work/"

replace_names() {
	sed -e "s|${stem}_Example|$name|g" -e "s|${stem}Example|$ident|g" -e "s|${s_upper}EXAMPLE|$upper|g" \
		-e "s|${s_lower}example|$lower|g" -e "s|${s_lower}-example|$slug|g" -e "s|${stem} Example|$title|g"
}

# Rename files and folders whose names carry a placeholder (deepest first).
(cd "$work" && find . -mindepth 1 | awk '{ print length($0) "\t" $0 }' | sort -rn | cut -f2-) > "$list"
while IFS= read -r path; do
	base=${path##*/}
	newbase=$(printf '%s\n' "$base" | replace_names)
	if [ "$newbase" != "$base" ]; then
		mv "$work/$path" "$work/${path%/*}/$newbase"
	fi
done < "$list"

# Replace placeholders in every text file. "cat >" keeps each file's permissions.
find "$work" -type f ! -name '*.png' ! -name '*.tga' ! -name '*.blp' ! -name '*.ttf' ! -name '*.ogg' ! -name '*.zip' > "$list"
while IFS= read -r file; do
	replace_names < "$file" | sed -e "s|YOUR-ORG|$org|g" > "$tmp"
	cat "$tmp" > "$file"
done < "$list"

# ------------------------------------------------------------------ verify the result
left=$(grep -rn -e "${stem}_Example" -e "${stem}Example" -e "${s_upper}EXAMPLE" -e "${s_lower}example" \
	-e "${s_lower}-example" -e "${stem} Example" -e 'YOUR-ORG' "$work" | sed "s|^$work/||" || true)
[ -z "$left" ] || { printf '%s\n' "$left" >&2; fail "placeholders are left in the lines above; nothing was created"; }
toc="$work/$name.toc"
[ -f "$toc" ] || fail "$name.toc was not created; nothing was created"
missing=""
for lib in $(tr -d '\r' < "$toc" | sed -n 's/^Libs\\\([^\\]*\)\\.*$/\1/p' | sort -u); do
	grep -q "^  Libs/$lib:" "$work/.pkgmeta" || missing="$missing $lib"
done
[ -z "$missing" ] || fail "the TOC loads Libs\\$missing but .pkgmeta has no such external; nothing was created"

mv "$work" "$dest"
work=""

echo "Created $dest for $name ($title)."
echo "Fill in by hand:"
grep -rn -e 'YOUR-INVITE' -e 'X-Curse-Project-ID: 0' -e 'X-Wago-ID: 0' -e '^## Notes: One sentence' \
	-e '^One sentence that says' -e "curseforge.com/wow/addons/$slug" "$dest" | sed "s|^$dest/|  |" || true
[ -f "$conf" ] || echo "  (team placeholders such as Tx Studio and LibTx-1.0 are still in place: run set-team.sh on the templates first)"
lib=$(sed -n 's/^  \(Libs\/Lib[A-Za-z]*-1\.0\):.*/\1/p' "$dest/.pkgmeta" | head -n 1)
lib_url=$(sed -n 's/^    url: \(https:\/\/github\.com\/[^ ]*\/Lib[A-Za-z]*-1\.0\)$/\1/p' "$dest/.pkgmeta" | head -n 1)
lib_tag=$(sed -n '/^  Libs\/Lib[A-Za-z]*-1\.0:/,/^$/s/^    tag: \(.*\)$/\1/p' "$dest/.pkgmeta" | head -n 1)
cat <<EOF
Next (RELEASING.md, "First-time setup for a new addon"):
  cd "$dest" && git init -b main && git add -A && git commit -m "Start $name"
  create the empty public repository $org/$name on GitHub (no README, .gitignore or license), then
  git remote add origin https://github.com/$org/$name.git && git push -u origin main
  git clone --depth 1 --branch ${lib_tag:-v1.0.0} ${lib_url:-https://github.com/$org/Lib${stem}-1.0} ${lib:-Libs/Lib${stem}-1.0}
EOF
