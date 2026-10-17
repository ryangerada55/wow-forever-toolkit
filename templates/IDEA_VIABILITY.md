# Is my idea viable on WoW: Forever?

A screen for addon ideas, and the in-game tests that settle them. Use it before anyone starts
building: rate the idea, name the data it needs, and write its acceptance test.

**Valid for:** Forever beta build 1.60.1.70425 (interface 16001), checked on 2026-10-16. Rules can
change in any build, and server-side changes leave no trace in the code. Re-run the tests in
"Prove it in game" on the last beta days, on launch day (2026-11-04) and when raids open
(2026-12-09). See PATCH_DAY.md.

**Why ideas fail on Forever.** Forever plays like Classic but runs retail's Midnight client code.
That brings Midnight's addon restrictions. While a *restriction* is active, many APIs return
**secret values**. Your addon can store a secret and pass it to a display widget, but it cannot
compare it, do maths on it, branch on it or use it as a table key. The combat log is closed to
addons everywhere.

Legend used below:

| Mark | Meaning |
|---|---|
| **Open** | No addon restriction gets in the way. Normal taint and combat-lockdown rules still apply. |
| **Partly restricted** | Works in some situations, or can only *display* some data, not reason about it. |
| **Blocked** | The core of the idea needs data or actions addons cannot get. |
| R / S / B / ? | Readable / Secret (display only) / Blocked / not settled: run the test |
| H / M / L | Confidence: **H** = Blizzard code says so, or code plus a first-hand Forever report agree. **M** = Blizzard's documentation wording or retail evidence only. **L** = inference. |

---

## The 60-second screen

Answer these in order. The first "yes" sets the rating.

1. **Does it need the combat log** (`COMBAT_LOG_EVENT_UNFILTERED`, per-hit damage, healing, misses, kills by others)? **Blocked.**
2. **Does it make decisions on combat data while fighting?** That means comparing, sorting, adding or thresholding auras, cooldown times, health, power, stats, enemy casts, damage numbers or threat on bosses. **Blocked for that part.**
3. **Does it only need to *show* combat data?** Bars, numbers, icons, timers, text. **Partly restricted:** use the display toolkit in "Working with secrets".
4. **Does it need NPC names or IDs, chat text, guild or community data, or addon messages inside dungeons, raids or battlegrounds?** **Partly restricted:** it works in the open world only.
5. **None of the above?** **Open.**

Then fill in the acceptance worksheet at the end of this document, and do not call the idea done
until its test passes in every situation it claims to support.

---

## Ratings by idea category

