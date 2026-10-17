-- luacheck configuration (https://github.com/lunarmodules/luacheck). Run: luacheck .
--
-- WoW runs Lua 5.1. Every global the addon writes or reads is listed below, so luacheck flags
-- a new global (W111) or a misspelled API name (W113). Team rule: a global the addon creates
-- must start with the addon's name (TxExample..., SLASH_TXEXAMPLE...). Prefer the private
-- addon table (local addonName, ns = ...) for everything else.
std = "lua51"
max_line_length = 140
ignore = {
	"212/self", -- methods declared with ":" do not always use self
}
exclude_files = {
	".release/", -- packager output
	"Libs/", -- fetched by the packager; linted in their own repositories
	".lua/", -- Lua and LuaRocks installed into the workspace by CI
	".lua-build/",
	".luarocks/",
	"patchwatch/", -- only if patchwatch is vendored (not recommended; patchwatch/README.md)
}

-- The smoke harness is plain Lua 5.1 test code (never packaged): long lines are fine there.
files["tests/harness/"] = { max_line_length = false }

-- Globals this addon creates or writes.
globals = {
	"TxExampleDB", -- ## SavedVariables
	"SLASH_TXEXAMPLE1",
	"SlashCmdList", -- we add SlashCmdList.TXEXAMPLE
}

-- WoW API this addon reads. Add each new API here when you start using it.
read_globals = {
	"C_AddOns",
	"CreateFrame",
	"LibStub",
	"strtrim",
}
