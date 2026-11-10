"""Voicebank discovery and oto.ini parsing, mirroring OpenUtau's VoicebankLoader."""

import json
import os
import re

import yaml

from .errors import OpenUtauError


def data_dir() -> str:
    return os.environ.get("OPENUTAU_DATA_DIR") or os.path.join(os.path.expanduser("~"), "Documents", "OpenUtau")


def prefs() -> dict:
    try:
        with open(os.path.join(data_dir(), "prefs.json"), encoding="utf-8-sig") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def singer_roots() -> list[str]:
    roots = [os.path.join(data_dir(), "Singers")]
    extra = prefs().get("AdditionalSingerPath")
    if extra:
        roots.append(extra)
    return [r for r in roots if os.path.isdir(r)]


def _read_text(path: str, encoding: str) -> str:
    with open(path, "rb") as f:
        raw = f.read()
    try:
        return raw.decode(encoding)
    except (LookupError, UnicodeDecodeError):
        return raw.decode("utf-8", "replace")


def _info(char_txt: str, root: str) -> dict:
    folder = os.path.dirname(char_txt)
    cfg = {}
    yml = os.path.join(folder, "character.yaml")
    if os.path.isfile(yml):
        try:
            with open(yml, encoding="utf-8-sig") as f:
                cfg = yaml.safe_load(f) or {}
        except (OSError, yaml.YAMLError):
            cfg = {}
    encoding = cfg.get("text_file_encoding") or "shift_jis"
    txt = {}
    for line in _read_text(char_txt, encoding).splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            txt[k.strip().lower()] = v.strip()
    name = cfg.get("name") or txt.get("name") or f"No Name ({os.path.relpath(folder, root)})"
    return {
        "id": os.path.relpath(folder, root),  # same as OpenUtau: path relative to the singers root
        "name": name,
        "author": cfg.get("author") or txt.get("author") or txt.get("created by"),
        "default_phonemizer": cfg.get("default_phonemizer"),
        "singer_type": cfg.get("singer_type") or "utau",
        "text_file_encoding": encoding,
        "path": folder,
    }


def list_voicebanks() -> list[dict]:
    deep = prefs().get("LoadDeepFolderSinger", True)
    banks = []
    for root in singer_roots():
        if deep:
            for dirpath, _dirs, files in os.walk(root):
                if "character.txt" in files:
                    banks.append(_info(os.path.join(dirpath, "character.txt"), root))
        else:
            for d in sorted(os.listdir(root)):
                f = os.path.join(root, d, "character.txt")
                if os.path.isfile(f):
                    banks.append(_info(f, root))
    return sorted(banks, key=lambda b: b["id"])


_JA_DEFAULT = "OpenUtau.Plugin.Builtin.JapanesePresampPhonemizer"
_EN_CHOICES = ("EN ARPA (ArpasingPhonemizer)", "EN VCCV (EnglishVCCVPhonemizer)", "EN X-SAMPA (EnXSampaPhonemizer)")


def suggest_phonemizer(bank: dict) -> dict:
    """Best phonemizer guess for a voicebank: its character.yaml default, else the one the user last picked for it
    in OpenUtau (prefs.json SingerPhonemizers), else Japanese if its oto aliases are kana."""
    if bank.get("default_phonemizer"):
        return {"phonemizer": bank["default_phonemizer"], "source": "character.yaml"}
    used = (prefs().get("SingerPhonemizers") or {}).get(bank["id"])
    if used:
        return {"phonemizer": used, "source": "last used in OpenUtau / OpenUtau で前回使用"}
    try:
        aliases = [e["alias"] for e in otos(bank)[:500]]
    except Exception:  # noqa: BLE001 - unreadable oto: no suggestion
        aliases = []
    if aliases and sum(any("぀" <= c <= "ヿ" for c in a) for a in aliases) > len(aliases) / 2:
        return {"phonemizer": _JA_DEFAULT, "source": "kana aliases / かなエイリアス"}
    return {"phonemizer": None, "source": None,
            "hint": "Probably English: try " + ", ".join(_EN_CHOICES) + " and keep the one where list_phonemes shows "
                    "has_oto=true most often. / 英語音源と思われます。各候補を試し、list_phonemes の has_oto=true が"
                    "最も多いものを選んでください。"}


def find_voicebank(query: str) -> dict:
    banks = list_voicebanks()
    q = query.lower()
    for key in ("id", "name"):
        for b in banks:
            if (b[key] or "").lower() == q:
                return b
    for b in banks:
        if q in b["id"].lower() or q in (b["name"] or "").lower():
            return b
    raise OpenUtauError(f"Voicebank '{query}' not found; use list_voicebanks", f"音源 '{query}' が見つかりません。list_voicebanks で確認してください")


def parse_oto(path: str, encoding: str = "shift_jis") -> list[dict]:
    with open(path, "rb") as f:
        raw = f.read()
    for line in raw.splitlines()[:10]:
        m = re.match(rb"\s*#Charset:(\S+)", line)
        if m:
            encoding = m.group(1).decode("ascii", "replace")
            break
    entries = []
    for line in _read_text(path, encoding).splitlines():
        line = line.strip()
        if "=" not in line or line.startswith("#"):
            continue
        wav, rest = line.split("=", 1)
        f = rest.split(",")
        alias = f[0] if f and f[0] else os.path.splitext(wav.strip())[0]
        nums = []
        for x in f[1:6]:
            try:
                nums.append(float(x))
            except ValueError:
                nums.append(None)
        nums += [None] * (5 - len(nums))
        entries.append({"alias": alias, "wav": wav.strip(), "offset": nums[0], "consonant": nums[1],
                        "cutoff": nums[2], "preutter": nums[3], "overlap": nums[4]})
    return entries


def otos(bank: dict) -> list[dict]:
    """All oto entries of a voicebank, each tagged with its subfolder ("set")."""
    result = []
    for dirpath, _dirs, files in os.walk(bank["path"]):
        if "oto.ini" in files:
            rel = os.path.relpath(dirpath, bank["path"])
            for e in parse_oto(os.path.join(dirpath, "oto.ini"), bank["text_file_encoding"]):
                e["set"] = "" if rel == "." else rel
                result.append(e)
    return result
