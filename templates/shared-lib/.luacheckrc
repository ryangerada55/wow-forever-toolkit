-- luacheck configuration for LibTx-1.0. Run: luacheck .
std = "lua51"
max_line_length = 140
ignore = {
	"212/self", -- methods declared with ":" do not always use self
}
exclude_files = {
	"LibStub/", -- third-party (public domain), kept byte-identical to the upstream copy
	".lua/",
	".lua-build/",
	".luarocks/",
}
globals = {
	"LibStub", -- read, and created by LibStub.lua when no copy is loaded yet
}
read_globals = {
	"C_ChatInfo",
	"GetBuildInfo",
	"IsLinuxClient",
	"IsMacClient",
	"IsWindowsClient",
	"issecretvalue", -- nil on clients without secret values
	"WOW_PROJECT_CAMELOT", -- Forever only; nil elsewhere
	"WOW_PROJECT_CLASSIC",
	"WOW_PROJECT_ID",
	"WOW_PROJECT_MAINLINE",
}
