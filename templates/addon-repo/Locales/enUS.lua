-- Locales/enUS.lua
-- English strings. This file loads first, so every key has an English value; other locale
-- files (Locales/deDE.lua, ...) overwrite only the keys they translate and return early on
-- other clients:  if GetLocale() ~= "deDE" then return end
local _, ns = ...

-- A missing key shows its own name instead of raising an error in the middle of play.
local L = setmetatable({}, {
	__index = function(_, key)
		return key
	end,
})
ns.L = L

L.TITLE = "Tx Example"
L.HELP = "Commands: %s version"
L.VERSION = "%s on %s, interface %d, build %s, %s"
L.UNSUPPORTED_FLAVOR = "This version does not support the %s client and stays inactive."
