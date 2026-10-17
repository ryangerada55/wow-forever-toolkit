-- These are functions that were deprecated and will be removed in the future.
if not GetCVarBool("loadDeprecationFallbacks") then
	return;
end

do
	GetOldFoo = function(id)
		return C_Foo.GetThing(id);
	end
	local helper = {};
	helper.notGlobal = 1;
end

C_Foo.OldAlias = C_Foo.GetThing;
