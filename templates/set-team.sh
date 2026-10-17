#!/usr/bin/env bash
# set-team.sh - make the templates yours: replace the team placeholders in every file of templates/
# and rename the files whose names carry them, consistently, in one run.
#
#   bash set-team.sh TOKEN "Team Name" GITHUB_ORG DISCORD_INVITE [DEV_TEAM RELEASE_TEAM]
#   bash set-team.sh Ks "Kestrel Studio" kestrel-studio abcd1234
#
#   TOKEN           team token: one capital letter and 1 to 3 small letters (Ks, Tx, Abc), unused on
#                   CurseForge and Wago. It prefixes every addon (Ks_Bags), saved variable (KsBagsDB),
#                   slash command (/ksbags) and the shared library (LibKs-1.0).
#   "Team Name"     shown as the author of every addon (Kestrel Studio)
#   GITHUB_ORG      the GitHub organization (kestrel-studio)
#   DISCORD_INVITE  the code at the end of the Discord invite link (discord.gg/<code>)
#   DEV_TEAM, RELEASE_TEAM  GitHub team slugs for CODEOWNERS and the rulesets
#                   (default addon-devs and release-managers)
#
# What it changes (current values come from team.conf, or the placeholders Tx, "Tx Studio",
# YOUR-ORG, YOUR-INVITE, addon-devs and release-managers before the first run):
#   * text in every file of templates/ except README.md, this script, new-addon-repo.sh and
#     tests/: the team name, organization, invite, team slugs, the library name (LibTx-1.0 ->
#     LibKs-1.0, also LibTx: in code), and every token-derived name (Tx_Example -> Ks_Example,
#     TxExampleDB -> KsExampleDB, TXEXAMPLE -> KSEXAMPLE, /txexample -> /ksexample, tx-core ->
#     ks-core, Tx_Bags -> Ks_Bags in examples)
#   * file names: shared-lib/LibTx-1.0.lua and .toc -> LibKs-1.0.*, addon-repo/Tx_Example.toc ->
#     Ks_Example.toc (with "git mv" for files git tracks)
#   * writes team.conf with the new values; new-addon-repo.sh reads it
# Then it checks that no old value is left. Run it again to change a value; commit the result.
# Do not search and replace by hand: a text-only replacement leaves LibTx-1.0.lua behind while every
# TOC lists LibKs-1.0.lua, and the packaged addon fails with "Cannot find a library instance".
#
# Needs bash, perl and find. Tested with macOS's bash 3.2 and on Linux; Git Bash on Windows (which
# includes perl) is untested.

set -eu

usage() {
	sed -n '2,32p' "$0" | sed 's/^# \{0,1\}//' >&2
	exit 2
}
[ "$#" -eq 4 ] || [ "$#" -eq 6 ] || usage

here=$(cd "$(dirname "$0")" && pwd)
case $here in */templates) ;; *) echo "set-team.sh must stay in the toolkit's templates folder (found in $here)" >&2; exit 2 ;; esac
command -v perl >/dev/null 2>&1 || { echo "set-team.sh needs perl (macOS and Git for Windows include it)" >&2; exit 2; }

NT=$1 NNAME=$2 NORG=$3 NINV=$4 NDEV=${5:-addon-devs} NREL=${6:-release-managers}

# ---------------------------------------------------------------- validate everything first
fail() { echo "error: $*" >&2; exit 2; }
echo "$NT" | grep -Eq '^[A-Z][a-z]{1,3}$' ||
	fail "TOKEN must be one capital letter and 1 to 3 small letters, such as Ks or Abc (got '$NT')"
case $NNAME in
	'' | ' '* | *' ' | *'|'* | *\\* | *'&'* | *'
'*) fail "Team Name must not be empty, start or end with a space, or contain |, \\ or & (got '$NNAME')" ;;
esac
echo "$NORG" | grep -Eq '^[A-Za-z0-9]([A-Za-z0-9]|-[A-Za-z0-9]){0,38}$' ||
	fail "GITHUB_ORG must be a GitHub organization name: letters, digits and single hyphens (got '$NORG')"
echo "$NINV" | grep -Eq '^[A-Za-z0-9-]{2,64}$' || fail "DISCORD_INVITE must be the invite code only, such as abcd1234 (got '$NINV')"
for t in "$NDEV" "$NREL"; do
	echo "$t" | grep -Eq '^[a-z0-9][a-z0-9_-]*$' || fail "team slugs must be lower-case letters, digits, - and _ (got '$t')"
done
[ "$NDEV" != "$NREL" ] || fail "DEV_TEAM and RELEASE_TEAM must differ"

