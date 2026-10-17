## What and why

<!-- One or two sentences. Link the issue: "Fixes #123". -->

## How I tested it

<!-- Tick what you actually did. "In game" means the addon loaded from your checkout or from the
     test package attached to this PR's "Lint" run (Actions > Lint > Artifacts). -->

- [ ] WoW: Forever, build: <!-- /dump GetBuildInfo() -->
- [ ] Retail, build:
- [ ] Classic Era, build:
- [ ] `/reload` keeps the settings, and BugSack shows no new errors
- [ ] Tried in combat, if the change touches anything that runs in combat
- [ ] Tested on macOS / Windows (say which, if the change touches file names, paths or fonts)

## Checklist

- [ ] luacheck passes (the Lint workflow is green)
- [ ] No new global; or it starts with the addon's name and is listed in `.luacheckrc`
- [ ] New player-facing text goes through `L.KEY` with an English value in `Locales/enUS.lua`
- [ ] Changed the SavedVariables layout? `DB_VERSION` is bumped and a migration is added
- [ ] `CHANGELOG.md` has a line under "Unreleased" (written for players)
- [ ] Touched the TOC, `.pkgmeta`, `LibTx-1.0` pin or `.github/`? Say so here; a maintainer must review it
