"""Checks every tool the server advertises against the strictest documented MCP client rules.

    python tests/schema_check.py                    # the server from this checkout
    python tests/schema_check.py dist\\<name>.exe     # or any stdio server command (also: MCP_SERVER_EXE)

A plain MCP client (the official Python SDK), no Claude involved. Errors fail the run; warnings are printed.
Rules and the clients that need them (researched 2026-11):
  root object with properties ......................... MCP spec, Gemini CLI, VS Code, Codex
  valid JSON Schema draft-07 and 2020-12 .............. VS Code (draft-07 meta-schema), MCP spec (2020-12)
  every property / item has a type, arrays have items . Gemini Schema, VS Code, Codex (else inferred or {})
  no $ref/$defs/title/allOf/oneOf/not/const/if ........ Codex (refs become {}), Gemini (titles misread)
  no type arrays, anyOf only with typed branches ...... Gemini Schema (one type), older Codex
  no anyOf-with-null or default null on optional fields older Codex (flattened to string)
  object depth <= 3 below the root .................... Codex compaction, Gemini nesting limit
  description 1..1024 chars ........................... OpenAI, VS Code
  tool name ^[a-z][a-z0-9_]*$, <= 46 chars, server+tool <= 58: OpenAI, Codex, VS Code (64 - prefix), Cursor (60)
  warnings: compact input schema > 5000 bytes (Codex then strips descriptions); > 40 tools (Cursor's old cap)
"""

import asyncio
import json
import re
import sys

from jsonschema import Draft7Validator, Draft202012Validator
from mcp import ClientSession
from mcp.client.stdio import stdio_client

from _server import server_params

BANNED = {"$ref", "$defs", "definitions", "title", "allOf", "oneOf", "not", "const", "if", "then", "else",
          "prefixItems", "$dynamicRef", "patternProperties"}
TYPES = {"object", "array", "string", "integer", "number", "boolean", "null"}


def check_schema(name: str, schema: dict) -> list[str]:
    errors = []
    for v in (Draft7Validator, Draft202012Validator):
        errors += [f"{name}: not valid {v.__name__}: {e.message}" for e in v(v.META_SCHEMA).iter_errors(schema)]
    if schema.get("type") != "object" or "properties" not in schema:
        errors.append(f"{name}: root must be an object with properties")

    def walk(s, path, depth, omittable):
        if not isinstance(s, dict):
            return
        for k in BANNED & set(s):
            errors.append(f"{path}: banned keyword {k}")
        t = s.get("type")
        if "anyOf" in s:
            for i, b in enumerate(s["anyOf"]):
                if b.get("type") not in TYPES:
                    errors.append(f"{path}.anyOf[{i}]: branch without a type")
                walk(b, f"{path}.anyOf[{i}]", depth, False)
            if omittable and any(b.get("type") == "null" for b in s["anyOf"]):
                errors.append(f"{path}: optional field uses anyOf with null (leave it out of required instead)")
        elif not isinstance(t, str) or t not in TYPES:
            errors.append(f"{path}: needs a single type, got {t!r}")
        if omittable and "default" in s and s["default"] is None:
            errors.append(f"{path}: default null")
        if "enum" in s and not all(isinstance(e, str) for e in s["enum"]):
            errors.append(f"{path}: enum values must be strings")
        if t == "array":
            if not isinstance(s.get("items"), dict):
                errors.append(f"{path}: array without items")
            walk(s.get("items"), f"{path}[]", depth, False)
        if t == "object" or "properties" in s:
            if depth > 3:
                errors.append(f"{path}: objects nested deeper than 3 levels")
            req = set(s.get("required", []))
            for p, v in (s.get("properties") or {}).items():
                walk(v, f"{path}.{p}", depth + 1, p not in req)

    walk(schema, name, 0, False)
    return errors


def check_tools(server: str, tools: list) -> tuple[list[str], list[str]]:
    errors, warnings = [], []
    if len(tools) > 40:
        warnings.append(f"{len(tools)} tools: Cursor used to send only the first 40; users can disable unused tools")
    for t in tools:
        if not re.fullmatch(r"[a-z][a-z0-9_]*", t.name) or len(t.name) > 46 or len(server) + len(t.name) > 58:
            errors.append(f"{t.name}: tool name breaks the portable name rules")
        if not 1 <= len(t.description or "") <= 1024:
            errors.append(f"{t.name}: description must be 1..1024 characters (is {len(t.description or '')})")
        errors += check_schema(t.name, t.inputSchema)
        if getattr(t, "outputSchema", None):
            errors += check_schema(f"{t.name} (output)", t.outputSchema)
        size = len(json.dumps(t.inputSchema, ensure_ascii=False, separators=(",", ":")).encode())
        if size > 5000:
            warnings.append(f"{t.name}: input schema is {size} bytes; Codex strips its descriptions (> 5000)")
    return errors, warnings


async def main():
    params = server_params(sys.argv[1] if sys.argv[1:] else None)
    async with stdio_client(params) as (r, w), ClientSession(r, w) as s:
        init = await s.initialize()
        tools = (await s.list_tools()).tools
    server = init.serverInfo.name
    errors, warnings = check_tools(server, tools)
    if not re.fullmatch(r"[a-z0-9]+", server):
        errors.append(f"server name {server!r}: use [a-z0-9] only (Gemini CLI splits names on _)")
    for w in warnings:
        print("warn ", w)
    for e in errors:
        print("ERROR", e)
    print(f"{server}: {len(tools)} tools, instructions {len(init.instructions or '')} chars, "
          f"{len(errors)} errors, {len(warnings)} warnings")
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    asyncio.run(main())
