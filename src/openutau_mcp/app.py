"""Find, launch and close the OpenUtau desktop app."""

import os
import subprocess
import time

import psutil

from . import bridge
from .errors import OpenUtauError


def find_exe() -> str | None:
    candidates = [os.environ.get("OPENUTAU_EXE")]
    for base in (os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)"), os.environ.get("LOCALAPPDATA")):
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
        info["hint"] = (
            "OpenUtau is running but the bridge is not answering: copy OpenUtauMcp.Plugin.dll into "
            "Documents\\OpenUtau\\Plugins\\OpenUtauMcp\\ and restart OpenUtau (plugins load only at startup). / "
            "OpenUtau は起動していますがブリッジが応答しません。OpenUtauMcp.Plugin.dll を "
            "Documents\\OpenUtau\\Plugins\\OpenUtauMcp\\ に置き、OpenUtau を再起動してください。"
        )
    return info


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
    args = [exe] + ([project_path] if project_path else [])
    subprocess.Popen(args, cwd=os.path.dirname(exe), close_fds=True,
                     creationflags=getattr(subprocess, "DETACHED_PROCESS", 0))
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