| Idea category | Rating | What works on Forever | What does not | Prove it |
|---|---|---|---|---|
| **UI, skins, layout, action bars** | Open | Frames, textures, fonts, Edit Mode layouts, both experience presets (Classic and Enhanced, `C_GameRules.GetForeverExperiencePreset`). | Hooking scripts on Blizzard's aura containers and on frames that inherit their *forbidden aspects* (aura tooltips, the target frame's aura area). A widget you feed a secret reads back as secret (`GetText`). Secure frames cannot change in combat. | `/reload` in and out of combat, with both presets |
| **Unit frames, nameplates, party and raid frames** | Partly restricted | Health, power, auras and cast bars *displayed* through widgets: `StatusBar:SetValue`, `UnitHealthPercent` with a curve, `C_UnitAuras.GetAuraDuration`, `UnitCastingDuration` with `StatusBar:SetTimerDuration`. ElvUI/oUF already ship Forever code paths. | In combat: health deficit text, custom thresholds and colors computed in Lua. In dungeons and raids: NPC names and GUIDs (identity is secret). | R3, R8, TxProbe in a dungeon |
| **Bags, inventory, bank** | Open | `C_Container.*` and `C_Item.*` carry no secret annotations; sorting (`C_Container.SortBags`); one-bag preset. | Using items in combat needs secure buttons. Deleting items (`C_Item.DeleteItem`) is restricted. | none special |
| **Auction house, economy, mail** | Open | Scanning, pricing, posting and shopping lists out of combat. | Posting and bidding (`C_AuctionHouse.PostItem`, `PlaceBid`) are flagged `HasRestrictions`: run them from the player's click, not from timers or events. Taking money mailed by a stranger opens Blizzard's secure confirmation (`C_SecureTransfer.TakeMailMoney`, new in build 70425), so an "open all mail" addon cannot collect it unattended. | open all mail with a gift from a non-friend |
| **Professions** | Open | Recipes, skill-ups and reagents (`C_TradeSkillUI`, `C_SkillInfo`, event `SKILL_LINES_CHANGED`). | `CHAT_MSG_SKILL` and `CHAT_MSG_TRADESKILLS` text is secret in dungeons, raids and battlegrounds (M): read skill levels from `C_SkillInfo`, not chat. | none special |
| **Quest helpers, leveling guides** | Open | Quest log (`C_QuestLog.*`, no secret annotations), map pins, the tracker, quest timers, elite quests. Open-world NPC tooltips stay readable in combat. | World-object tooltips lose their quest IDs and text in combat. Inside instances tooltip data is effectively all secret, even out of combat. Questie found both. | hover a quest object in combat |
| **Maps, navigation, coordinates** | Open | `C_Map.GetPlayerMapPosition`, `UnitPosition`, `C_Map.GetBestMapForUnit`. | Positions of group members inside instances: ? | TxProbe `map=` in a dungeon |
| **Social, guild, chat, group sync** | Partly restricted | Everything in the open world, in or out of combat (M). | In dungeons, raids, battlegrounds and encounters, 62 chat and social events (47 of them `CHAT_MSG_*`) and guild/community data (`C_Club.GetMemberInfo` and others) are secret. `C_ChatInfo.SendAddonMessage` returns `AddOnMessageLockdown` (11), so queue messages and resend when the Chat restriction ends. Trial accounts cannot send addon messages at all (reported for beta build notes of 2026-10-08). Addon SAY/YELL outdoors is blocked (rule since patch 8.2.5). Keys must use "Name Surname", not "Name-Realm". | R7 in a dungeon |
| **Collections** | Open | Mounts, toys, appearances and companions (`C_MountJournal`, `C_TransmogCollection`); no secret annotations. | Forever's collection content is small at launch. | none |
| **Leveling and Classic mechanics** (pet happiness, ammo, swing timer, skills, spell ranks, poisons) | Open | The Forever-only APIs carry **no** secret annotations: `C_PetInfo.GetPetHappiness`, `C_PaperDollInfo.AmmoNeeded`, `PLAYER_SWING`, `C_SkillInfo`, `C_QuestLog.GetQuestTimers`, `C_Item.GetWeaponEnchantInfo`, `C_SpellBook.IsSpellBookItemLowRank`. Ammo *counts* come from `GetInventoryItemCount`, an undocumented global (no annotation either way: R4). See the next table. | Anything needing **power changes in combat** (energy tick, mana tick) is ? until R5 runs. Stat panels (defense skill, armor) may freeze in combat: stats are secret when `C_Secrets.ShouldUnitStatsBeSecret()` is true. | R4, R5 |
| **Hardcore and self-found helpers** | Open | `C_GameRules.IsHardcoreActive`, `IsSelfFoundAllowed`; mob level and classification (`UnitLevel`, `UnitClassification`) carry no secret annotation; pre-pull checks. | Danger warnings computed from health or auras in combat. Hardcore is announced for later, not launch (reported). Nobody has checked whether a live mode switches addons off (R6). | R6 on each mode |
| **Combat helpers** (buff and consumable reminders, CC and interrupt helpers, auto-marking, alerts) | Partly restricted | Pre-combat checks (snapshot when the Combat restriction is *Activating*). Blizzard-driven alerts: `C_UnitAuras.AddAuraSound` (register it while no Encounter restriction is active, as BigWigs does), `C_CombatAudioAlert`. Display-only icons and timers. | In-combat "if X then warn" logic on auras, cooldowns or health. Auto-marking: `SetRaidTarget` is flagged `HasRestrictions` and `GetRaidTargetIndex` may return secrets. Chat announcements inside instances. | R2, R8 in combat |
| **Damage meters** | Partly restricted (combat-log meters: Blocked) | A front-end for Blizzard's own meter data, `C_DamageMeter.*`: secret while the Combat restriction is active (show it in bars), readable afterwards. Details ships `Details_Camelot.toc` with a meter built this way. | Anything the combat log would feed: per-hit data, custom metrics, logs of other groups. | TxProbe `dmgMeter=` in and after combat |
| **Threat meters** | Partly restricted | Your threat on normal mobs: documented as generally not secret. | Threat on bosses and compound tokens is secret: bars only, no sorting or warnings. | R9 on trash and on a boss |
| **Boss mods** | Partly restricted, severely (classic designs: Blocked) | Fixed timers anchored on `ENCOUNTER_START` (confirm it fires in Forever dungeons). Cast warnings that display secret spell names (DBM's approach for Forever trash and elites). Aura sounds through `C_UnitAuras.AddAuraSound`. | Blizzard's encounter timeline does not load on Forever (DBM: "Forever has no timeline events"). The combat log is closed. Boss emotes and yells are secret during encounters. Boss casts are secret. Raid syncs are blocked in instances. DBM has no Forever raid pack yet. | first dungeon boss; raids from Dec 9 |
| **Cooldown trackers** | Partly restricted | Your own cooldowns: the booleans `isActive`, `isEnabled` and `isOnGCD` are never secret; show remaining time with `C_Spell.GetSpellCooldownDuration` on a Cooldown or StatusBar. Item cooldowns carry no annotation (?). Blizzard's Cooldown Manager loads on Forever: skin it. | Group cooldown trackers: they need others' casts and addon messages, both blocked in instances. Sorting or "ready in 3 s" logic in combat. | R8, TxProbe `cdHearth=` |
| **Rotation helpers** | Blocked | At most, showing Blizzard's own suggestion, `C_AssistedCombat.GetNextCastSpell`, if `C_AssistedCombat.IsAvailable()` is true on Forever (?). | Any custom priority logic: it compares auras, cooldowns and power in combat. | R10 |
| **PvP tools** | Partly restricted | Battleground objective timers from `CHAT_MSG_BG_SYSTEM_*` (not annotated), honor tracking (`CHAT_MSG_COMBAT_HONOR_GAIN`, not annotated), Classic PvP ranks. World PvP follows open-world combat rules. | During a match (PvPMatch restriction): the scoreboard (`C_PvP.GetScoreInfo` is secret), enemy unit data, comms. War Mode is off on Forever (reported). | TxProbe in a battleground |
| **Accessibility** | Open (smart combat narration: Partly restricted) | Scaling, contrast, colorblind aids, keybinding helpers. Text-to-speech accepts secret text (`C_VoiceChat.SpeakText` is `AllowedWhenTainted`). | Narration that decides *what* to say from combat values. | speak a secret in combat |

---

## What Forever adds: Classic-mechanic APIs that open new ideas

Unless the row says otherwise, these carry no secret annotation in Forever 70425's API documentation,
so they should stay readable in combat and in instances. `GetInventoryItemCount` and
`GetPetExperience` are undocumented globals, so nothing is known either way. Confirm with R4 and
TxProbe before you rely on any of them (M).

| Mechanic | API and events | Idea space |
|---|---|---|
| Hunter pets | `C_PetInfo.GetPetHappiness` (happiness, damage %, loyalty rate), `GetPetLoyalty`, `GetPetTrainingPoints`, `CanPetEatItem`, `GetPetFoodTypes`; events `UNIT_HAPPINESS`, `UNIT_PET_TRAINING_POINTS`, `PET_STATS_UPDATE`; `GetPetExperience` | feeding reminders, food finder in bags, training-point planner |
| Stables | `C_StableInfo.GetNumStableSlots`, `GetNextStableSlotCost`, `BuyStableSlot`, `GetStablePetInfo` | stable manager |
| Ammo | `C_PaperDollInfo.AmmoNeeded`, `UnitUsesAmmo`, `GetInventoryItemCount("player", INVSLOT_AMMO)` | ammo counter and low-ammo warning |
| Swing timer | `C_SwingTimer.IsTargetWithinSwingRange`, `C_SwingTimer.EnableRangeCheck`; events `PLAYER_SWING` (swingDuration, swingType), `PLAYER_SWING_RANGE_UPDATE`; `Enum.PlayerSwingType` | custom swing bars, hunter auto-shot bar, warrior Slam timing. Use `swingDuration` from the event: `UnitAttackSpeed` is a stat API and may be secret in combat |
| Skills | `C_SkillInfo.GetNumSkillLines`, `GetSkillLineInfo`, `GetSkillLineInfoByID`; event `SKILL_LINES_CHANGED` | weapon-skill and defense trainers, profession planners |
| Quests | `C_QuestLog.GetQuestTimers`, `IsEliteQuest`, `GetTrivialRange` | escort timers, elite markers, grey-quest filters |
| Spell ranks | `C_SpellBook.IsSpellBookItemLowRank` | "low rank on your bar" warnings, downranking helpers |
| Weapon buffs | `C_Item.GetWeaponEnchantInfo` | poison, oil and sharpening-stone reminders |
| Classic stats | `GetGlancingBlowChance`, `GetRangedHitModifier`, `GetOffhandHitModifier`, `GetArmorPenetration`, `UnitDefenseSkill` (stat-restricted); `GetHealthRegenFromSpirit`, `GetManaRegenFromSpirit` (not annotated); `UnitResistance` (identity-restricted, so never secret for yourself) | character-sheet extensions, refreshed out of combat |
| Game rules | `C_GameRules.IsHardcoreActive`, `IsSelfFoundAllowed`, `GetForeverExperiencePreset`; event `GAME_RULES_CHANGED` | mode-aware UIs and challenge trackers |
| Names | `RegionalUniqueNamesEnabled`, `UnitNameUnmodified` (returns name and surname), `C_PlayerInfo.ShouldDisplaySurname` | everything that stores per-character data |
| World | `C_DateAndTime.IsDayTime`, event `DIEL_CYCLE_CHANGED`; events `SHARD_TRANSFER`, `SHARD_TRANSFER_IMMINENT` | day/night widgets, group tools that notice shard moves |

---

## When restrictions switch on

`Enum.AddOnRestrictionType` has six members. Read them with
`C_RestrictedActions.GetAddOnRestrictionState(type)`, which returns 0 Inactive, 1 Activating or
2 Active. The event `ADDON_RESTRICTION_STATE_CHANGED(type, state)` fires *before* a restriction is
enforced and *after* it ends. Blizzard's documentation says an Activating restriction "won't be
enforced until event dispatch has completed", and that `C_RestrictedActions.IsAddOnRestrictionActive`
always returns false during the event.

Expected on Forever 70425. **Bold** = active. Every cell is still waiting for a logged in-game
reading: TxProbe produces one.

| Restriction (Blizzard's words) | Open world, out of combat | Open world, in combat (solo, group, world PvP) | Dungeon, out of combat | Dungeon, trash fight | Boss encounter | Battleground match |
|---|---|---|---|---|---|---|
| Combat: "actively affecting combat" | Inactive (H) | **Active** (H) | Inactive (H) | **Active** (H) | **Active** (H) | **Active** while you fight (H) |
| Encounter: "an instance encounter" | Inactive (H) | Inactive (M); world bosses ? | Inactive (H) | Inactive (H) | **Active** (M) | Inactive (M) |
| ChallengeMode: keystone dungeons | Inactive | Inactive | Inactive (M): Forever has no keystone UI | Inactive | Inactive | Inactive |
| PvPMatch: "an active and incomplete PvP match" | Inactive | Inactive (M) | Inactive | Inactive | Inactive | **Active** (M) |
| Map: "a map that applies addon restrictions" | Inactive (M) | Inactive (M) | **Active** (M) | **Active** (M) | **Active** (M) | ? (L) |
| Chat: "addon chat communications are restricted" | Inactive (M) | Inactive (M) | **Active** (M) | **Active** (M) | **Active** (M) | **Active** (M) |

- **Raids** (10, 20 and 40 players, from 2026-12-09) should behave like dungeons. They cannot be tested before then.
- **Hardcore and self-found** add no restriction type of their own; the columns above apply. The separate question is whether a live mode switches addons off (the `UserAddonsDisabled` game rule). The beta cannot answer it: it is a test build, and test builds show the AddOns menu whatever that rule says. Run R6 on launch day, and on Hardcore when it opens.
- **Why these values.** Combat has no instance qualifier in Blizzard's text, and Forever testers saw aura and object-tooltip secrecy while levelling in the open world. Map and Chat come from Blizzard's predicate text ("a dungeon or raid"), and Questie's team found tooltip data "effectively all secret" inside Forever instances even out of combat. ChallengeMode: `Blizzard_ChallengesUI` does not load on Forever.

## What you can read where

R = readable, S = secret (display only), B = blocked, ? = run the test. The "rule" column is
Blizzard's own text for the predicate (`SecretPredicatesDocumentation.lua`, identical on Forever,
retail live and the 12.1.7 PTR).

| Data | Rule (predicate) | Open world, out of combat | Open world, combat | Dungeon, out of combat | Dungeon/raid combat and bosses | Battleground |
|---|---|---|---|---|---|---|
| Auras (`C_UnitAuras.*`, `UNIT_AURA`) | `SecretWhenUnitAuraRestricted`: combat, encounter, challenge-mode or PvP restriction; per-spell "never secret" flags win | R (H) | S (H) | R by the rule (M); ? | S (H) | S (M) |
| Spell and action cooldowns, charges | `SecretWhenCooldownsRestricted`: same as auras. `isActive`, `isEnabled` and `isOnGCD` are never secret | R (H) | S (H) | R by the rule (M) | S (H) | S (M) |
| Item cooldowns (`C_Item.GetItemCooldown`) | none | R (M) | R (M); ? | R (M) | R (M); ? | R (M) |
| Current health, absorbs (`UnitHealth`) | `SecretReturns`, no rule given | ? (L) | S (M) | ? | S (M) | S (M) |
| Max health (`UnitHealthMax`) | secret "when the unit isn't player-controlled" | players and pets R (M); NPCs ? | players and pets R (M); NPCs ? | players and pets R (M); NPCs ? | players and pets R (M); NPCs S (M) | players and pets R (M) |
| Power (`UnitPower`) | secret unless the power type is flagged never-secret; check `C_Secrets.GetPowerTypeSecrecy` (R5) | ? | ? | ? | ? | ? |
| Identity of NPCs: names, GUIDs, NPC IDs, creature type, resistances (`UnitGUID`, `UnitName`, `UnitResistance`) | secret "when the unit isn't player-controlled or in the party/raid" | R (H) | R (H) | S (M) | S (M) | ? |
| Identity of you, your party or raid, and pets | exempt under that rule | R (H) | R (H) | R (H) | R (H) | R (H) |
| Identity of other players (passers-by, battleground enemies) | the rule's wording is ambiguous; `UnitName` is exempt "in PvP when the queried unit is a player" | R (M) | R (M) | rarely needed | rarely needed | names R (M), the rest ? |
| Unit comparisons (`UnitIsUnit`) | "only applies when the player is on an addon-restricted map" | R (H) | R (H) | restricted (M) | restricted (M) | ? |
| Casts by other units (`UnitCastingInfo`, `UNIT_SPELLCAST_*`) | secret "if the unit … is not the player or their pet" | ? | ? | S (M) | S (M) | S (M) |
| Your own casts and your pet's | exempt | R (H) | R (H) | R (H) | R (H) | R (H) |
| Player stats (`UnitStat`, `UnitArmor`, `UnitDefenseSkill`, crit, hit) | secret when `C_Secrets.ShouldUnitStatsBeSecret()`; on retail this follows aura secrecy (community) | R (M) | S? (L) | ? | S? (L) | S? (L) |
| Threat (`UnitThreatSituation`, `UnitDetailedThreatSituation`) | by token pair: you, pet or ally against a normal mob is "generally not secret"; against a boss it is | R (M) | normal mobs R, bosses S (M) | n/a | bosses S (M) | ? |
| Combat log | readers are `SecureOnly` | B (H) | B (H) | B (H) | B (H) | B (H) |
| Blizzard meter data (`C_DamageMeter.GetCombatSessionFromType`) | `SecretWhenInCombat` | R (H) | S (H) | R (H) | S (H) | S while fighting (H) |
| Chat text, guild and community data, LFG list, AFK/DND (62 events, 38 functions) | `SecretInChatMessagingLockdown`: encounter, challenge-mode or PvP restriction, or "a communication-restricted map such as a dungeon or raid" | R (M) | R (M) | S (M) | S (M) | S (M) |
| Not annotated: `CHAT_MSG_ADDON`, `CHAT_MSG_LOOT`, `CHAT_MSG_MONEY`, `CHAT_MSG_COMBAT_XP_GAIN`, `CHAT_MSG_COMBAT_HONOR_GAIN`, `CHAT_MSG_COMBAT_FACTION_CHANGE`, `CHAT_MSG_BG_SYSTEM_*` | no predicate | R (M) | R (M) | R (M) | R (M) | R (M) |
| Sending addon messages (`C_ChatInfo.SendAddonMessage`) | returns `AddOnMessageLockdown` (11) under the Chat restriction | works (M) | works (M) | B (M) | B (M) | B (M) |
| Tooltip quest lines on world objects | runtime only (Questie, builds 70291 and 70338) | R (H) | S (H) | S (M) | S (M) | ? |
| Classic mechanics: pet happiness, ammo, swing events, skills, quest timers, weapon enchants | none | R (M) | R (M) | R (M) | R (M) | R (M) |
| Protected actions: secure frames, targeting, `SetRaidTarget`, group management, AH posting | combat lockdown; `HasRestrictions` | allowed (needs a click where marked) | queue until `PLAYER_REGEN_ENABLED` (H) | allowed | queue (H) | queue (H) |

---

## Working with secrets

**What still works with a secret value** (the Forever 70425 docs mark the setters below
`AllowedWhenTainted`; the other items name their source):

- Showing it: `FontString:SetText`, `SetFormattedText`, `SetTextColor`; `StatusBar:SetValue`, `SetMinMaxValues`, `SetStatusBarColor`; `Texture:SetTexture`, `SetAtlas`, `SetDesaturated`; `SetAlpha`, `SetVertexColor`, and the boolean versions `SetAlphaFromBoolean`, `SetVertexColorFromBoolean`; `GameTooltip:SetText`. Questie also passed secret text to `GameTooltip:AddLine` in a live test.
- Timers without reading times: `C_UnitAuras.GetAuraDuration`, `C_Spell.GetSpellCooldownDuration` and `UnitCastingDuration` return duration objects. Hand them to `StatusBar:SetTimerDuration` or `Cooldown:SetCooldownFromDurationObject` on your own frames; oUF does both.
- Colors and choices without branching: `UnitHealthPercent` and `UnitPowerPercent` with a curve (`C_CurveUtil.CreateColorCurve`); `C_CurveUtil.EvaluateColorFromBoolean`; `C_ClassColor.GetClassColor`; `C_StringUtil.WrapString`; `C_Spell.GetSpellName` and `GetSpellTexture` on a secret spell ID.
- `tostring`, `string.format` and `..` succeed, **but the result stays secret** (Questie, live). `print` accepts secrets, and the docs let `C_VoiceChat.SpeakText` take them.

**What fails:** `==`, `<`, `+`, `if secret then`, `#secret`, `string.len`, `sub`, `find`,
`match` and `gsub`, and secrets as table keys. Reading back a widget you fed a secret
(`GetText`, `GetValue`) returns a secret. Calling `C_UnitAuras.GetAuraDataByIndex` from addon code
while auras are secret raised "Auras cannot be accessed when secret while tainted" for Questie
(issue #7900, open-world levelling).

**Patterns that hold up:**

1. **Test the value, not the situation.** Call `issecretvalue(v)` (or `LibTx.IsSecret(v)`) before any compare or maths. `InCombatLockdown()` does not cover the Map, Encounter or Chat restrictions.
2. **React to restriction changes.** Register `ADDON_RESTRICTION_STATE_CHANGED` and read the `state` payload. On 1 (Activating), Blizzard's documentation says nothing is enforced until the event finishes, so that is the moment for a pre-combat snapshot (TxProbe logs a check of this). On 0 (Inactive), recompute. Details waits for the Combat state to return to 0 before reading meter data.
3. **Guard aura reads.** Check `C_Secrets.ShouldAurasBeSecret()` first and use `pcall`, as Questie does, or display through duration objects instead.
4. **Queue addon messages.** When `C_ChatInfo.InChatMessagingLockdown()` is true, or a send returns 11, keep the message and resend after the Chat restriction ends. AceComm's ChatThrottleLib drops it otherwise.
5. **Keep your state in Lua variables**, not in widgets: a widget's secret aspect spreads to everything you read from it.

---

## Blizzard UI on Forever

From each module's `## AllowLoadGameType` line on the forever branch, build 70425. Forever is game
type `camelot`, and `mainline` includes it unless a module excludes it.

| Loads on Forever | Does not load |
|---|---|
| Damage meter (`Blizzard_DamageMeter`, with a Forever override that hides classification) | Encounter timeline and encounter warnings (`standard` only) |
| Cooldown Manager (`Blizzard_CooldownViewer`) | Encounter Journal / Adventure Guide (`standard, classic`) |
| Swing timer (`Blizzard_SwingTimer`, Forever only) | Keystone UI (`Blizzard_ChallengesUI`) |
| Hardcore UI, quest timers, Vanilla-style group finder, stables, statistics | Retail PvP UI (`Blizzard_PVPUI` excludes camelot) and the retail group finder |
| PvP scoreboard (`Blizzard_PVPMatch`), auction house, professions, collections, personal resource display | Housing, two of the three Delves modules, Garrison, Trading Post |
| Combat audio alerts, private auras UI, the assisted-combat manager (whether the feature works on Forever is runtime: R10) | |

Your addon can skin or replace what loads. It cannot get data from modules that do not load. For
example, `C_EncounterTimeline` exists in the API, but Blizzard does not show a timeline on Forever.

---

## Prove it in game

### One-line checks (`/run`)

Each line is under the 255-character chat limit. They print only `true`/`false` verdicts and
states, never the secret values themselves. If `/run` is refused, use TxProbe below.

| ID | Checks | Line |
|---|---|---|
| R1 | Restriction states (0 Inactive, 1 Activating, 2 Active) | `/run for k,v in pairs(Enum.AddOnRestrictionType) do print(k,C_RestrictedActions.GetAddOnRestrictionState(v)) end print("chatLock",C_ChatInfo.InChatMessagingLockdown(),"lockdown",InCombatLockdown(),"inst",IsInInstance())` |
| R2 | Blizzard's own "will it be secret?" answers | `/run local S=C_Secrets print("auras",S.ShouldAurasBeSecret(),"cds",S.ShouldCooldownsBeSecret(),"stats",S.ShouldUnitStatsBeSecret(),"idT",S.ShouldUnitIdentityBeSecret("target"),"castT",S.ShouldUnitSpellCastingBeSecret("target"))` |
| R3 | Health, power, identity | `/run local s=issecretvalue print("hpP",s(UnitHealth("player")),"hpT",s(UnitHealth("target")),"maxT",s(UnitHealthMax("target")),"powP",s(UnitPower("player")),"guidT",s(UnitGUID("target")),"nameT",s(UnitName("target")))` |
| R4 | Classic mechanics and stats | `/run local s=issecretvalue print("happy",s(C_PetInfo.GetPetHappiness()),"ammo",s(GetInventoryItemCount("player",INVSLOT_AMMO)),"def",s(UnitDefenseSkill("player")),"res",s(select(3,UnitResistance("player",2))),"armor",s(UnitArmor("player")))` |
| R5 | Power secrecy per type (0 never, 1 always, 2 depends on context) | `/run for _,n in ipairs({"Mana","Rage","Energy","Focus","ComboPoints"}) do print(n,C_Secrets.GetPowerTypeSecrecy(Enum.PowerType[n])) end` |
| R6 | Addon and script kill switches, mode | `/run local G,E=C_GameRules,Enum.GameRule print("addonsOff",G.IsGameRuleActive(E.UserAddonsDisabled),"scriptsOff",G.IsGameRuleActive(E.UserScriptsDisabled),"HC",G.IsHardcoreActive(),"SF",G.IsSelfFoundAllowed(),"test",IsTestBuild())` |
| R7 | Can we send addon messages? (0 sent, 11 lockdown, 5 not in group, 10 not in guild) | `/run C_ChatInfo.RegisterAddonMessagePrefix("TxProbe") print("send",C_ChatInfo.SendAddonMessage("TxProbe","x",IsInGroup() and "PARTY" or "GUILD"))` |
| R8 | Aura and cooldown access | `/run local s=issecretvalue local ok,a=pcall(C_UnitAuras.GetAuraDataByIndex,"player",1,"HELPFUL") print("auraOK",ok,"tbl",s(a),"id",not s(a) and type(a)=="table" and s(a.spellId)) local c=C_Spell.GetSpellCooldown(6603) print("cd",c and s(c.startTime))` |
| R9 | Threat, level, classification, enemy casts | `/run local s=issecretvalue print("thr",s(UnitThreatSituation("player","target")),"pct",s(select(3,UnitDetailedThreatSituation("player","target"))),"lvl",s(UnitLevel("target")),"cls",s(UnitClassification("target")),"cast",s(UnitCastingInfo("target")))` |
| R10 | Assisted combat, swing range, item cooldown | `/run print("assist",C_AssistedCombat.IsAvailable()) print("swing",C_SwingTimer.IsTargetWithinSwingRange(Enum.PlayerSwingType.MainHand),"hearthCD",issecretvalue(C_Item.GetItemCooldown(6948)))` |

To check a value *in combat*, put the line in a macro and press it mid-fight. To check a target's
data, target the mob first; R3 and R9 need a target, R8 a buff on you.

### TxProbe: a throwaway test addon that logs everything above

Create `Interface/AddOns/TxProbe/` with the two files below. `/txprobe` prints and saves one
snapshot. `/txprobe auto` takes a snapshot on every restriction change. `/txprobe send` also tries
an addon message. The log is saved in `WTF/Account/<account>/SavedVariables/TxProbe.lua` (after a
`/reload` or logout); attach it to the idea's issue. It records only verdicts ("SECRET",
"readable", states), never names or GUIDs. Do not ship it.

`TxProbe.toc`:

```text
## Interface: 16001
## Title: TxProbe (test tool)
## Notes: Records addon restriction states and secret values. Do not ship.
## SavedVariables: TxProbeDB
TxProbe.lua
```

`TxProbe.lua`:

```lua
-- TxProbe: records which addon restrictions are active and which values reach addons as secrets.
-- Test tool only; never ship it. /txprobe = snapshot, /txprobe auto = snapshot on every
-- restriction change, /txprobe send = also try an addon message, /txprobe clear = empty the log.
local R, S, T = C_RestrictedActions, C_Secrets, Enum.AddOnRestrictionType
local iss = issecretvalue or function() return false end
local PREFIX, MAXLOG = "TxProbe", 3000
local auto, lastSend = false, "-"

local function val(f, ...)               -- never compares or prints a secret
  local ok, v = pcall(f, ...)
  if not ok then return "ERR" end
  if iss(v) then return "SECRET" end
  if v == nil then return "nil" end
  return tostring(v)
end

local function field(f, key, ...)        -- one field of a returned table
  return val(function(...)
    local t = f(...)
    if iss(t) then return t end
    if type(t) ~= "table" then return nil end
    return t[key]
  end, ...)
end

local function third(f, ...) return val(function(...) return select(3, f(...)) end, ...) end

local function shown(v)                  -- hide names and GUIDs, keep the verdict
  if v == "SECRET" or v == "nil" or v == "ERR" then return v end
  return "readable"
end

local function context()
  local name, instType, diffID, _, _, _, _, instID = GetInstanceInfo()
  return ("%s|%s|diff=%s|id=%s|combat=%s|enc=%s|group=%s|bg=%s|map=%s"):format(
    tostring(name), tostring(instType), tostring(diffID), tostring(instID),
    val(UnitAffectingCombat, "player"), val(C_InstanceEncounter.IsEncounterInProgress),
    IsInRaid() and "raid" or (IsInGroup() and "party" or "solo"),
    val(C_PvP.IsActiveBattlefield), val(C_Map.GetBestMapForUnit, "player"))
end

local function rows()
  local r = {}
  local function add(k, v) r[#r + 1] = k .. "=" .. v end
  for _, n in ipairs({ "Combat", "Encounter", "ChallengeMode", "PvPMatch", "Map", "Chat" }) do
    add("st." .. n, val(R.GetAddOnRestrictionState, T[n]))   -- 0 Inactive, 1 Activating, 2 Active
  end
  add("chatLock", val(C_ChatInfo.InChatMessagingLockdown))
  add("lockdown", val(InCombatLockdown))
  add("p.auras", val(S.ShouldAurasBeSecret))
  add("p.cds", val(S.ShouldCooldownsBeSecret))
  add("p.stats", val(S.ShouldUnitStatsBeSecret))
  add("p.idT", val(S.ShouldUnitIdentityBeSecret, "target"))
  add("p.castT", val(S.ShouldUnitSpellCastingBeSecret, "target"))
  add("p.hpMaxT", val(S.ShouldUnitHealthMaxBeSecret, "target"))
  add("p.powP", val(S.ShouldUnitPowerBeSecret, "player"))
  add("p.thrT", val(S.ShouldUnitThreatStateBeSecret, "player", "target"))
  add("powSecrecy", val(function() return S.GetPowerTypeSecrecy((UnitPowerType("player"))) end))
  add("hpP", val(UnitHealth, "player"))
  add("hpT", val(UnitHealth, "target"))
  add("hpMaxT", val(UnitHealthMax, "target"))
  add("powP", val(UnitPower, "player"))
  add("guidT", shown(val(UnitGUID, "target")))      -- identity: only "readable"/"SECRET" is logged
  add("nameT", shown(val(UnitName, "target")))
  add("lvlT", val(UnitLevel, "target"))
  add("classifT", val(UnitClassification, "target"))
  add("castT", val(UnitCastingInfo, "target"))
  add("thrT", val(UnitThreatSituation, "player", "target"))
  add("thrPctT", third(UnitDetailedThreatSituation, "player", "target"))
  add("aura1", field(C_UnitAuras.GetAuraDataByIndex, "spellId", "player", 1, "HELPFUL"))
  add("cdAttack", field(C_Spell.GetSpellCooldown, "startTime", 6603))
  add("cdHearth", val(C_Item.GetItemCooldown, 6948))
  add("dmgMeter", field(C_DamageMeter.GetCombatSessionFromType, "totalAmount",
    Enum.DamageMeterSessionType.Current, Enum.DamageMeterType.DamageDone))
  add("defense", val(UnitDefenseSkill, "player"))
  add("resFireP", third(UnitResistance, "player", 2))
  add("armorP", val(UnitArmor, "player"))
  add("happy", val(C_PetInfo.GetPetHappiness))
  add("ammo", val(GetInventoryItemCount, "player", INVSLOT_AMMO))
  add("swingRange", val(C_SwingTimer.IsTargetWithinSwingRange, Enum.PlayerSwingType.MainHand))
  add("addonsOff", val(C_GameRules.IsGameRuleActive, Enum.GameRule.UserAddonsDisabled))
  add("scriptsOff", val(C_GameRules.IsGameRuleActive, Enum.GameRule.UserScriptsDisabled))
  add("hardcore", val(C_GameRules.IsHardcoreActive))
  add("selfFound", val(C_GameRules.IsSelfFoundAllowed))
  add("send", lastSend)
  return r
end

local function save(line)
  TxProbeDB = TxProbeDB or { log = {} }
  local log = TxProbeDB.log
  log[#log + 1] = date("%Y-%m-%d %H:%M:%S") .. " " .. line
  while #log > MAXLOG do table.remove(log, 1) end
end

local function snapshot(why)
  local head = ("[%s] build %s %s"):format(why, select(2, GetBuildInfo()), context())
  local body = table.concat(rows(), " ")
  save(head .. " || " .. body)
  print("|cff33ff99TxProbe|r " .. head)
  print(body)
end

local f = CreateFrame("Frame")
f:RegisterEvent("ADDON_RESTRICTION_STATE_CHANGED")
f:RegisterEvent("ENCOUNTER_START")
f:RegisterEvent("ENCOUNTER_END")
f:RegisterEvent("ZONE_CHANGED_NEW_AREA")
f:SetScript("OnEvent", function(_, event, a, b)
  if event == "ADDON_RESTRICTION_STATE_CHANGED" then
    -- IsAddOnRestrictionActive is always false during this event; read the payload instead.
    local name = "?"
    for k, v in pairs(T) do if v == a then name = k end end
    save(("event %s %s state=%s | %s"):format(event, name, tostring(b), context()))
    if b == 1 then  -- Activating: Blizzard says nothing is enforced until this event finishes
      save(("  during Activating: aura1=%s cdAttack=%s hpT=%s"):format(
        field(C_UnitAuras.GetAuraDataByIndex, "spellId", "player", 1, "HELPFUL"),
        field(C_Spell.GetSpellCooldown, "startTime", 6603), val(UnitHealth, "target")))
    end
    if auto then C_Timer.After(0.2, function() snapshot("auto " .. name .. "=" .. tostring(b)) end) end
  else
    save(("event %s %s | %s"):format(event, tostring(a), context()))
  end
end)

SLASH_TXPROBE1 = "/txprobe"
SlashCmdList.TXPROBE = function(msg)
  msg = (msg or ""):lower()
  if msg == "auto" then
    auto = not auto
    print("TxProbe auto snapshots: " .. tostring(auto))
  elseif msg == "clear" then
    TxProbeDB = { log = {} }
    print("TxProbe log cleared")
  else
    if msg == "send" then
      C_ChatInfo.RegisterAddonMessagePrefix(PREFIX)
      local channel = IsInGroup() and "PARTY" or (IsInGuild() and "GUILD" or nil)
      lastSend = channel and val(C_ChatInfo.SendAddonMessage, PREFIX, "probe", channel) or "no-channel"
    end
    snapshot("manual")
  end
end
```

How to read a snapshot: `st.Map=2` means the Map restriction is active. `hpT=SECRET` means target
health is display-only here. `aura1=ERR` means the aura call itself failed, as in Questie's report.
`send=11` means addon messages are locked down. A log line "during Activating" with readable
values confirms the pre-combat snapshot pattern.

### Force restrictions at your desk

Forever 1.60.1 has six test CVars (in the client's CVar list for build 70338; retail has them too).
In Blizzard's words, with one set, "APIs guarded by" that restriction "will be restricted, or may
return secrets". That lets you test your secret handling in a city with `/reload` at hand:

```text
/console addonCombatRestrictionsForced 1
/console addonEncounterRestrictionsForced 1
/console addonChallengeModeRestrictionsForced 1
/console addonPvPMatchRestrictionsForced 1
/console addonMapRestrictionsForced 1
/console addonChatRestrictionsForced 1
```

Set them back to 0 when done. They show that your code *survives* secrets. They do not show what
the live servers turn on: only the real-situation runs below show that.

### Where and when to run the checks

| Situation | Run | When |
|---|---|---|
| Open world, out of combat, solo and in a party | R1-R10 or `/txprobe` | now (beta), launch day |
| Open world, in combat (a quest mob; then an elite) | `/txprobe auto`, R2/R3/R8/R9 as macros | now, launch day |
| A Forever dungeon: on entry, trash, first boss, after the boss | `/txprobe auto` + `/txprobe send` | first dungeon run after launch, or on beta if reachable |
| Battleground (the new 15v15 map, as reported) | `/txprobe auto` | when it opens |
| Raid (10/20/40) | `/txprobe auto` | from 2026-12-09 |
| Each game mode: normal, Hardcore, self-found | R6 | launch day; Hardcore when it opens |
| World boss | R1 during the fight (Encounter?) | when one spawns |

Beta notes for planning: the beta is reported to close on 2026-10-21 or 22, and a 2026-10-19
stress test is not confirmed. If nobody on the team has access, run everything on 2026-11-04 and
update this document the same day.

### Acceptance worksheet (copy into the idea's issue)

```text
Idea:
Rating from the screen (Open / Partly restricted / Blocked):
Data it needs           | Situations it must work in        | R/S/B/? per situation (tables above)
------------------------|-----------------------------------|-------------------------------------
e.g. pet happiness      | open world, dungeons, combat      | R / R / R (M)  -> verify with R4
e.g. target health      | open world combat                 | S (M) -> display only, no thresholds
Fallback when data is secret (display-only? hide? queue until restriction ends?):
Acceptance test (which R-lines or TxProbe runs, where, and the expected values):
Result (build number, date, tester, TxProbe log attached):
```

---

## What the code cannot settle yet

| Unknown | Settle it with |
|---|---|
| Is current health (`UnitHealth`) secret out of combat in the open world, and for which units? | R3 out of combat, on a mob and on yourself |
| Which power types are never secret (energy and mana ticks depend on it) | R5, then R3 `powP` in combat |
| Are other units' casts secret in the open world? | R9 `cast` on a casting mob in the open world |
| Do stats go secret in open-world combat? | R4 in combat |
| Are auras and cooldowns readable inside a dungeon out of combat, as the rule text implies? | `/txprobe` in a dungeon between pulls |
| Does any Forever map outside dungeons and raids apply the Map restriction (new zones, battlegrounds)? | `/txprobe auto` while travelling, and in a battleground |
| Does a world boss start the Encounter restriction? | R1 during the fight |
| Does any live mode (Hardcore, self-found) switch addons or `/run` off? | R6 on launch day and when Hardcore opens |
| Which spells are flagged "never secret" on Forever? | TxProbe `aura1` with common buffs in combat |
| Is `C_AssistedCombat` available to Forever classes? | R10 |

## Sources

Research notes: `WoW Forever addon project playbook/gap_3.md` (full evidence, links and
confidence), `forever.md`, `coding.md`. Main evidence:

- Blizzard UI source, forever branch at build 70425 (Gethe/wow-ui-source, commit `b401e033`): `RestrictedActionsConstantsDocumentation.lua`, `RestrictedActionsDocumentation.lua`, `SecretPredicatesDocumentation.lua` (identical on retail live and the 12.1.7 PTR), the per-API annotations, and the module TOCs.
- Forever CVar and enum dumps (Ketho/BlizzardInterfaceResources, branch `forever`, build 70338).
- First-hand Forever reports: Questie `docs/forever-tooltip-secrets.md` (builds 70291 and 70338) and issue #7900. Forever code paths in DBM, BigWigs, ElvUI and Details (2026-10-14 to 2026-10-16).
