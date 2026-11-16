"""Find, launch and close the OpenUtau desktop app."""

import os
import subprocess
import time

import psutil

from . import bridge, voicebanks
from .errors import OpenUtauError


def find_exe() -> str | None:
    candidates = [os.environ.get("OPENUTAU_EXE")]
    # MCP clients often start servers with a short env whitelist that has no ProgramFiles (but has SystemDrive)
    drive = os.environ.get("SystemDrive", "C:") + os.sep
    for base in (os.environ.get("ProgramFiles") or os.path.join(drive, "Program Files"),
                 os.environ.get("ProgramFiles(x86)") or os.path.join(drive, "Program Files (x86)"),
                 os.environ.get("LOCALAPPDATA")):
        if base:
            candidates.append(os.path.join(base, "OpenUtau", "OpenUtau.exe"))
            candidates.append(os.path.join(base, "Programs", "OpenUtau", "OpenUtau.exe"))
    return next((c for c in candidates if c and os.path.isfile(c)), None)


def processes() -> list[psutil.Process]:
    found = []
    for p in psutil.process_iter(["name"]):
        if (p.info.get("name") or "").lower() in ("openutau.exe", "openutau"):
            found.append(p)
    return found


def status() -> dict:
    procs = processes()
    up = bridge.reachable()
    info = {"running": bool(procs), "pids": [p.pid for p in procs], "bridge": up, "port": bridge.PORT, "exe": find_exe()}
    if up:
        info["hint"] = "Ready. / 準備完了です。"
    elif not procs:
        info["hint"] = ("OpenUtau is not running: call launch_openutau. / "
                        "OpenUtau が起動していません。launch_openutau を実行してください。")
    else:
        plugins = voicebanks.plugins_dir()
        info["hint"] = (
            f"OpenUtau is running but the bridge is not answering: put OpenUtauMcp.Plugin.dll into {plugins} "
            "(single-file build: close OpenUtau and run `openutau-mcp.exe install-plugin`) and restart OpenUtau "
            "(plugins load only at startup). / "
            f"OpenUtau は起動していますがブリッジが応答しません。OpenUtauMcp.Plugin.dll を {plugins} に置き"
            "（1ファイル版は OpenUtau を閉じて `openutau-mcp.exe install-plugin`）、OpenUtau を再起動してください。"
        )
    return info


_SPAWN_PS = """
$a = @{CommandLine = $env:MCP_SPAWN_CMD; CurrentDirectory = $env:MCP_SPAWN_DIR}
if ($env:MCP_SPAWN_HIDE) {
  $a.ProcessStartupInformation = New-CimInstance -ClassName Win32_ProcessStartup -ClientOnly -Property @{ShowWindow = [uint16]0}
}
try { $r = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments $a -ErrorAction Stop } catch { exit 1 }
if ($null -eq $r) { exit 1 }
exit $r.ReturnValue
"""


def spawn(args: list[str], cwd: str, env_prefix: str | None = None) -> None:
    """Start the editor so it outlives this server. Some MCP clients (e.g. the official Python SDK on Windows) run
    the server in a job object that kills every child process when the client disconnects, which would close the
    editor with unsaved work; Windows creates a process started through WMI outside that job. That process gets the
    user's full environment; this server's variables whose names start with env_prefix are added by a hidden cmd
    that then starts the editor (WMI's own environment option would replace the whole environment)."""
    cmd = subprocess.list2cmdline(args)
    # skip values cmd would expand or misquote (% and "); Windows paths cannot contain "
    extra = {k: v for k, v in os.environ.items()
             if env_prefix and k.upper().startswith(env_prefix) and not {'"', "%"} & set(v)}
    wrap = bool(extra) and "%" not in cmd
    if wrap:  # every argument in quotes, so cmd reads & | < > ^ in a path as text
        cmd = ("cmd /c " + " && ".join(f'set "{k}={v}"' for k, v in extra.items())
               + ' && start "" ' + " ".join(f'"{a}"' for a in args))
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", _SPAWN_PS], capture_output=True,
                           env={**os.environ, "MCP_SPAWN_CMD": cmd, "MCP_SPAWN_DIR": cwd,
                                "MCP_SPAWN_HIDE": "1" if wrap else ""},
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), timeout=60)
        if r.returncode == 0:
            return
    except (OSError, subprocess.TimeoutExpired):
        pass
    for _ in range(5):  # a slow WMI call may still have started it: never start a second copy
        if processes():
            return
        time.sleep(1)
    subprocess.Popen(args, cwd=cwd, close_fds=True, creationflags=getattr(subprocess, "DETACHED_PROCESS", 0))


def launch(project_path: str | None = None, wait_seconds: float = 60) -> dict:
    if project_path:
        project_path = os.path.abspath(project_path)
        if not os.path.isfile(project_path):
            raise OpenUtauError(f"File not found: {project_path}", f"ファイルが見つかりません: {project_path}")
    if processes():
        if project_path and bridge.reachable():
            summary = bridge.call("project.open", path=project_path)
            return {"launched": False, "opened": project_path, "summary": summary}
        return {"launched": False, **status()}
    exe = find_exe()
    if not exe:
        raise OpenUtauError(
            "OpenUtau.exe not found; set the OPENUTAU_EXE environment variable",
            "OpenUtau.exe が見つかりません。環境変数 OPENUTAU_EXE を設定してください",
        )
    spawn([exe] + ([project_path] if project_path else []), os.path.dirname(exe), env_prefix="OPENUTAU")
    deadline = time.time() + wait_seconds
    while time.time() < deadline:
        if bridge.reachable():
            break
        time.sleep(1)
    return {"launched": True, **status()}


def close(force: bool = False) -> dict:
    procs = processes()
    if not procs:
        return {"closed": False, "message": "OpenUtau is not running. / OpenUtau は起動していません。"}
    if not force and bridge.reachable():
        summary = bridge.call("project.get")
        if not summary.get("saved"):
            raise OpenUtauError(
                "The project has unsaved changes; save it first or pass force=true",
                "未保存の変更があります。先に保存するか force=true を指定してください",
            )
    for p in procs:
        try:
            if force:
                p.kill()
            elif os.name == "nt":
                # taskkill without /F asks the window to close (like clicking X)
                subprocess.run(["taskkill", "/PID", str(p.pid)], capture_output=True)
            else:
                p.terminate()
        except psutil.Error:
            pass
    gone, alive = psutil.wait_procs(procs, timeout=15)
    if alive:
        return {"closed": False, "still_running": [p.pid for p in alive],
                "hint": "OpenUtau did not close (it may be busy or showing a dialog). Close it in OpenUtau, "
                        "or pass force=true if losing unsaved work is OK. / OpenUtau が閉じませんでした。"
                        "OpenUtau 側で閉じるか、未保存の変更を失ってよければ force=true を指定してください。"}
    return {"closed": True, "pids": [p.pid for p in gone]}
