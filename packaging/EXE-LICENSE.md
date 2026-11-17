# License of the single-file exe

`openutau-mcp.exe` is built from this repository (MIT, see `LICENSE`) together with the Python packages listed in
`openutau-mcp-packages.txt`. One of them, pykakasi, is licensed under the GNU General Public License, version 3 or
later. Because pykakasi is inside the exe, the exe as a whole is distributed under GPL-3.0-or-later. The full
text is in `GPL-3.0.txt`, attached to the same release.

Source code:

- This project: https://github.com/Tehcnological/openutauMCP. The release tag is the exact source, and
  `packaging/build.ps1` builds the exe.
- pykakasi: https://codeberg.org/miurahr/pykakasi
- Every other bundled package: the versions in `openutau-mcp-packages.txt`, from https://pypi.org, each under its
  own license.

The source in this repository stays MIT. Running it from source without the `kanji` extra does not include
pykakasi.
