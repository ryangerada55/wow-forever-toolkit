if not GetCVarBool("loadDeprecationFallbacks") then
	return;
end

C_Foo.RemovedThing = function() return C_Foo.RemovedThingV2(); end
