--[[ platform-notes.lua - Mac/Windows differences an addon must handle (WoW: Forever, retail)

Every global function used below exists on Blizzard's `forever` branch (1.60.1 build 70425);
check_platform_api.py in this folder re-checks that against the UI source mirror.
This file is an example to copy from, not an addon: nothing runs until you call the functions.

What differs between the Windows and macOS clients (both run the same addon zip):
  * Platform checks: IsMacClient(), IsWindowsClient(), IsLinuxClient() (BuildDocumentation.lua;
    the file is identical on forever and live 12.1.5). There is no native Linux client.
  * Command (Cmd) on a Mac is the META modifier: IsMetaKeyDown(), IsLeftMetaKeyDown(),
    IsRightMetaKeyDown(). Binding strings put modifiers in the order ALT-CTRL-SHIFT-META
    (Blizzard_SharedXML/KeyCommand.lua: "MUST BE IN THIS ORDER").
  * Secure action buttons only know the alt-/ctrl-/shift- attribute prefixes
    (SecureButton_GetModifierPrefix in SecureTemplates.lua), so Cmd+click on a secure button is a
    plain click. Never make a protected action depend on Cmd.
  * Mac-only CVars: MacUseCommandLeftClickAsRightClick, MacDisableOsShortcuts
    (Blizzard_SettingsDefinitions_Shared/Mac.lua registers them only when IsMacClient()).
  * PlatformIsHandheld() exists on forever and ptr 12.1.7 but NOT on live 12.1.5: guard it.
]]

local PlatformNotes = {}

-- 1. Platform checks --------------------------------------------------------------------------
-- On Forever/retail all three exist. On the Classic flavors Blizzard's own code calls
-- IsMacClient() but neither documents nor calls IsWindowsClient/IsLinuxClient, so code shared
-- with Classic should test that the function exists first (as done here).
function PlatformNotes.GetPlatform()
	if IsMacClient() then
		return "mac"
	elseif IsWindowsClient and IsWindowsClient() then
		return "windows"
	elseif IsLinuxClient and IsLinuxClient() then
		return "linux"
	end
	return "unknown"
end

-- Text hints: say "Cmd" on a Mac and "Ctrl" elsewhere (DBM does the same for copy prompts).
function PlatformNotes.CopyHint()
	if IsMacClient() then
		return "Press Cmd-C to copy"
	end
	return "Press Ctrl-C to copy"
end

-- Folder paths shown to the user (DBM picks "\\" or "/" with IsWindowsClient(); IsMacClient()
-- also works on Classic). Windows players expect backslashes, Mac players slashes.
function PlatformNotes.UserPath(...)
	local sep = IsMacClient() and "/" or "\\"
	return table.concat({ ... }, sep)
end

-- Forever-only API: the function does not exist on live 12.1.5, so test before calling.
function PlatformNotes.IsHandheld()
	return PlatformIsHandheld ~= nil and PlatformIsHandheld() or false
end

-- Mac users may right-click with Cmd+left-click when this CVar is on; the CVar is only
-- registered by the Mac client, so ask only there.
function PlatformNotes.CommandClickIsRightClick()
	return IsMacClient() and C_CVar.GetCVarBool("MacUseCommandLeftClickAsRightClick") or false
end

-- 2. Key-binding capture that works with Cmd (META) ------------------------------------------
-- Same order and rules as Blizzard's CreateKeyChordStringUsingMetaKeyState and
-- IsKeyPressIgnoredForBinding (BindingUtil.lua): ALT, CTRL, SHIFT, META, then the key;
-- a lone modifier, UNKNOWN, left click (BUTTON1) and right click (BUTTON2) are not bindings.
local IGNORED_KEYS = {
	LALT = true, RALT = true, LCTRL = true, RCTRL = true, LSHIFT = true, RSHIFT = true,
	LMETA = true, RMETA = true, ALT = true, CTRL = true, SHIFT = true, META = true,
	UNKNOWN = true, BUTTON1 = true, BUTTON2 = true,
}

function PlatformNotes.BuildChord(keyOrButton)
	-- mouse buttons arrive as "LeftButton", "Button4"...; bindings want "BUTTON1", "BUTTON4"
	local key = GetConvertedKeyOrButton(keyOrButton)
	if IGNORED_KEYS[key] then
		return nil
	end
	local chord = ""
	if IsAltKeyDown() then chord = chord .. "ALT-" end
	if IsControlKeyDown() then chord = chord .. "CTRL-" end
	if IsShiftKeyDown() then chord = chord .. "SHIFT-" end
	if IsMetaKeyDown() then chord = chord .. "META-" end -- Cmd on a Mac
	return chord .. key
end

-- Bind a captured chord to a binding action (from your Bindings.xml) and save it.
function PlatformNotes.BindChord(chord, action)
	if InCombatLockdown() then
		return false, "cannot change bindings in combat"
	end
	if not SetBinding(chord, action) then
		return false, "SetBinding failed"
	end
	SaveBindings(GetCurrentBindingSet())
	-- GetBindingText turns "META-K" into the client's localized display text
	return true, GetBindingText(chord)
end

-- A frame that captures the next key or mouse button. Call from a button's OnClick.
function PlatformNotes.CreateBindingCatcher(action, onDone)
	local f = CreateFrame("Button", nil, UIParent)
	f:SetAllPoints(UIParent)
	f:EnableKeyboard(true)
	f:RegisterForClicks("AnyUp")
	local function finish(input)
		local chord = PlatformNotes.BuildChord(input)
		if not chord then
			return -- a lone modifier or a plain left/right click: keep waiting
		end
		f:Hide()
		f:EnableKeyboard(false)
		if chord == "ESCAPE" then
			return onDone(false, "cancelled")
		end
		return onDone(PlatformNotes.BindChord(chord, action))
	end
	f:SetScript("OnKeyDown", function(_, key) finish(key) end)
	f:SetScript("OnClick", function(_, button) finish(button) end)
	return f
end

-- 3. Secure buttons: use alt-/ctrl-/shift- only ----------------------------------------------
-- There is no "meta-" prefix, so offer Alt/Ctrl/Shift variants and document that Cmd is ignored.
function PlatformNotes.ConfigureSecureButton(button, spellName)
	button:SetAttribute("type", "spell")
	button:SetAttribute("spell", spellName)
	button:SetAttribute("shift-type1", "macro")
	button:SetAttribute("shift-macrotext1", "/cast [@player] " .. spellName)
	-- NOT supported: button:SetAttribute("meta-type1", ...)
end

return PlatformNotes
