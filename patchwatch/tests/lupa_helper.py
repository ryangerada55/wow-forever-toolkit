"""Load documentation files with a real Lua 5.1 runtime (lupa) for cross-checking.

Unknown globals (Enum, Constants, NUM_BAG_SLOTS, ...) resolve to proxy
objects that remember their dotted path, so ``Enum.A.B + Enum.A.C`` becomes
the string ``"Enum.A.B + Enum.A.C"`` - the same text patchwatch's parser
keeps for unevaluated expressions.
"""
from __future__ import annotations

from typing import Any, Dict, List

_BOOT = r"""
local proxymt = {}
local function proxy(path) return setmetatable({__path = path}, proxymt) end
proxymt.__index = function(t, k) return proxy(rawget(t, "__path") .. "." .. tostring(k)) end
local function txt(v)
  if type(v) == "table" and getmetatable(v) == proxymt then return rawget(v, "__path") end
  return tostring(v)
end
for _, op in ipairs({"add", "sub", "mul", "div"}) do
  local sym = ({add = "+", sub = "-", mul = "*", div = "/"})[op]
  proxymt["__" .. op] = function(a, b) return proxy(txt(a) .. " " .. sym .. " " .. txt(b)) end
end
proxymt.__unm = function(a) return proxy("-" .. txt(a)) end
REGISTERED = {}
APIDocumentation = { AddDocumentationTable = function(self, t) table.insert(REGISTERED, t) end }
setmetatable(_G, { __index = function(t, k) return proxy(k) end })
function PW_PROXYPATH(v)
  if type(v) == "table" and getmetatable(v) == proxymt then return rawget(v, "__path") end
  return nil
end
"""


def lua_load_file(src: str) -> List[Any]:
    import lupa.lua51 as lupa  # type: ignore

    rt = lupa.LuaRuntime(unpack_returned_tuples=True)
    rt.execute(_BOOT)
    rt.execute(src)
    g = rt.globals()
    proxypath = g.PW_PROXYPATH
    lua_type = rt.eval("type")

    def conv(v: Any) -> Any:
        if lua_type(v) == "table":
            path = proxypath(v)
            if path is not None:
                return str(path)
            keys = list(v.keys())
            if not keys:
                return []
            if all(isinstance(k, int) for k in keys) and sorted(keys) == list(range(1, len(keys) + 1)):
                return [conv(v[k]) for k in range(1, len(keys) + 1)]
            out: Dict[Any, Any] = {}
            for k in keys:
                out[k] = conv(v[k])
            return out
        return v

    reg = g.REGISTERED
    return [conv(reg[i]) for i in range(1, len(reg) + 1)]


def normalise(v: Any) -> Any:
    """Make patchwatch parser output comparable (Expr -> str, float ints -> int)."""
    if isinstance(v, dict):
        return {k: normalise(x) for k, x in v.items()}
    if isinstance(v, list):
        return [normalise(x) for x in v]
    if isinstance(v, float) and v.is_integer():
        return int(v)
    if isinstance(v, str):
        return str(v)
    return v
