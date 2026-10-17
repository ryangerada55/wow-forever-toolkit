-- Lint fixture: each path below is wrong in a way Windows/macOS players would not notice.
local BAR = "Interface\AddOns\BrokenAddon\Media\bar"                -- SEP: \A and \b are Lua escapes
local GLOW = "Interface\\Addons\\BrokenAddon\\Media\\Glow"           -- PREFIX + CASE (glow.blp)
local FONT = [[Interface\AddOns\BrokenAddon\Media\Font.ttf]]        -- correct (long string)
local ICON = "|TInterface\\AddOns\\BrokenAddon\\Media\\Icon:16|t"    -- CASE (icon.tga)
local SOUND = "Interface/AddOns/BrokenAddon/Sounds/alert.ogg"       -- MISSING
local OTHER = "Interface\\AddOns\\brokenaddon\\Media\\bar.tga"       -- CASE in the addon folder name
local DIR = "Interface\\AddOns\\BrokenAddon\\media\\"                -- CASE in a folder prefix
local EXT = "Interface\\AddOns\\SomeOtherAddon\\x.tga"               -- other addon: not checked
-- "Interface\AddOns\BrokenAddon\InAComment.tga" is ignored
