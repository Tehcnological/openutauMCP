"""HTTP client for the OpenUtau plugin bridge (127.0.0.1 only)."""

import json
import os
import urllib.error
import urllib.request

from .errors import OpenUtauError

HOST = "127.0.0.1"
PORT = int(os.environ.get("OPENUTAU_MCP_PORT", "51128"))


class BridgeUnavailable(OpenUtauError):
    pass


def call(op: str, timeout: float = 60, **args):
    body = json.dumps({k: v for k, v in args.items() if v is not None}, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        f"http://{HOST}:{PORT}/{op}",
        data=body,
        method="POST",
        headers={"Content-Type": "application/json; charset=utf-8", "X-OpenUtau-MCP": "1"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise OpenUtauError(f"Bridge HTTP error {e.code}", f"ブリッジ HTTP エラー {e.code}") from e
    except (urllib.error.URLError, ConnectionError, TimeoutError, OSError) as e:
        raise BridgeUnavailable(
            f"OpenUtau bridge not reachable on {HOST}:{PORT} ({e}). Run openutau_status for how to fix it",
            f"OpenUtau ブリッジ ({HOST}:{PORT}) に接続できません。openutau_status で対処法を確認してください",
        ) from e
    if not data.get("ok"):
        msg = data.get("error", "unknown error")
        raise OpenUtauError(f"OpenUtau: {msg}", f"OpenUtau でエラー: {msg}")
    return data.get("result")


def reachable() -> bool:
    try:
        call("status", timeout=3)
        return True
    except OpenUtauError:
        return False
