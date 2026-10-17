-- Core.lua
-- Startup, saved variables and the slash command. Everything lives in the private addon
-- table (ns); the only globals are the SavedVariables table and the SLASH_ strings, all
-- prefixed with the addon's name (see .luacheckrc).
local addonName, ns = ...
local L = ns.L
local LibTx = LibStub("LibTx-1.0")

-- Flavors this addon supports. Keep in step with the ## Interface line in the TOC.
local SUPPORTED_FLAVORS = { forever = true }

local function Print(message)
	print("|cff33ff99" .. L.TITLE .. "|r: " .. message)
end

-- The client decides from the TOC whether to load us, and its rules for interface numbers
-- outside its own range are not documented. Stay inactive on a client we do not support.
if not LibTx:IsFlavorSupported(SUPPORTED_FLAVORS) then
	local notice = CreateFrame("Frame")
	notice:RegisterEvent("PLAYER_LOGIN")
	notice:SetScript("OnEvent", function()
		Print(L.UNSUPPORTED_FLAVOR:format(LibTx:GetFlavor()))
	end)
	return
end

--------------------------------------------------------------------------------
-- Saved variables
--------------------------------------------------------------------------------
-- DB_VERSION is the layout of TxExampleDB. Bump it when the layout changes and add a
-- migration step, so players keep their settings across updates.
local DB_VERSION = 1

local function InitDatabase()
	TxExampleDB = TxExampleDB or {}
	local db = TxExampleDB
	db.dbVersion = db.dbVersion or DB_VERSION
	-- Migrations, oldest first:
	-- if db.dbVersion < 2 then ... ; db.dbVersion = 2 end
	if db.enabled == nil then
		db.enabled = true
	end
	ns.db = db
end

--------------------------------------------------------------------------------
-- Events
--------------------------------------------------------------------------------
local events = {}

function events.ADDON_LOADED(loadedName)
	if loadedName ~= addonName then
		return
	end
	ns.eventFrame:UnregisterEvent("ADDON_LOADED")
	InitDatabase()
end

function events.PLAYER_LOGIN()
	-- Build the UI here: character data and every non-load-on-demand addon are available.
end

local eventFrame = CreateFrame("Frame")
eventFrame:SetScript("OnEvent", function(_, event, ...)
	events[event](...)
end)
for event in pairs(events) do
	eventFrame:RegisterEvent(event)
end
ns.eventFrame = eventFrame

--------------------------------------------------------------------------------
-- Slash command
--------------------------------------------------------------------------------
-- Slash commands are one client-wide table: if two addons register the same /command, one
-- silently replaces the other. Use the addon's own name for both the key and the command.
SLASH_TXEXAMPLE1 = "/txexample"
SlashCmdList.TXEXAMPLE = function(message)
	local command = strtrim(message or ""):lower()
	if command == "version" then
		-- Everything a bug report needs in one line: addon version, flavor, interface, build, OS.
		local version = C_AddOns.GetAddOnMetadata(addonName, "Version")
		Print(L.VERSION:format(version or "?", LibTx:GetFlavor(), LibTx.interface, LibTx.build, LibTx:GetPlatform()))
	else
		Print(L.HELP:format(SLASH_TXEXAMPLE1))
	end
end
