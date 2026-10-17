# Releasing Tx Studio addons

A release is a git tag. Pushing `v1.2.0` starts `.github/workflows/release.yml`, which lints,
builds the zip once without uploading and checks it (every file its TOC lists is in it, and it
loads in the Lua 5.1 smoke test), then runs the BigWigs packager again and uploads the zip to
CurseForge, Wago and GitHub Releases. Only
release managers can push `v*` tags (tag ruleset, see "First-time setup").

One exception: a new addon's **first** CurseForge file is uploaded by hand on the CurseForge
website. CI uploads to CurseForge only when the repository variable `CURSEFORGE_UPLOADS` is `on`,
and a release manager sets it only after CurseForge has approved the project (see "First
publication on CurseForge"). Until then the packager runs with `-p 0`: Wago and the GitHub Release
work as usual, CurseForge is skipped. `-p 0` unsets the CurseForge project ID for the whole run,
so it also turns off CurseForge `@localization(...)@` imports (the packager prints "Skipping
localization!" and drops those lines). The template keeps its translations in `Locales/*.lua`
files and is not affected; an addon that imports translations from CurseForge ships without them
while the switch is off.

## Versions and channels

Semantic versions: `vMAJOR.MINOR.PATCH`.

- **PATCH** for fixes, **MINOR** for features, **MAJOR** for a new game flavor or a saved-variable
  change that cannot be migrated.
- The packager writes the tag into the TOC (`## Version: @project-version@` becomes `v1.2.0`).

The packager chooses the CurseForge and Wago file type from the tag text (tested with the
packager at 0f24d21):

| You push | Packager uploads as | Who gets it |
|---|---|---|
| `v1.2.0` | Release (Wago: stable) | everyone; CurseForge's app syncs Release files by default |
| `v1.2.0-beta.1` | Beta | players who opted into beta files |
| `v1.2.0-alpha.1` | Alpha | players who opted into alpha files |
| a commit without a tag | Alpha | only if CI runs on branch pushes (off in our template) |
| `v1.2.0-rc.1` | **Release**: "rc" is not a keyword | refused by our release workflow |

The release workflow refuses tags that do not match `vX.Y.Z`, `vX.Y.Z-beta.N` or
`vX.Y.Z-alpha.N`. Never move or delete a pushed tag; release a new version instead.
One exception: a tag the Release workflow refused (its "Check the tag name" step failed) published
nothing. A release manager deletes it (the tag ruleset lets only release managers delete tags),
locally and on GitHub, and then pushes a valid one:

```sh
git tag -d v1.2.0-rc.1
git push origin :refs/tags/v1.2.0-rc.1
```

A project's first CurseForge file is never an alpha: a project with only alpha files does not
appear in the CurseForge app.

## Release checklist

Copy this into the release's tracking issue.

**Before tagging**
- [ ] `main` is green (Lint) and contains everything for this release.
- [ ] `CHANGELOG.md`: rename "Unreleased" to `vX.Y.Z (YYYY-MM-DD)`, written for players. The
      packager uploads the **whole** file as the release notes, so keep only player text in it
      (no notes for developers), and add the next empty "Unreleased" heading only **after** the tag
      is pushed: an empty heading above the version would be published too.
- [ ] TOC `## Interface:` holds the number of every client we ship for, as the live client
      reports it (`/dump (select(4, GetBuildInfo()))`). Forever: 16001 during the beta.
- [ ] `.pkgmeta` pins (`tag:`) are the versions you tested, LibTx-1.0 included.
- [ ] The PR's or `main`'s **test-package** artifact was installed and smoke-tested on the Forever
      client: loads with only this addon + BugSack, no errors after `/reload`, in or out of combat,
      slash command and settings work. (CI has already checked that the zip holds every file its
      TOC lists and that it loads in the Lua 5.1 smoke test; that does not replace the client.)

**Tag** (release manager)
```sh
git switch main && git pull
git tag -a v1.2.0 -m v1.2.0
git push origin v1.2.0
```

**Watch the Release run** (Actions > Release). In the packager log, check:
- [ ] `Current version: v1.2.0` and `Build type: non-retail version-forever non-alpha non-debug`
      (Forever-only) or `Build type: multi-version non-alpha non-debug` (several flavors). An alpha
      tag (or an untagged commit) prints `alpha` in place of `non-alpha`; a beta tag does not.
- [ ] `Game version: 1.60.1` (plus `12.1.5`, `1.15.9` if you ship those).
- [ ] `CurseForge ID: <id> [token set]`, then `Uploading ... (1.60.1 release) ... Success!`.
      Until `CURSEFORGE_UPLOADS` is `on` there is no `CurseForge ID` line, and the step "Check
      upload IDs against tokens" prints `CurseForge uploads: off` and a notice that CurseForge
      uploads are off. That is expected before approval.
- [ ] No `WARNING: No CurseForge game version match` and no `WARNING: No Wago game version match`.
      `... for "1.60.2", using "1.60.1"` means that site does not know the new game version yet and
      the file was labeled with another one (see PATCH_DAY.md). `... for "1.60.1", ignoring` means
      CurseForge knows no Forever version at all: see "If the Release run fails".
- [ ] Wago: `Success!` (if the TOC has an `X-Wago-ID`). WoWInterface is skipped for Forever.

**After the upload**
- [ ] CurseForge > Files: the file is listed with game version 1.60.1 under WoW: Forever and moves
      from Processing or Under Review to Approved ("a few minutes to three workdays",
      CurseForge's own estimate). A file waiting for review is normal; do not upload it again.
- [ ] Wago project page and the GitHub Release show the new version.
- [ ] Post the changelog in Discord; close the issues fixed by this release.

**If the Release run fails**
- `Uploading to CurseForge failed, aborting uploads.` The packager tried CurseForge 10 times and
  then **skipped Wago and the GitHub Release** as well ("Packager version" below). The `Error!`
  lines above it show CurseForge's answer:
  - `No project for "<id>" found`: HTTP 404. Check the ID.
  - `(401)` or `(403)`: CurseForge did not accept the token (wrong, revoked, or from an account
    that may not upload to this project).
  - `(422)` plus a message: something in the upload, such as a game version.

  - `WARNING: No CurseForge game version match for "1.60.1", ignoring`, then `Error fetching game
    version info` and `Skipping upload to CurseForge.` (10 times): CurseForge's version list has no
    WoW: Forever version. A **Forever-only** addon then has no game version left for CurseForge,
    so the run fails without uploading anything (no Wago file, no GitHub Release). A multi-flavor
    addon's run stays green, but its CurseForge file silently lacks Forever. Do what "CurseForge is
    down" below says, and keep `CURSEFORGE_UPLOADS` off until the CurseForge upload form lists
    WoW Forever 1.60.1 (this can happen on launch day, 2026-11-04, if CurseForge adds a new
    version late).

  Look at CurseForge > Files before you do anything else. If the file arrived anyway, do **not**
  re-run: fix the cause and tag the next PATCH. If nothing arrived, fix the cause and re-run the
  job.
- **CurseForge is down (or has no Forever version) and the fix cannot wait:** set
  `CURSEFORGE_UPLOADS` to `off`, tag the next PATCH (it reaches Wago and GitHub), and upload that
  zip to CurseForge by hand when it is back (Files > Add File, same fields as "First
  publication"). Then set the variable to `on` again.
- **A failure after CurseForge printed `Success!`** (Wago, GitHub): do not re-run the job. A
  re-run uploads a second copy to CurseForge and Wago, and CurseForge's rules forbid re-uploads
  without changes. Fix the cause and tag the next PATCH, or attach the missing zip by hand.

## Hotfix

1. Fix on a branch, merge to `main`, tag the next PATCH (`v1.2.1`).
2. If `main` already holds unfinished work, tag from a branch made at the release tag instead.
   Create the branch:
   ```sh
   git switch -c hotfix/v1.2.1 v1.2.0
   ```
   Commit the fix there (if it is already on `main`, `git cherry-pick <commit>`), then tag and
   push the branch and the tag:
   ```sh
   git tag -a v1.2.1 -m v1.2.1
   git push origin hotfix/v1.2.1 v1.2.1
   ```
   The workflow runs for the tag wherever it points. Merge the branch back into `main`.

## Rollback

Roll forward; do not delete. Tag the last good code again with a **new, higher** version (for
example `v1.2.2` on the commit of `v1.2.0`) so every addon manager sees an update. On
CurseForge, **archive** the bad file instead of deleting it (archived files can be restored).
Tell players in the pinned issue and on Discord.

## Packager version

Every workflow (`release.yml`, the test package in `lint.yml`, and the HelloAzeroth sample's
`release.yml`) pins the BigWigs packager to master commit
`0f24d2169de3ceb3b79a981311b2ebab4c6160c7` (2026-10-10). Use the same commit for local builds
(`git -C <packager clone> checkout 0f24d21`). Why not the `v2` tag: `v2` is still v2.6.1
(2026-09-17), 17 commits older. It lacks:
- Forever interface numbers in `_Mainline.toc` (v2.6.1 stops the build) and the check that keeps
  them out of `_Classic.toc`;
- the retry when CurseForge's game-version list fails to load (v2.6.1 skips CurseForge after one
  try);
- the `GH_API_TOKEN` name (our workflows set `GITHUB_OAUTH` too, so both work), a clear error for
  a wrong `path:` in a library external (both versions stop the build; v2.6.1 only prints a
  failed `cd`), `zip` externals and several `.pkgmeta` fixes.

**The trade-off.** On `0f24d21` a CurseForge upload that fails 10 times stops the run: no Wago
upload and no GitHub Release. v2.6.1 would carry on with them (both reproduced against a mock
server). We accept it because the riskiest time, before the project is approved, is covered by
`CURSEFORGE_UPLOADS`, and the "CurseForge is down" recipe above covers the rest. Dependabot leaves
the packager alone: check master on patch day (PATCH_DAY.md, "Patch day"), and move to a tagged
release once one contains these fixes, after re-checking how it handles a failed upload.

## First-time setup for a new addon

Do this once per addon, well before its first release. CurseForge reviews a new project only
after it has a file, and a review can take up to three workdays, so keep to the dates in
"Launch window" below.

**GitHub**
1. Create the repository in the organization and push the folder `new-addon-repo.sh` made. Make
   it **public**: the code ships as plain Lua anyway, and public repositories get rulesets,
   environments and required reviewers on every plan. With the GitHub CLI (`gh auth login` once),
   from the new folder after its first commit:
   ```sh
   gh repo create your-org/Tx_Bags --public --source . --remote origin --push
   ```
   Or on github.com: New repository, owner your organization, name `Tx_Bags`, **public**, no
   README, `.gitignore` or license (the folder has them), then:
   ```sh
   git remote add origin https://github.com/your-org/Tx_Bags.git
   git push -u origin main
   ```
2. Teams (visible, not secret; Organization > Teams > New team): `addon-devs` (write) and
   `release-managers` (maintain), created once for the organization and given access to each new
   repository (Settings > Collaborators and teams). At least two organization owners.
3. Ruleset for `main`: require a pull request with 1 approval, review from code owners,
   approval of the most recent push by someone else, the status check
   "luacheck and TOC checks", and block force pushes.
4. Ruleset for tags `v*`: restrict creations, updates and deletions; bypass list:
   `release-managers` only.
5. Settings > Actions > General: workflow permissions "Read repository contents"; `release.yml`
   asks for `contents: write` itself. If the GitHub Release step still fails with "Resource not
   accessible by integration", check this setting and the organization's Actions policy.
6. Labels: `needs-triage` (used by the bug form), `confirmed`, `needs-info`, `forever-launch`.
   GitHub creates `bug` and `enhancement` in every new repository, and the patchwatch workflow
   creates `patchwatch` itself. The four others, from the addon folder:
   ```sh
   gh label create needs-triage
   gh label create confirmed
   gh label create needs-info
   gh label create forever-launch
   ```

**CurseForge** (the owner account; see "Who owns what")
1. Authors Console (authors.curseforge.com) > Projects > Create a Project > World of Warcraft.
   Name, one-sentence summary, description and a 400 × 400 PNG avatar (not a solid color): use
   [CURSEFORGE_DESCRIPTION.md](CURSEFORGE_DESCRIPTION.md). License MIT; source and issues links
   to GitHub. Leave third-party distribution allowed: when it is off, WowUp and instawow cannot
   download the addon.
2. Put the numeric **Project ID** (the "About Project" box, or the console URL) into every TOC
   (`## X-Curse-Project-ID: 123456`) and merge. **Do not create the repository variable
   `CURSEFORGE_UPLOADS` yet**: while it is missing (or anything but `on`), CI uploads nothing to
   CurseForge.
3. Members tab > add each team member by exact CurseForge username, with a role and reward share;
   they must accept the invitation.
4. Publish the first file: "First publication on CurseForge" below.

**Wago Addons**: create the project, copy its ID into `## X-Wago-ID:`. We do not know whether
Wago reviews new projects before it accepts uploads. If the Release log shows `Error! (403)` for
Wago, check the Wago dashboard and set the ID back to 0 until that is sorted out. A Wago failure
does not stop the GitHub Release.

**Accounts**: the owner needs a CurseForge account to reach the Authors Console
(authors.curseforge.com; CurseForge belongs to Overwolf) and should enroll in the Rewards program
there before the first project ("Who owns what" below), and an account on addons.wago.io before
Wago's developer dashboard and API keys appear. The sign-up steps of both sites were not checked
from here: the sites were blocked.

**Tokens and secrets**
- CurseForge: the owner creates an API token (authors.curseforge.com > API tokens).
  Wago: the owner creates an API key (addons.wago.io > account > API keys).
- Store them as `CF_API_TOKEN` and `WAGO_API_TOKEN`, either as **organization secrets** shared with
  selected repositories (Organization settings > Secrets and variables > Actions > New
  organization secret, Repository access: Selected repositories), or as repository secrets in
  each repository (Settings > Secrets and variables > Actions > Secrets > New repository secret;
  required for private repositories on GitHub Free). With the GitHub CLI, which asks for the value
  without showing it:
  ```sh
  gh secret set CF_API_TOKEN --repo your-org/Tx_Bags
  gh secret set WAGO_API_TOKEN --repo your-org/Tx_Bags
  ```
  Never put them in a file in the repository. `CF_API_TOKEN` can
  exist before the project is approved: while `CURSEFORGE_UPLOADS` is not `on`, the packager runs
  with `-p 0` and never contacts CurseForge.
- `CURSEFORGE_UPLOADS` is a repository **variable**, not a secret (Settings > Secrets and
  variables > Actions > Variables). Only release managers should change it.
- Optional hardening (public repositories, or a paid plan): an environment `release` limited to
  tags `v*`, holding the secrets; uncomment `environment: release` in `release.yml`.
- Rotate both tokens when someone with write access leaves: anyone with write access to a
  repository can read its secrets through a workflow.
- Tags pushed by a workflow using `GITHUB_TOKEN` do not start other workflows. Release tags come
  from a release manager's machine (or a GitHub App token).

**Who owns what**: one accountable owner (or a shared team account) owns every CurseForge and
Wago project and enrolls in CurseForge's Rewards program first: if the owner is not enrolled, no
member earns points. Agree reward shares in writing. CurseForge documents no self-service
ownership transfer, so choose the owner carefully.

### First publication on CurseForge (once per project)

The first file goes through the CurseForge website. CI takes over after the project is approved.

1. **Build it.** Pass the release checklist on the Forever client (the beta closes on Oct 21 or
   22), then tag, for example `v1.0.0`. With `CURSEFORGE_UPLOADS` not set, the Release run builds
   the zip and publishes the GitHub Release (and the Wago version); its log says
   `CurseForge uploads: off` and shows no `CurseForge ID` line.
2. **Check the token, without uploading.** On a Mac, in WSL or in Git Bash with Scoop's `jq`. The
   first line waits for you to paste the token and press Enter; the token is neither shown nor
   saved:
   ```sh
   read -rs CF_API_TOKEN
   curl -sS -H "X-Api-Token: $CF_API_TOKEN" https://wow.curseforge.com/api/game/wow/versions | jq -c '.[] | select(.gameVersionTypeID == 88568) | {id, name}'
   ```
   Expect a line for WoW Forever 1.60.1, such as `{"id":17053,"name":"1.60.1"}`. A jq error means
   CurseForge sent no version list: run the `curl` line alone to see its `errorMessage` (usually
   a wrong token).
3. **Upload it by hand.** Download the zip from the GitHub Release: `<Addon>-v1.0.0-forever.zip`
   for a Forever-only addon (`Tx_Bags-v1.0.0-forever.zip`), `<Addon>-v1.0.0.zip` for a
   multi-flavor one. In the Authors
   Console, open the project > Files > Add File:

   | Field | Value |
   |---|---|
   | File | the zip from the GitHub Release, unchanged |
   | Display name | the label CI gives later files: the zip name without the addon name, so `v1.0.0-forever` for a Forever-only addon (`Tx_Bags-v1.0.0-forever.zip`) and `v1.0.0` for a multi-flavor one |
   | Release type | **Release** (rule below) |
   | Game versions | exactly the flavors in the TOC's `## Interface` line: **WoW Forever 1.60.1** (16001), plus Retail 12.1.5 or Classic Era 1.15.9 only if listed and tested |
   | Changelog | this version's section of `CHANGELOG.md`, as Markdown |
   | Related projects | what CI would send from `.pkgmeta`: `required-dependencies` (for example tx-core), `tools-used` (bugsack), and externals with a `curse-slug` as embedded libraries (ace3) |
   | Release options | release when approved (the default) |

   If WoW Forever 1.60.1 is not in the game-version list, stop and ask CurseForge support, and
   keep `CURSEFORGE_UPLOADS` off: with it `on`, CI would fail every release of a Forever-only addon
   (no Wago file, no GitHub Release; "If the Release run fails") and would drop Forever from a
   multi-flavor file with only a warning.
4. **Check that review has started.** The file shows Processing or Under Review. If the project
   still shows "Action Required", read the explanation next to it and do what it asks.
5. **Wait, one file at a time.** Do not upload another file while this one is under review. If
   moderators ask for changes, fix exactly what the message says and resubmit (or ask through a
   support ticket); never delete and re-create the project. Testers can still get betas: tag
   them as usual, and they go to GitHub and Wago only.
6. **Approved: turn CI on.** When the project is approved and the file shows Approved (or
   Released), a release manager creates the repository variable `CURSEFORGE_UPLOADS` with the
   value `on` (Settings > Secrets and variables > Actions > Variables > New repository variable).
   No commit is needed; check that the TOC carries the Project ID. From the next tag on, CI
   uploads to CurseForge. Make that tag a new version with real changes (`v1.0.1`), never a
   re-run of `v1.0.0`.
7. **Watch the first CI upload.** The log shows `CurseForge ID: 123456 [token set]` and
   `Uploading ... (1.60.1 release) ... Success!`. In the Files tab, the file has the same game
   versions as the first one.

**Rule for the first file: Release, never alpha.**
- **Release**: CurseForge's app installs Release files by default and beta or alpha files only
  for players who opted in. A project with only alpha files stays website-only. (WowUp and
  instawow fall back to a beta when there is no Release; the CurseForge app does not.)
- **Beta** (`v1.0.0-beta.1`) only if the addon is not release quality yet but review has to
  start. Then tag the first Release by Thu Oct 29, so it can be approved before launch.
- **Game versions**: one file for all the flavors in the TOC, the same set CI sends later, and
  only flavors you have tested.

**Why CI does not upload the first file**
- CurseForge documents the first upload through the Files tab. Whether its upload API accepts a
  file for a project that has never been reviewed is not documented. It probably does: an
  open-source modpack tool reports that its first CI upload went into review. We could not test
  it.
- If CurseForge refused it, the pinned packager would try 10 times and then skip Wago and the
  GitHub Release too ("Packager version").
- The form shows whether WoW Forever 1.60.1 exists before any CI upload depends on it, and only
  one file waits in review.
- With the switch, the Project ID sits in the TOC from the first file on, and approval needs no
  commit. Leaving `## X-Curse-Project-ID: 0` until approval works too (the packager then has no
  CurseForge project to upload to); then step 6 is "put the ID in the TOC and set the variable".

## GitHub plan limits (as documented on 2026-10-15)

| Feature | Public repository, any plan | Private repository in an organization |
|---|---|---|
| Rulesets (branch and tag) | yes | Team or Enterprise |
| Environments, environment secrets, deployment tag rules | yes | Team or Enterprise |
| Required reviewers, wait timers on environments | yes | Enterprise only |
| Organization secrets | yes | Team or Enterprise (not GitHub Free) |

("Pro" unlocks the same features for repositories owned by a personal account.) Teams used in
CODEOWNERS or in a ruleset's bypass list must be visible teams, not secret ones.

## Launch window for WoW: Forever

No date below comes from a Blizzard page we could open: every game date is from news coverage,
forum posts and search results (the research notes `gap_1.md`, `gap_2.md` and `verify_forever.md`
list them), so re-check them. Dates marked "plan" are ours, worked back from CurseForge's own
review estimate, "a few minutes to three workdays", counting Monday to Friday. Queues may be longer
before launch, when every Forever addon is new. In 2020 CurseForge paused new-project reviews for
several days after the Shadowlands launch, because of a site move. If CurseForge reviews the
project page and the file one after the other, a cycle can take twice as long. That is why the
target is Oct 20, not the last possible day.

| When (2026) | What | Source | Our plan |
|---|---|---|---|
| Tue Oct 13 | "WoW: Forever - Stress Test" appears in the Battle.net app as its own product, `wowf` (1.60.1.70245, a lower build number than the beta's 70425; unverified, re-check on BlizzTrack); it can be installed before the test | unverified: BlizzTrack, Wowhead and fan-site snippets | install it on both machines; `bash devsetup/link-addons.sh list` (Windows: `link-addons.ps1 list`) shows its folder, and from then on `-f forever` asks which Forever folder you mean (PATCH_DAY.md, "Launch day") |
| Fri Oct 16 – Mon Oct 19 | | plan | every CurseForge and Wago project created; Project IDs in the TOCs, `CURSEFORGE_UPLOADS` not set; secrets stored; token checked |
| Mon Oct 19 | stress test; Blizzard takes the Forever beta offline first | unverified: snippet of a Blizzard forum post; earlier snippets disagreed on the date | smoke-test each addon on the stress-test client if you can log in |
| **Tue Oct 20** (target) | | plan | first file of every project uploaded by hand ("First publication on CurseForge") |
| Wed Oct 21 or Thu Oct 22 | closed beta ends | unverified: snippets differ (a Blizzard forum post says "through October 21") | last chance to test on a Forever client, if the beta comes back after the stress test |
| **Fri Oct 23** | | plan | latest first upload that leaves room for one rejection: 3 workdays, a day to fix, 3 more workdays, approved by Tue Nov 3 |
| about Oct 22 – Nov 3 | probably no Forever client to play on | inference | feature freeze; finish docs; answer moderator messages the same day; watch patchwatch and the packager |
| Tue Oct 27 – Tue Nov 3 | early name reservation: pack owners can start the client and create characters, but not enter the world | unverified: guide and news snippets | repeat the folder check (PATCH_DAY.md); see whether WowUp and the CurseForge app detect the install |
| **Thu Oct 29** | | plan | latest first upload or resubmission for one 3-workday review to end by Tue Nov 3; latest tag for the first Release if the first file was a beta |
| **Tue Nov 3** | | plan | every project approved; `CURSEFORGE_UPLOADS` = `on` in every repository; open each project page while logged out, and find it in the CurseForge app |
| **Wed Nov 4, 3 p.m. PST** (23:00 UTC) | launch | unverified: Blizzard News article, seen as a search snippet only | PATCH_DAY.md "Launch day": check interface number and addon folder; tag a fix within hours if needed. Every Forever addon must have an approved **Release** file: the CurseForge app installs only Release files by default |
| Nov 4 – 18 | first two weeks | plan | daily triage; hotfix tags; pinned "Known issues" issue; no refactors |
| Wed Dec 9 | raids unlock | unverified: Blizzard roadmap as reported by several fan sites | content-dependent addons: data update |
