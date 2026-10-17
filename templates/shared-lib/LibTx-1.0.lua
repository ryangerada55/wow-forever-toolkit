-- LibTx-1.0: code shared by every Tx Studio addon.
--
-- Each addon embeds its own copy through the packager (.pkgmeta "externals", pinned by tag).
-- LibStub then serves ONE copy to every addon in the session: the one with the highest MINOR
-- that has loaded so far. Rules that follow from that:
--   1. Bump MINOR on every release of this library, even for a one-line fix.
--   2. Within MAJOR "LibTx-1.0", never remove a public function or change what it returns.
--      A breaking change needs a new MAJOR ("LibTx-2.0"), which loads side by side.
--   3. Keep state on the library table (lib.x = lib.x or ...), so an in-place upgrade by a
--      newer copy keeps it.
--   4. Addons call through the library table (LibTx:GetFlavor()), not through functions
--      cached in locals, so they pick up a newer copy that loads later.
local MAJOR, MINOR = "LibTx-1.0", 1
local lib = LibStub:NewLibrary(MAJOR, MINOR)
if not lib then
	return -- an equal or newer copy is already loaded
end

--------------------------------------------------------------------------------
-- Game flavor
--------------------------------------------------------------------------------
-- The one place to fix if Blizzard renames the internal "camelot" label or changes project
-- IDs. Forever reports WOW_PROJECT_ID = WOW_PROJECT_CAMELOT (18) since beta build 70170
-- (2026-10-01); earlier beta builds reported WOW_PROJECT_MAINLINE (1), so the interface band
-- 16000-19999 (versions 1.60.x-1.99.x) is checked too. WOW_PROJECT_CAMELOT is nil on retail
-- and Classic.
-- Use the flavor only for game rules and data. Before calling an API, test that it exists:
-- retail PTR builds already carry most Forever-only APIs, so API presence does not identify
-- the flavor.
local _, build, _, interface = GetBuildInfo()
local FOREVER_PROJECT_ID = WOW_PROJECT_CAMELOT or 18

local flavor
if WOW_PROJECT_ID == FOREVER_PROJECT_ID
	or (WOW_PROJECT_ID == WOW_PROJECT_MAINLINE and interface >= 16000 and interface < 20000) then
	flavor = "forever"
elseif WOW_PROJECT_ID == WOW_PROJECT_MAINLINE then
	flavor = "retail"
elseif WOW_PROJECT_ID == WOW_PROJECT_CLASSIC then
	flavor = "classic_era"
else
	flavor = "classic" -- TBC Anniversary, MoP Classic and the other Classic progression clients
end
lib.flavor = flavor
lib.interface = interface
lib.build = build

-- Returns "forever", "retail", "classic_era" or "classic".
function lib:GetFlavor()
	return self.flavor
end

-- supported: a set such as { forever = true, retail = true }.
function lib:IsFlavorSupported(supported)
	return supported[self.flavor] == true
end

--------------------------------------------------------------------------------
-- Operating system (for bug reports: the same Lua runs on macOS and Windows)
--------------------------------------------------------------------------------
-- IsMacClient/IsWindowsClient/IsLinuxClient are documented on Forever and retail; the guards
-- keep this safe on clients that lack them. Returns "macOS", "Windows", "Linux" or "unknown".
function lib:GetPlatform()
	if IsMacClient and IsMacClient() then
		return "macOS"
	elseif IsWindowsClient and IsWindowsClient() then
		return "Windows"
	elseif IsLinuxClient and IsLinuxClient() then
		return "Linux"
	end
	return "unknown"
end

--------------------------------------------------------------------------------
-- Secret values (retail 12.x and Forever)
--------------------------------------------------------------------------------
-- A secret can be passed to widgets (FontString:SetText, StatusBar:SetValue, ...) but not
-- compared, measured, concatenated or used in arithmetic. issecretvalue is nil on clients
-- without secrets.
function lib.IsSecret(value)
	return issecretvalue ~= nil and issecretvalue(value) == true
end

--------------------------------------------------------------------------------
-- Addon message prefixes
--------------------------------------------------------------------------------
-- Prefixes are one registry for the whole client. Enum.RegisterAddonMessagePrefixResult:
-- 0 Success, 1 DuplicatePrefix (someone registered it first; messages still arrive),
-- 2 InvalidPrefix, 3 MaxPrefixes. AceComm-3.0 rejects prefixes longer than 16 characters.
-- Returns ok, result.
function lib:RegisterPrefix(prefix)
	if type(prefix) ~= "string" or prefix == "" or #prefix > 16 then
		return false, 2
	end
	local result = C_ChatInfo.RegisterAddonMessagePrefix(prefix)
	if type(result) ~= "number" then -- very old clients returned a boolean
		return result ~= false, result
	end
	return result <= 1, result
end
