-- a global (no Namespace) system and a widget (ScriptObject) system
local UnitFoo =
{
	Name = "UnitFoo",
	Type = "System",

	Functions =
	{
		{
			Name = "UnitFoo",
			Type = "Function",
			SecretArguments = "AllowedWhenUntainted",

			Arguments =
			{
				{ Name = "unit", Type = "UnitToken", Nilable = false },
			},

			Returns =
			{
				{ Name = "result", Type = "number", Nilable = false },
			},
		},
	},

	Events = {},
	Tables = {},
};

local FooFrameAPI =
{
	Name = "FooFrameAPI",
	Type = "ScriptObject",

	Functions =
	{
		{
			Name = "SetScript",
			Type = "Function",
			SecretArguments = "NotAllowed",

			Arguments =
			{
				{ Name = "scriptTypeName", Type = "cstring", Nilable = false },
				{ Name = "script", Type = "LuaFunctionReference", Nilable = true },
			},
		},
	},
};

APIDocumentation:AddDocumentationTable(UnitFoo);
APIDocumentation:AddDocumentationTable(FooFrameAPI);
