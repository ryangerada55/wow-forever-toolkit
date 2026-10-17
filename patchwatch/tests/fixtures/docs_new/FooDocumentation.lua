local Foo =
{
	Name = "Foo",
	Type = "System",
	Namespace = "C_Foo",
	Environment = "All",

	Functions =
	{
		{
			Name = "ChangedArgs",
			Type = "Function",
			SecretArguments = "AllowedWhenUntainted",

			Arguments =
			{
				{ Name = "id", Type = "number", Nilable = false },
				{ Name = "mode", Type = "number", Nilable = false },
			},
		},
		{
			Name = "GetThing",
			Type = "Function",
			SecretArguments = "AllowedWhenTainted",
			Documentation = { "Returns a thing; uses 'quotes' and \"escapes\"." },

			Arguments =
			{
				{ Name = "id", Type = "number", Nilable = false },
			},

			Returns =
			{
				{ Name = "name", Type = "string", Nilable = true },
			},
		},
		{
			Name = "RemovedThingV2",
			Type = "Function",
		},
		{
			Name = "StatFunc",
			Type = "Function",
			SecretWhenFooRestricted = true,

			Returns =
			{
				{ Name = "value", Type = "number", Nilable = false },
			},
		},
	},

	Events =
	{
		{
			Name = "FooAdded",
			Type = "Event",
			LiteralName = "FOO_ADDED",
			SynchronousEvent = true,
		},
		{
			Name = "FooUpdated",
			Type = "Event",
			LiteralName = "FOO_UPDATED",
			Payload =
			{
				{ Name = "id", Type = "number", Nilable = false, ConditionalSecret = true },
			},
		},
	},

	Tables =
	{
		{
			Name = "FooType",
			Type = "Enumeration",
			NumValues = 2,
			MinValue = 0,
			MaxValue = 1,
			Fields =
			{
				{ Name = "A", Type = "FooType", EnumValue = 0 },
				{ Name = "B", Type = "FooType", EnumValue = 1 },
			},
		},
		{
			Name = "FooInfo",
			Type = "Structure",
			Fields =
			{
				{ Name = "id", Type = "number", Nilable = false, Default = -1 },
				{ Name = "flags", Type = "number", Nilable = false, Default = Enum.FooType.A + Enum.FooType.B },
				{ Name = "text", Type = "cstring", Nilable = true, Default = [[long
string]] },
			},
		},
	},

	Predicates =
	{
		{
			Name = "SecretWhenFooRestricted",
			Type = "Secret",
		},
	},
};

APIDocumentation:AddDocumentationTable(Foo);