conf="$here/team.conf"
CT=Tx CNAME="Tx Studio" CORG=YOUR-ORG CINV=YOUR-INVITE CDEV=addon-devs CREL=release-managers
if [ -f "$conf" ]; then
	while IFS= read -r line; do
		case $line in '#'* | '') continue ;; esac
		key=${line%%=*} value=${line#*=}
		case $key in
			TEAM_TOKEN) CT=$value ;; TEAM_NAME) CNAME=$value ;; GITHUB_ORG) CORG=$value ;;
			DISCORD_INVITE) CINV=$value ;; DEV_TEAM) CDEV=$value ;; RELEASE_TEAM) CREL=$value ;;
		esac
	done < "$conf"
fi

# The templates must still be in the state team.conf describes (no half-done manual replacement).
[ -f "$here/addon-repo/${CT}_Example.toc" ] ||
	fail "addon-repo/${CT}_Example.toc is missing: the templates do not match team.conf (token $CT). Restore them (git checkout -- templates) and run this script instead of replacing by hand."
if [ ! -f "$here/shared-lib/Lib${CT}-1.0.lua" ] || [ ! -f "$here/shared-lib/Lib${CT}-1.0.toc" ]; then
	fail "shared-lib/Lib${CT}-1.0.lua or .toc is missing: the templates do not match team.conf (token $CT). Restore them (git checkout -- templates)."
fi
grep -q "^package-as: ${CT}_Example" "$here/addon-repo/.pkgmeta" ||
	fail "addon-repo/.pkgmeta does not say 'package-as: ${CT}_Example': the templates were edited by hand. Restore them (git checkout -- templates)."

upper() { echo "$1" | tr '[:lower:]' '[:upper:]'; }
lower() { echo "$1" | tr '[:upper:]' '[:lower:]'; }
export CT NT CNAME NNAME CORG NORG CINV NINV CDEV NDEV CREL NREL
CU=$(upper "$CT") NU=$(upper "$NT") CL=$(lower "$CT") NL=$(lower "$NT")
export CU NU CL NL

