-- smoke.lua: load this addon the way a game client does, in plain Lua 5.1, and fail on any error.
--
--   lua tests/harness/smoke.lua [ADDON_DIR] [FLAVOR] [LOCALE]
--
-- ADDON_DIR  the addon folder: the repository root (default; the libraries must be in Libs/,
--            see README.md, "Developing") or a packaged folder such as .release/Tx_Example
-- FLAVOR     forever (default), forever_pre70170, retail or classic_era
-- LOCALE     enUS (default) or another client locale, for example deDE
-- SMOKE_ADDON (environment) names the addon when the folder is named differently (a checkout
-- folder "wow-addon-foo" that holds Foo.toc); run.sh sets it from the TOC file name.
--
-- What it does, with stub WoW APIs and real copies of the addon's own files and libraries:
--   * picks the TOC the client would load and applies its game-type gate (## AllowLoadGameType /
--     ## ExcludeLoadGameType; words each client knows, from the wowless project's real-client tests)
--   * checks that the TOC lists this client's interface number and that every listed file exists
--   * runs every file in TOC order with (addonName, ns), as the client does, so a missing library
--     ("Cannot find a library instance"), a nil global or a load-order mistake fails here
--   * fires ADDON_LOADED (another addon first, then this one) and PLAYER_LOGIN, then checks the
--     SavedVariables tables and that no global outside .luacheckrc's list was created (frames
--     named after the addon, such as CreateFrame("Frame", "Tx_ExampleFrame"), are allowed)
--   * checks that every SLASH_<KEY>n string has its SlashCmdList.<KEY> handler, then runs the
--     command with "", "help" and "version" (plus SMOKE_SLASH="toggle,reset,...")
--   * calls the TOC's addon compartment functions (Forever and retail)
--   * with SMOKE_COMBAT=options: runs "options" in combat and checks that it waits for
--     PLAYER_REGEN_ENABLED (for an addon that copied the HelloAzeroth sample's combat queue)
-- An addon that SUPPORTED_FLAVORS keeps inactive on this client must print its notice and create
-- nothing. Exit status 1 on any FAIL. run.sh runs every client the TOC lists.
local addonDir, flavorKey, locale = ...
local say = print -- the stub client below replaces print to record what the addon prints
local HERE = ((arg and arg[0]) or ""):match("^(.*)[/\\][^/\\]*$") or "."
addonDir = (addonDir and addonDir ~= "") and addonDir or (HERE .. "/../..")
flavorKey = flavorKey or "forever"
locale = locale or "enUS"

local FLAVORS = {
	forever = { version = "1.60.1", build = "70425", interface = 16001, project = 18, libtx = "forever",
		tocs = { "Camelot", "Forever", "Mainline" }, compartment = true, secrets = true,
		known = { camelot = true, mainline = true, forever = true, standard = false, classic = false, vanilla = false,
			tbc = false, wrath = false, cata = false, mists = false, plunderstorm = false, wowhack = false } },
	forever_pre70170 = { version = "1.60.1", build = "70009", interface = 16001, project = 1, libtx = "forever",
		tocs = { "Camelot", "Forever", "Mainline" }, compartment = true, secrets = true,
		known = { camelot = true, mainline = true, forever = true, standard = false, classic = false, vanilla = false,
			tbc = false, wrath = false, cata = false, mists = false, plunderstorm = false, wowhack = false } },
	retail = { version = "12.1.5", build = "70391", interface = 120105, project = 1, libtx = "retail",
		tocs = { "Standard", "Mainline" }, compartment = true, secrets = true,
		known = { standard = true, mainline = true, classic = false, vanilla = false, tbc = false, wrath = false,
			cata = false, mists = false, plunderstorm = false, wowhack = false } },
	classic_era = { version = "1.15.9", build = "70003", interface = 11509, project = 2, libtx = "classic_era",
		tocs = { "Vanilla", "Classic" }, compartment = false, secrets = false,
		known = { classic = true, vanilla = true, standard = false, mainline = false, tbc = false, wrath = false,
			cata = false, mists = false, plunderstorm = false, wowhack = false } },
}
local flavor = assert(FLAVORS[flavorKey], "unknown flavor " .. tostring(flavorKey) .. " (forever, forever_pre70170, retail, classic_era)")

---------------------------------------------------------------------------
-- Results
---------------------------------------------------------------------------
local failed, checks = 0, 0
local function check(name, ok, detail)
	checks = checks + 1
	if ok then
		say("PASS " .. name)
	else
		failed = failed + 1
		say("FAIL " .. name .. (detail and (": " .. tostring(detail)) or ""))
	end
	return ok
end
local function protect(name, fn, ...)
	local args, n = { ... }, select("#", ...)
	local ok, err = xpcall(function() return fn(unpack(args, 1, n)) end, function(e) return debug.traceback(e, 2) end)
	return check(name, ok, err)
end
local function finish()
	say(string.format("%s/%s: %d checks, %d failed", flavorKey, locale, checks, failed))
	os.exit(failed == 0 and 0 or 1)
end

---------------------------------------------------------------------------
-- Which TOC the client loads (folder name first, as the client does)
---------------------------------------------------------------------------
local function readFile(path)
	local f = io.open(path, "rb")
	if not f then return nil end
	local s = f:read("*a")
	f:close()
	return s
end
local function words(list)
	local t = {}
	for w in (list or ""):gmatch("[^,%s]+") do t[#t + 1] = w:lower() end
	return t
end
-- Game-type gates as real clients evaluate them (wowless commit 413e04ec, 2026-09-24): a list whose
-- words the client does not know at all is ignored; otherwise it matches when one of its words is
-- this client's own game type or family.
local function listMatches(list)
	local known, hit = false, false
	for _, w in ipairs(words(list)) do
		if flavor.known[w] ~= nil then
			known = true
			if flavor.known[w] then hit = true end
		end
	end
	return known, hit
end
local function gateAllows(allow, exclude)
	if allow then
		local known, hit = listMatches(allow)
		if known and not hit then return false end
	end
	if exclude then
		local _, hit = listMatches(exclude)
		if hit then return false end
	end
	return true
end

local dirName = addonDir:gsub("[/\\]+$", ""):match("([^/\\]+)$") or addonDir
local function tocText(name)
	return readFile(addonDir .. "/" .. name .. ".toc")
end
local baseName = os.getenv("SMOKE_ADDON") or dirName
local candidates = {}
for _, suffix in ipairs(flavor.tocs) do candidates[#candidates + 1] = baseName .. "_" .. suffix end
candidates[#candidates + 1] = baseName
local tocName, toc
for _, c in ipairs(candidates) do
	toc = tocText(c)
	if toc then tocName = c break end
end
if not check("a TOC this " .. flavorKey .. " client loads exists in " .. addonDir, toc ~= nil) then finish() end
local addonName = baseName

local meta, files = {}, {}
for line in (toc .. "\n"):gmatch("([^\n]*)\n") do
	line = line:gsub("\r$", "")
	local key, value = line:match("^##%s*([^:]+):%s*(.-)%s*$")
	if key then
		meta[key] = value
	elseif line:match("%S") and not line:match("^%s*#") then
		local allow = line:match("%[AllowLoadGameType%s+([^%]]*)%]")
		local exclude = line:match("%[ExcludeLoadGameType%s+([^%]]*)%]")
		local path = line:gsub("%s*%[.-%]", ""):gsub("^%s+", ""):gsub("%s+$", ""):gsub("\\", "/")
		files[#files + 1] = { path = path, load = gateAllows(allow, exclude) }
	end
end
say("addon " .. addonName .. ", " .. tocName .. ".toc, client " .. flavorKey .. " " .. flavor.version .. " (" .. flavor.interface .. ")")

if not gateAllows(meta.AllowLoadGameType, meta.ExcludeLoadGameType) then
	check("game-type gate keeps the addon off " .. flavorKey .. " (## AllowLoadGameType: " .. tostring(meta.AllowLoadGameType)
		.. ", ## ExcludeLoadGameType: " .. tostring(meta.ExcludeLoadGameType) .. "): not loaded, as intended", true)
	finish()
end
local interfaces = {}
for n in (meta.Interface or ""):gmatch("%d+") do interfaces[tonumber(n)] = true end
check("## Interface lists " .. flavor.interface .. " (not out of date on this client)", interfaces[flavor.interface])

---------------------------------------------------------------------------
-- Stub client
---------------------------------------------------------------------------
local printed, frames, opened, frameNames = {}, {}, {}, {}
local inCombat = false
local function stub(kind)
	local o = { __kind = kind, __scripts = {}, __events = {}, __shown = true }
	return setmetatable(o, { __index = function(_, k)
		if k == "RegisterEvent" then return function(self, e) self.__events[e] = true end end
		if k == "UnregisterEvent" then return function(self, e) self.__events[e] = nil end end
		if k == "IsEventRegistered" then return function(self, e) return self.__events[e] == true end end
		if k == "SetScript" then return function(self, s, f) self.__scripts[s] = f end end
		if k == "GetScript" then return function(self, s) return self.__scripts[s] end end
		if k == "HookScript" then return function(self, s, f) local old = self.__scripts[s]; self.__scripts[s] = function(...) if old then old(...) end f(...) end end end
		if k == "Show" then return function(self) self.__shown = true end end
		if k == "Hide" then return function(self) self.__shown = false end end
		if k == "SetShown" then return function(self, v) self.__shown = not not v end end
		if k == "IsShown" or k == "IsVisible" then return function(self) return self.__shown end end
		if k == "GetPoint" then return function() return "CENTER", nil, "CENTER", 0, 0 end end
		if k == "GetID" then return function() return 7 end end
		if k == "GetName" then return function(self) return rawget(self, "__name") end end
		if k == "GetObjectType" then return function(self) return self.__kind end end
		if k == "GetText" then return function(self) return rawget(self, "__text") end end
		if k == "SetText" or k == "SetFormattedText" then
			return function(self, fmt, ...)
				if select("#", ...) > 0 then self.__text = string.format(fmt, ...) else self.__text = fmt end
			end
		end
		if k == "GetScale" then return function() return 1 end end
		return function() return stub(k) end
	end })
end
local before = {}
for k in pairs(_G) do before[k] = true end

local env = {
	GetBuildInfo = function() return flavor.version, flavor.build, "Oct 16 2026", flavor.interface end,
	WOW_PROJECT_MAINLINE = 1, WOW_PROJECT_CLASSIC = 2,
	WOW_PROJECT_ID = flavor.project,
	WOW_PROJECT_CAMELOT = (flavor.project == 18) and 18 or nil,
	GetLocale = function() return locale end,
	InCombatLockdown = function() return inCombat end,
	IsMacClient = function() return true end,
	IsWindowsClient = function() return false end,
	IsLinuxClient = function() return false end,
	strtrim = function(s) return (s:gsub("^%s+", ""):gsub("%s+$", "")) end,
	strsplit = function(sep, s) local t = {} for p in (s .. sep):gmatch("(.-)%" .. sep) do t[#t + 1] = p end return unpack(t) end,
	tinsert = table.insert, tremove = table.remove, wipe = function(t) for k in pairs(t) do t[k] = nil end return t end,
	format = string.format,
	UnitName = function() return "Aelinor", nil end,
	UnitClass = function() return "Mage", "MAGE", 8 end,
	UnitGUID = function() return "Player-0000-00000001" end,
	print = function(...)
		local parts = {}
		for i = 1, select("#", ...) do parts[#parts + 1] = tostring((select(i, ...))) end
		printed[#printed + 1] = table.concat(parts, " ")
		say("chat: " .. printed[#printed])
	end,
	C_AddOns = {
		GetAddOnMetadata = function(name, key)
			assert(name == addonName or name == 1, "GetAddOnMetadata for another addon: " .. tostring(name))
			if key == "Version" and meta.Version == "@project-version@" then return "v0.0.0-dev" end
			return meta[key]
		end,
		IsAddOnLoaded = function() return true end,
	},
	C_ChatInfo = { RegisterAddonMessagePrefix = function() return 0 end, IsAddonMessagePrefixRegistered = function() return false end },
	C_Texture = { GetAtlasInfo = function() return { width = 32, height = 32 } end },
	C_ClassColor = { GetClassColor = function() return { WrapTextInColorCode = function(_, s) return s end } end },
	C_SettingsUtil = { OpenSettingsPanel = function(id) opened[#opened + 1] = id end },
	Enum = {},
	BACKDROP_DIALOG_32_32 = {},
	MinimalSliderWithSteppersMixin = { Label = { Left = 0, Right = 1, Top = 2, Min = 3, Max = 4 } },
	SlashCmdList = {},
	UIParent = stub("UIParent"),
	GameTooltip = stub("GameTooltip"),
	CreateFrame = function(kind, name, parent)
		local f = stub(kind)
		f.__name, f.__parent = name, parent
		frames[#frames + 1] = f
		if name then
			_G[name] = f
			frameNames[name] = true
		end
		return f
	end,
}
if flavor.secrets then env.issecretvalue = function() return false end end
if flavor.compartment then env.AddonCompartmentFrame = stub("AddonCompartmentFrame") end
local settingsCategories = 0
env.Settings = {
	VarType = { Boolean = "boolean", Number = "number", String = "string" },
	RegisterVerticalLayoutCategory = function(name)
		local c = stub("category"); c.__name = name; return c
	end,
	RegisterAddOnSetting = function(_, variable, key, tbl)
		assert(type(variable) == "string" and type(key) == "string" and type(tbl) == "table", "RegisterAddOnSetting(category, variable, key, table, ...)")
		local s = stub("setting")
		s.SetValueChangedCallback = function(self, cb) self.cb = cb end
		s.SetValue = function(self, v) tbl[key] = v; if self.cb then self.cb(self, v) end end
		s.GetValue = function() return tbl[key] end
		return s
	end,
	CreateCheckbox = function() end,
	CreateSliderOptions = function() return stub("sliderOptions") end,
	CreateSlider = function() end,
	RegisterAddOnCategory = function() settingsCategories = settingsCategories + 1 end,
	OpenToCategory = function(id) assert(type(id) == "number", "Settings.OpenToCategory needs the numeric category ID"); opened[#opened + 1] = id end,
}
for k, v in pairs(env) do _G[k] = v end

-- What the addon may create: .luacheckrc's "globals", the TOC's SavedVariables and compartment
-- functions, SLASH_ strings and the libraries' own globals (LibStub).
local allowed = { LibStub = true, SlashCmdList = true }
local rcText = readFile(addonDir .. "/.luacheckrc") or readFile(HERE .. "/../../.luacheckrc")
if rcText then
	local rcEnv = {}
	local chunk = loadstring(rcText)
	if chunk then
		setfenv(chunk, rcEnv)
		pcall(chunk)
		for _, g in ipairs(type(rcEnv.globals) == "table" and rcEnv.globals or {}) do allowed[g] = true end
	end
end
local savedVariables = {}
for _, field in ipairs({ "SavedVariables", "SavedVariablesPerCharacter" }) do
	for name in (meta[field] or ""):gmatch("[^,%s]+") do allowed[name] = true; savedVariables[#savedVariables + 1] = name end
end
for _, field in ipairs({ "AddonCompartmentFunc", "AddonCompartmentFuncOnEnter", "AddonCompartmentFuncOnLeave" }) do
	if meta[field] then allowed[meta[field]] = true end
end

---------------------------------------------------------------------------
-- Load the files in TOC order
---------------------------------------------------------------------------
local ns = {}
local loadedOK = true
for _, f in ipairs(files) do
	if f.load then
		local chunk, err = loadfile(addonDir .. "/" .. f.path)
		if not chunk then
			loadedOK = check("file listed in the TOC loads: " .. f.path, false, err) and loadedOK
		else
			loadedOK = protect("run " .. f.path, chunk, addonName, ns) and loadedOK
		end
	end
end
check("every file in the TOC ran without error", loadedOK)
if not loadedOK then finish() end

local function fire(event, ...)
	for _, fr in ipairs(frames) do
		local h = fr.__scripts.OnEvent
		if h and fr.__events[event] then protect("event " .. event .. " on " .. tostring(rawget(fr, "__name") or fr.__kind), h, fr, event, ...) end
	end
end

-- Is the addon meant to run on this client? (the template's SUPPORTED_FLAVORS guard)
local supported
do
	local src = ""
	for _, f in ipairs(files) do src = src .. (readFile(addonDir .. "/" .. f.path) or "") .. "\n" end
	local body = src:gsub("%-%-[^\n]*", ""):match("SUPPORTED_FLAVORS%s*=%s*(%b{})")
	if body then
		supported = false
		for name in body:gmatch("([%a_]+)%s*=%s*true") do
			if name == flavor.libtx then supported = true end
		end
		say("SUPPORTED_FLAVORS " .. body:gsub("%s+", " ") .. " -> " .. (supported and "active" or "inactive") .. " on " .. flavorKey)
	end
end
-- The TOC lists this client's number, so the client loads the addon as up to date: it must not
-- then sit there inactive (a flavor added to ## Interface but not to SUPPORTED_FLAVORS).
if supported == false and interfaces[flavor.interface] then
	check("SUPPORTED_FLAVORS includes " .. flavor.libtx .. " (## Interface lists " .. flavor.interface .. ")", false,
		"the client loads the addon and it stays inactive; add " .. flavor.libtx .. " = true to SUPPORTED_FLAVORS or remove the number")
end

fire("ADDON_LOADED", "Blizzard_SomeOtherAddon")
fire("ADDON_LOADED", addonName)
if supported ~= false then
	for _, sv in ipairs(savedVariables) do
		check("SavedVariables " .. sv .. " is a table after ADDON_LOADED", type(_G[sv]) == "table", type(_G[sv]))
	end
end
local mark = #printed
fire("PLAYER_LOGIN")
if supported == false then
	local notice = false
	for i = mark + 1, #printed do notice = notice or printed[i]:find(flavor.libtx, 1, true) ~= nil end
	check("inactive on " .. flavorKey .. " (not in SUPPORTED_FLAVORS): prints its notice at login", notice, printed[#printed])
	for _, sv in ipairs(savedVariables) do
		check("inactive: " .. sv .. " untouched", _G[sv] == nil, type(_G[sv]))
	end
end

-- Globals created at load and login. A named frame (CreateFrame("Frame", name)) is a global too;
-- its name must start with the addon's name, like every other global the addon creates.
local ident = addonName:gsub("_", "")
local function ownName(k)
	return k:sub(1, #addonName) == addonName or k:sub(1, #ident) == ident
end
local leaked = {}
for k in pairs(_G) do
	if not before[k] and env[k] == nil and not allowed[k] and not tostring(k):match("^SLASH_") then
		if not (frameNames[k] and ownName(tostring(k))) then
			leaked[#leaked + 1] = tostring(k) .. (frameNames[k] and " (frame name)" or "")
		end
	end
end
table.sort(leaked)
check("no global outside .luacheckrc's list, the TOC's SavedVariables, SLASH_ strings and frames named after the addon",
	#leaked == 0, table.concat(leaked, ", "))

---------------------------------------------------------------------------
-- Slash commands, compartment, combat queue
---------------------------------------------------------------------------
local ours = {}
for k in pairs(_G) do
	local key = tostring(k):match("^SLASH_(.-)%d+$")
	if key and not before[k] then
		if check(k .. " has its handler SlashCmdList." .. key, type(SlashCmdList[key]) == "function") then ours[key] = true end
	end
end
local subs = { "", "help", "version" }
for extra in (os.getenv("SMOKE_SLASH") or ""):gmatch("[^,%s]+") do subs[#subs + 1] = extra end
for key in pairs(ours) do
	for _, sub in ipairs(subs) do
		protect("slash /" .. key:lower() .. " " .. sub, SlashCmdList[key], sub, nil)
	end
end
if flavor.compartment and supported ~= false then
	for _, field in ipairs({ "AddonCompartmentFunc", "AddonCompartmentFuncOnEnter", "AddonCompartmentFuncOnLeave" }) do
		local name = meta[field]
		if name then
			if check("compartment function " .. name .. " exists", type(_G[name]) == "function") then
				protect("compartment " .. name .. "()", _G[name], addonName, field == "AddonCompartmentFunc" and "LeftButton" or stub("button"))
			end
		end
	end
end

if os.getenv("SMOKE_COMBAT") and supported ~= false then
	local sub = os.getenv("SMOKE_COMBAT")
	inCombat = true
	local n = #opened
	for key in pairs(ours) do protect("in combat: /" .. key:lower() .. " " .. sub, SlashCmdList[key], sub, nil) end
	check("in combat: settings not opened yet", #opened == n)
	inCombat = false
	fire("PLAYER_REGEN_ENABLED")
	check("after combat: the queued action ran once", #opened == n + 1, #opened - n)
end

finish()
