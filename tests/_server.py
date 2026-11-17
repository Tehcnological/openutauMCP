"""How the tests start the server: as an MCP client would, with the SDK's default environment."""

import glob
import os
import sys

from mcp import StdioServerParameters
from mcp.client.stdio import get_default_environment

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PKG = os.path.basename(glob.glob(os.path.join(ROOT, "src", "*_mcp"))[0])
PREFIX = PKG.split("_")[0].upper()  # the server's own settings (VOCALOID6_*, OPENUTAU_*) are passed on


def server_params(exe: str | None = None) -> StdioServerParameters:
    """exe (else MCP_SERVER_EXE) is a server command such as the single-file build; without one, this checkout."""
    exe = exe or os.environ.get("MCP_SERVER_EXE")
    env = {**get_default_environment(), "PYTHONIOENCODING": "utf-8",  # what MCP clients pass by default
           **{k: v for k, v in os.environ.items() if k.upper().startswith(PREFIX)}}
    if exe:
        return StdioServerParameters(command=os.path.abspath(exe), env=env)
    return StdioServerParameters(command=sys.executable, args=["-m", f"{PKG}.server"], env=env)
