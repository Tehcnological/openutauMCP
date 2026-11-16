"""Entry point of the single-file build (packaging/build.ps1)."""

import os
import sys

from openutau_mcp.server import main

try:
    main()
finally:
    # the onefile bootloader flushes stdout at exit, after the MCP transport closed it
    sys.stdout = sys.__stdout__ = open(os.devnull, "w")
