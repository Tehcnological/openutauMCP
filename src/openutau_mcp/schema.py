"""Tool input schemas that strict MCP clients accept (Gemini, Codex, VS Code, Cursor).

pydantic's schemas use $ref/$defs, anyOf-with-null for optional fields and anyOf unions, which some clients reject
or flatten to strings. Only the advertised schema is simplified: arguments are still validated by the same pydantic
models, so every tool accepts exactly what it accepted before (e.g. a pitch as 60 or "60" or "C4").
"""

from mcp.server import fastmcp


def simplify(schema: dict) -> dict:
    """Inline $ref, drop titles, express optional fields as plain types and collapse unions."""
    defs = schema.get("$defs", {})

    def node(s: dict, omittable: bool = False, seen: tuple = ()) -> dict:
        if len(s.get("allOf", ())) == 1:  # a $ref wrapped in allOf (older pydantic, or a ref with siblings)
            s = {**s["allOf"][0], **{k: v for k, v in s.items() if k != "allOf"}}
        if "$ref" in s:
            name = s["$ref"].rsplit("/", 1)[1]
            if name in seen:  # a model that contains itself: stop at a plain object
                return {"type": "object", **{k: v for k, v in s.items() if k == "description"}}
            seen += (name,)
            s = {**defs[name], **{k: v for k, v in s.items() if k != "$ref"}}
        s = {k: v for k, v in s.items() if k not in ("title", "$defs")}
        if "anyOf" in s:
            branches = [node(b, seen=seen) for b in s.pop("anyOf")]
            typed = [b for b in branches if b.get("type") != "null"]
            one = _collapse(typed)
            if len(typed) < len(branches) and not omittable:
                s["anyOf"] = [one, {"type": "null"}]  # null means something here (required value or list item)
            else:
                s = {**one, **s}  # an omittable field just leaves null out
            if s.get("default") is None or len(typed) > 1:
                s.pop("default", None)
        if isinstance(s.get("additionalProperties"), dict):
            del s["additionalProperties"]  # dict[str, X]: an open object; the description lists the keys
        if "properties" in s:
            req = s.get("required", [])
            s["properties"] = {k: node(v, k not in req, seen) for k, v in s["properties"].items()}
        if isinstance(s.get("items"), dict):
            s["items"] = node(s["items"], seen=seen)
        return s

    return node(schema)


def _collapse(branches: list[dict]) -> dict:
    """One schema for a union: the list form if there is one (a single value is still accepted), else an object
    branch, else the widest scalar (string > number > integer > boolean)."""
    if len(branches) == 1:
        return branches[0]
    for t in ("array", "object"):
        for b in branches:
            if b.get("type") == t:
                return b
    types = {b.get("type") for b in branches}
    return {"type": next((t for t in ("string", "number", "integer") if t in types), "boolean")}


class FastMCP(fastmcp.FastMCP):
    """FastMCP whose tools/list advertises simplified input schemas."""

    async def list_tools(self):
        tools = await super().list_tools()
        cache = self.__dict__.setdefault("_simplified", {})  # tools are fixed after startup: simplify each once
        for t in tools:
            if t.name not in cache:
                cache[t.name] = simplify(t.inputSchema)
            t.inputSchema = cache[t.name]
        return tools
