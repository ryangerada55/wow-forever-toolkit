# Getting help with Tx Studio addons

## Where to go

| You want to | Go to |
|---|---|
| Ask a question, get help with settings | our [Discord](https://discord.gg/YOUR-INVITE) |
| Report a bug or a Lua error | the addon's GitHub repository: **Issues > New issue > Bug report** |
| Suggest a feature | the addon's GitHub repository: **Issues > New issue > Feature request** |
| Comment on CurseForge or Wago | welcome, but we cannot track bugs there; please open an issue |

Each addon has its own repository (`github.com/YOUR-ORG/<AddonName>`), linked from its CurseForge
and Wago pages.

## Before you report a bug

1. **Update** the addon. Check that your addon manager is set to the right game (WoW: Forever,
   retail or Classic) and installed the version for that game.
2. **Do not tick "Load out of date AddOns"** to make an old version run after a game patch.
   Update the addon instead; an out-of-date addon may break in ways we cannot fix.
3. **Try with only our addon enabled** (plus BugGrabber and BugSack). If the bug disappears,
   enable your other addons again in halves until it comes back (the Bisector addon does this
   for you: `/bisect start +Tx_Bags`). Tell us which other addon is involved.

## What a good bug report contains

The bug form asks for each of these:

- **Game flavor and build.** Type `/dump GetBuildInfo()` in the chat box and copy what it prints.
  The game asks once before it allows such commands, and some clients block them; then copy the
  version and build shown on the login screen, or use our addon's `version` command below.
  For WoW: Forever, also say whether you chose the Classic or the Enhanced experience preset.
- **Addon version and OS.** Our addons print both: `/txbags version` (use your addon's command).
  It shows something like `v1.2.0 on forever, interface 16001, build 70425, macOS`.
- **The full error text.** Install **BugGrabber** and **BugSack**, reproduce the problem, click
  the BugSack icon and copy the first error completely (message, stack and locals). Without them,
  type `/console scriptErrors 1` to make the game show errors in a window.
- **Steps to reproduce,** starting from login, and what you expected instead.

## Where your addons and settings live

Default install folders. Your game may be installed elsewhere: in the Battle.net app, open the
game's settings (gear next to Play) and choose **Show in Explorer** (Windows) or **Show in Finder**
(macOS).

| Game | Windows | macOS |
|---|---|---|
| WoW: Forever (beta) | `C:\Program Files (x86)\World of Warcraft\_classic_beta_\` | `/Applications/World of Warcraft/_classic_beta_/` |
| WoW: Forever (from launch, Nov 4) | Blizzard has not named the folder yet; it is probably a new one next to `_retail_`. Battle.net app > **World of Warcraft: Forever** > gear next to Play > **Show in Explorer** opens it. We will add its name here on launch day. | the same, with **Show in Finder** |
| Retail | `...\World of Warcraft\_retail_\` | `.../World of Warcraft/_retail_/` |
| Classic Era | `...\World of Warcraft\_classic_era_\` | `.../World of Warcraft/_classic_era_/` |

Inside that folder:

- **Addons:** `Interface\AddOns\`. Each addon is one folder whose `.toc` file has the folder's
  name: `Interface\AddOns\Tx_Bags\Tx_Bags.toc`. A common mistake after unzipping by hand is a
  doubled folder (`AddOns\Tx_Bags\Tx_Bags\...`) or a folder renamed by the browser
  (`Tx_Bags-v1.2.0`); the game then ignores the addon.
- **Settings (SavedVariables):** `WTF\Account\<ACCOUNT NAME>\SavedVariables\Tx_Bags.lua`, and per
  character below `WTF\Account\<ACCOUNT NAME>\`. To reset an addon's settings, log out completely
  and delete or rename its file. The files contain character names; remove anything you do not
  want public before attaching one to an issue.

macOS notes: the game's folder is a normal folder in Finder (`/Applications/World of Warcraft`).
Unzipping with Finder (Archive Utility) is fine. Windows notes: "Extract All" in Explorer offers a
destination that ends in the zip's name; extract to `Interface\AddOns` directly.

## Your addon manager doesn't show WoW: Forever yet?

Around launch day, an addon manager may not recognize the new WoW: Forever install for a day or
two (WowUp needed one to two days for the last new Classic folder; for the CurseForge app we do not
know). Install by hand until it updates:

1. Download the newest file marked **WoW: Forever** from the addon's CurseForge **Files** tab or
   its GitHub **Releases** page.
2. In the Battle.net app pick **World of Warcraft: Forever**, click the gear next to Play and choose
   **Show in Explorer** (Windows) or **Show in Finder** (Mac). Open `Interface\AddOns` in that
   folder (`Interface/AddOns` on a Mac); create `Interface` and `AddOns` if they are missing.
3. Unzip so that you get `AddOns\Tx_Bags\Tx_Bags.toc`, not `AddOns\Tx_Bags\Tx_Bags\...` and not
   a folder named after the zip (`Tx_Bags-v1.2.0`).
4. Restart the game and check the **AddOns** button on the character screen.

Don't add the Forever folder to your addon manager as a "Retail" install: it would install the
retail files. Once the manager lists WoW: Forever on its own, let it take over (it may ask to
reinstall the addon once).

## For the team: triage

Labels: `needs-triage` (set by the bug form), `bug`, `confirmed`, `needs-info`, `enhancement`,
`forever-launch`, `patchwatch` (opened by the patchwatch workflow).

1. **Within 2 working days** (daily during launch week and patch weeks): read every `needs-triage`
   issue. Check flavor, build, version and OS. Remove `needs-triage`; add `confirmed` or
   `needs-info` (with a comment saying exactly what is missing).
2. **Reproduce** on the reporter's flavor and build. Note in the issue which client build you
   used. If it only happens with another addon, ask for the Bisector result.
3. Close `needs-info` issues with no answer after 14 days, with a friendly note that they can be
   reopened.
4. Duplicates: close with "Duplicate of #N". Known launch or patch problems go into the pinned
   "Known issues" issue (PATCH_DAY.md).
5. Once a week, read the CurseForge and Wago comments and answer with a link to the bug form.
6. Never ask for, and delete on sight, passwords, account names in full, authenticator codes or
   API tokens.

Canned replies:

- **Missing information:** "Thanks! To look into this we need the output of
  `/dump GetBuildInfo()`, `/txbags version` and the full BugSack text. The bug form explains how."
- **Out of date:** "Your game build is newer than the version you run. Please update the addon
  (and untick 'Load out of date AddOns'); tell us if it still happens."
- **Blizzard restriction:** "This information is a protected 'secret value' in combat on
  WoW: Forever and retail, so no addon can read or compare it. We keep the issue open in case
  Blizzard changes the rule."
- **Another addon's bug:** "The error comes from <AddonName>, not from Tx Bags. Please report it
  to its authors: <link>."
