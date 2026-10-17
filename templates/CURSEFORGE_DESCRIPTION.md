# CurseForge project page template

Fill in the parts in `<angle brackets>`, delete the notes, and paste the result into the
CurseForge project form (and the Wago project page). Keep it in the addon repository as
`.github/curseforge.md` so changes are reviewed like code: the packager never puts dot-folders
into the zip. (`docs/` works too, because the template's `.pkgmeta` lists `docs` under `ignore:`;
any other folder would ship inside every zip.)

Notes from CurseForge's moderation guidance (seen in search results; their pages could not be
opened from our build machine, so re-read them before submitting):

- Name, summary and description must be **in English**; the name must be unique.
- The **summary** is one sentence about what the addon does, not who made it or who it is for,
  and it must not repeat the description.
- The **description** must describe the project properly and be grammatically correct. Thin
  descriptions and wording like "for my friends" or "for my guild" are rejected.
- **Avatar:** a 1:1 PNG of at least 400 × 400 pixels; not a solid color, not another project's
  avatar, nothing copyrighted. Avoid WebP.
- **No download links** to other sites. Donation links are allowed only if modest and at the
  bottom of the description.
- New projects are reviewed after their first file is uploaded; reviews take from minutes to
  three workdays.

---

## Name

`<Tx Bags>`

## Summary (one sentence)

`<Keeps all your bags in one sorted window, with search and item-level labels.>`

## Description

```markdown
**<Tx Bags>** <does what, in one or two sentences, from the player's point of view>.

Built for **WoW: Forever**. <Also available for retail and Classic Era. | Forever only.>

## Features
- <Feature one, written as a benefit: "Find any item in one keystroke with the search box">
- <Feature two>
- <Feature three>

<A screenshot or two: upload them in the project's Images tab and link them here.>

## Getting started
1. Install with the CurseForge app (or WowUp, or the Wago app) and start the game.
2. Type `/txbags` for the command list, or open **Options > AddOns > Tx Bags**.

| Command | What it does |
|---|---|
| `/txbags` | show the commands |
| `/txbags version` | print the addon version, game build and operating system (useful for bug reports) |

## Supported game versions
| Game | Supported | Notes |
|---|---|---|
| WoW: Forever | yes | tested on <build 70425> |
| Retail (Midnight) | <yes / no> | |
| Classic Era | <yes / no> | |

Works on **Windows and macOS** (the game runs the same addon code on both).

## Known limitations
- <Example: "Item levels of other players' gear are not shown in combat: the game hides them from addons there.">

## Bugs, questions and ideas
- **Bug or Lua error:** please open an issue on GitHub: <https://github.com/YOUR-ORG/Tx_Bags/issues/new/choose>.
  Include the text from BugSack and the line `/txbags version` prints.
- **Questions:** our Discord: <https://discord.gg/YOUR-INVITE>.
- Comments here are read, but bugs reported on GitHub get fixed faster.

## Translations
<Tx Bags> is available in <English, German>. Want to help translate? See the
`Locales` folder on GitHub and send a pull request.

## Credits and license
Made by **Tx Studio** (<names>). Source code: <https://github.com/YOUR-ORG/Tx_Bags>, MIT license.
Uses LibStub (public domain).
```

## Project settings to fill in

| Field | Value |
|---|---|
| Main category | `<Bags & Inventory>` (pick the closest WoW addon category) |
| Additional categories | `<at most a few that really apply>` |
| License | MIT (or the license in the repository's `LICENSE`) |
| Source link | `https://github.com/YOUR-ORG/Tx_Bags` |
| Issues link | `https://github.com/YOUR-ORG/Tx_Bags/issues` |
| Members | each team member by exact CurseForge username; agree reward shares in writing |
| Project ID | copy it into every TOC right away: `## X-Curse-Project-ID: <id>`. CI uploads to CurseForge only after the project is approved **and** a release manager has set the repository variable `CURSEFORGE_UPLOADS` to `on` (RELEASING.md, "First publication on CurseForge"). A workflow without that switch uploads as soon as the ID is in the TOC: there, keep `0` until the project is approved |