# One pass of every rule over the text, so replaced text is never matched again.
perl_rules() {
	cat <<'PERL'
use strict;
use warnings;
my %e = %ENV;
my @rules;
sub rule { my ($re, $to, $from, $new) = @_; push @rules, [$re, $to] if $from ne $new; }
rule('(?<![A-Za-z0-9_-])' . quotemeta($e{CDEV}) . '(?![A-Za-z0-9_-])', $e{NDEV}, $e{CDEV}, $e{NDEV});
rule('(?<![A-Za-z0-9_-])' . quotemeta($e{CREL}) . '(?![A-Za-z0-9_-])', $e{NREL}, $e{CREL}, $e{NREL});
rule(quotemeta($e{CNAME}), $e{NNAME}, $e{CNAME}, $e{NNAME});
rule('(?<![A-Za-z0-9-])' . quotemeta($e{CORG}) . '(?![A-Za-z0-9-])', $e{NORG}, $e{CORG}, $e{NORG});
rule('(?<![A-Za-z0-9-])' . quotemeta($e{CINV}) . '(?![A-Za-z0-9-])', $e{NINV}, $e{CINV}, $e{NINV});
# LibTx-1.0, LibTx:GetFlavor(), local LibTx = ...
rule('(?<![A-Za-z0-9])Lib' . quotemeta($e{CT}) . '(?![a-z0-9])', 'Lib' . $e{NT}, $e{CT}, $e{NT});
# Tx_Example, TxExampleDB, Tx<Name>DB, Tx Example, `Tx`
rule('(?<![A-Za-z0-9])' . quotemeta($e{CT}) . '(?![a-z0-9])', $e{NT}, $e{CT}, $e{NT});
# TXEXAMPLE, SLASH_TXEXAMPLE1, SlashCmdList.TXEXAMPLE, TX<NAME> (never a .TXT extension)
my $not_upper_txt = $e{CU} eq 'TX' ? '(?!T(?![A-Za-z0-9]))' : '';
rule('(?<![A-Za-z0-9])' . quotemeta($e{CU}) . $not_upper_txt . '(?=[A-Z<])', $e{NU}, $e{CU}, $e{NU});
# /txexample, txexample, tx-core, tx<name> (never the .txt extension)
my $not_txt = $e{CL} eq 'tx' ? '(?!t(?![a-z]))' : '';
rule('(?<![A-Za-z0-9.])' . quotemeta($e{CL}) . $not_txt . '(?=[a-z<-])', $e{NL}, $e{CL}, $e{NL});
exit 0 unless @rules;
my $alt = join '|', map { "(?<r$_>$rules[$_][0])" } 0 .. $#rules;
my $re = qr/$alt/;
my $mode = shift @ARGV;
if ($mode eq 'names') {
	while (my $line = <STDIN>) {
		$line =~ s/$re/my $t; for my $i (0 .. $#rules) { if (defined $+{"r$i"}) { $t = $rules[$i][1]; last } } $t/ge;
		print $line;
	}
} elsif ($mode eq 'files') {
	local $^I = '';
	while (my $line = <>) {
		$line =~ s/$re/my $t; for my $i (0 .. $#rules) { if (defined $+{"r$i"}) { $t = $rules[$i][1]; last } } $t/ge;
		print $line;
	}
} elsif ($mode eq 'check') {
	# the new values themselves may contain an old one (token Txa after Tx): ignore them
	my @new = sort { length($b) <=> length($a) } grep { length } ($e{NNAME}, $e{NORG}, $e{NINV}, $e{NDEV}, $e{NREL},
		'Lib' . $e{NT}, $e{NT}, $e{NU}, $e{NL});
	my $bad = 0;
	while (my $line = <>) {
		my $l = $line;
		$l =~ s/\Q$_\E//g for @new;
		if ($l =~ $re) { print "$ARGV:$.: $line"; $bad = 1 }
	} continue { close ARGV if eof }
	exit $bad;
}
PERL
}

if [ "$CT/$CNAME/$CORG/$CINV/$CDEV/$CREL" = "$NT/$NNAME/$NORG/$NINV/$NDEV/$NREL" ]; then
	echo "Nothing to change: team.conf already has these values."
	exit 0
fi

# Files to rewrite: every text file in templates/ except the tools, the index README and tests/.
list=$(mktemp "${TMPDIR:-/tmp}/set-team.XXXXXX")
trap 'rm -f "$list"' EXIT
(cd "$here" && find . -type f ! -path './.git/*' ! -path './tests/*' ! -name '*.png' ! -name '*.tga' ! -name '*.blp' \
	! -name '*.ttf' ! -name '*.ogg' ! -name '*.zip' ! -path './README.md' ! -path './set-team.sh' \
	! -path './new-addon-repo.sh' ! -path './team.conf') > "$list"
(cd "$here" && tr '\n' '\0' < "$list" | xargs -0 perl -e "$(perl_rules)" files)

# Rename files and folders whose names carry an old value (deepest first).
renamed=0
for path in $(cd "$here" && find . ! -path './.git/*' ! -path './tests/*' ! -path . | awk '{ print length($0) "\t" $0 }' | sort -rn | cut -f2- | tr ' ' '\001'); do
	path=$(printf '%s' "$path" | tr '\001' ' ')
	base=${path##*/}
	newbase=$(printf '%s\n' "$base" | perl -e "$(perl_rules)" names)
	[ "$newbase" != "$base" ] || continue
	dir=${path%/*}
	if git -C "$here" ls-files --error-unmatch "$path" > /dev/null 2>&1; then
		git -C "$here" mv "$path" "$dir/$newbase"
	else
		mv "$here/$path" "$here/$dir/$newbase"
	fi
	new=${dir#.}
	new=${new#/}
	echo "renamed ${path#./} -> ${new:+$new/}$newbase"
	renamed=$((renamed + 1))
done

{
	echo "# Written by set-team.sh. Change these values by running set-team.sh again, not by hand:"
	echo "# the templates' file names and texts must match them."
	echo "TEAM_TOKEN=$NT"
	echo "TEAM_NAME=$NNAME"
	echo "GITHUB_ORG=$NORG"
	echo "DISCORD_INVITE=$NINV"
	echo "DEV_TEAM=$NDEV"
	echo "RELEASE_TEAM=$NREL"
} > "$conf"

# Nothing of the old values may be left (in file contents or names).
(cd "$here" && find . -type f ! -path './.git/*' ! -path './tests/*' ! -name '*.png' ! -name '*.tga' ! -name '*.blp' \
	! -name '*.ttf' ! -name '*.ogg' ! -name '*.zip' ! -path './README.md' ! -path './set-team.sh' \
	! -path './new-addon-repo.sh' ! -path './team.conf') > "$list"
if ! (cd "$here" && tr '\n' '\0' < "$list" | xargs -0 perl -e "$(perl_rules)" check); then
	echo "error: the lines above still carry an old value" >&2
	exit 1
fi
if (cd "$here" && find . ! -path './.git/*' ! -path './tests/*' | perl -e "$(perl_rules)" check); then :; else
	echo "error: the file names above still carry an old value" >&2
	exit 1
fi

echo "Templates now use: token $NT (Lib${NT}-1.0, ${NT}_Example), \"$NNAME\", github.com/$NORG,"
echo "discord.gg/$NINV, teams @$NORG/$NDEV and @$NORG/$NREL. $renamed file(s) renamed; values saved in templates/team.conf."
echo "Next: review and commit the change (git add -A templates && git commit -m \"Templates: $NNAME\"),"
echo "then create the .github and Lib${NT}-1.0 repositories (templates/README.md, \"Make the templates yours\")."
