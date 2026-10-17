-- Core.lua: references used by the scanner tests.
-- A comment that mentions C_Foo.ChangedArgs(1) must not count.
local addonName, ns = ...
local GetTime = GetTime            -- caching a global counts as a reference
local UnitFoo = UnitFoo

local f = CreateFrame("Frame")
f:RegisterEvent("FOO_REMOVED")
f:RegisterEvent('FOO_UPDATED')
f:SetScript("OnEvent", function(self, event, ...)
	if event == "FOO_REMOVED" then
		C_Foo.RemovedThing()
	end
end)

local name = C_Foo["GetThing"](42)
local msg = "C_Foo.StatFunc is only mentioned in a string"
local kind = Enum.FooType.C
local isForever = WOW_PROJECT_ID == WOW_PROJECT_CAMELOT
local hp = UnitFoo("player")

function ns.Thing()
	return [[ long string C_Foo.ChangedArgs ]]
end
