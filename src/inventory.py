"""Everything installed on this machine, from every package source, as one list.

Each item is a dict: name, source, bytes, version, explicit (bool), date (ISO day
or ""), deps (int). Sources:

  core, extra, omarchy   pacman packages, by the sync repo that provides them
  aur                    foreign pacman packages (AUR / locally built)
  flatpak, runtime       flatpak apps and runtimes (sizes as flatpak reports them)
  appimage               ~/AppImages/*.AppImage
  omarchy-plugin         ~/.config/omarchy/plugins/*
  hypr-plugin            hyprpm plugins (/var/cache/hyprpm/<user>/*)
  mise                   mise tool installs (tool@version)
  local-bin              executables in ~/.local/bin

Collecting takes a few seconds, so the result is cached in .wip/inventory.json.
`python3 src/inventory.py --refresh` re-reads the system and prints a summary.
"""
import collections
import datetime as dt
import json
import os
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
CACHE = ROOT / ".wip" / "inventory.json"
HOME = pathlib.Path.home()
SOURCES = ["core", "extra", "omarchy", "aur", "flatpak", "runtime", "appimage",
           "omarchy-plugin", "hypr-plugin", "mise", "local-bin"]
UNITS = {"B": 1, "KiB": 1024, "MiB": 1024 ** 2, "GiB": 1024 ** 3, "kB": 1000, "MB": 1000 ** 2, "GB": 1000 ** 3}


def run(*cmd):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, env={**os.environ, "LC_ALL": "C"}).stdout
    except OSError:
        return ""


def du(path):
    total = 0
    for dirpath, _, files in os.walk(path):
        for f in files:
            try:
                total += os.lstat(os.path.join(dirpath, f)).st_size
            except OSError:
                pass
    return total


def size(text):
    m = re.match(r"([\d.]+)\s*(\S+)", text.strip())
    return int(float(m.group(1)) * UNITS.get(m.group(2), 1)) if m else 0


def pacman():
    repo_of = {}
    for repo in ("extra", "core", "omarchy"):                  # later wins: omarchy > core > extra
        for name in run("pacman", "-Slq", repo).split():
            repo_of[name] = repo
    items = []
    for block in run("pacman", "-Qi").split("\n\n"):
        f = dict(re.findall(r"^(\S[^:]*?)\s*: (.*)$", block, re.M))
        if "Name" not in f:
            continue
        deps = [] if f.get("Depends On", "None") == "None" else f["Depends On"].split()
        date = ""
        m = re.search(r"(\w{3}) (\w{3})\s+(\d+) [\d:]+ (\d{4})", f.get("Install Date", ""))
        if m:
            date = dt.datetime.strptime(f"{m.group(2)} {m.group(3)} {m.group(4)}", "%b %d %Y").date().isoformat()
        items.append({"name": f["Name"], "source": repo_of.get(f["Name"], "aur"), "bytes": size(f.get("Installed Size", "0")),
                      "version": f.get("Version", ""), "explicit": "Explicitly" in f.get("Install Reason", ""),
                      "date": date, "deps": len(deps)})
    return items


def flatpaks():
    items = []
    for line in run("flatpak", "list", "--columns=application,version,size,options").splitlines():
        parts = line.split("\t")
        if len(parts) < 4:
            continue
        app, ver, sz, opts = parts[:4]
        items.append({"name": app, "source": "runtime" if "runtime" in opts else "flatpak", "bytes": size(sz),
                      "version": ver, "explicit": "runtime" not in opts, "date": "", "deps": 0})
    return items


def files(source, paths, explicit=True):
    return [{"name": p.name, "source": source, "bytes": du(p) if p.is_dir() else p.stat().st_size,
             "version": "", "explicit": explicit, "date": "", "deps": 0} for p in paths]


def collect():
    items = pacman() + flatpaks()
    items += files("appimage", sorted((HOME / "AppImages").glob("*.AppImage")))
    plug = HOME / ".config" / "omarchy" / "plugins"
    items += files("omarchy-plugin", sorted(p for p in plug.iterdir() if p.is_dir()) if plug.exists() else [])
    hp = pathlib.Path("/var/cache/hyprpm") / os.environ.get("USER", "")
    items += files("hypr-plugin", sorted(p for p in hp.iterdir() if p.is_dir() and p.name != "headersRoot") if hp.exists() else [])
    mise = HOME / ".local" / "share" / "mise" / "installs"
    if mise.exists():
        for tool in sorted(p for p in mise.iterdir() if p.is_dir()):
            for ver in sorted(p for p in tool.iterdir() if p.is_dir() and not p.is_symlink()):
                items.append({"name": f"{tool.name}@{ver.name}", "source": "mise", "bytes": du(ver), "version": ver.name,
                              "explicit": True, "date": "", "deps": 0})
    lb = HOME / ".local" / "bin"
    if lb.exists():
        bins = [p for p in sorted(lb.iterdir()) if p.is_file() and os.access(p, os.X_OK)]
        items += [{"name": p.name, "source": "local-bin", "bytes": p.stat().st_size, "version": "", "explicit": True,
                   "date": "", "deps": 0} for p in bins]
    return items


def load(refresh=False):
    if refresh or not CACHE.exists():
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        CACHE.write_text(json.dumps(collect()))
    return json.loads(CACHE.read_text())


def summary(items):
    by = collections.defaultdict(lambda: [0, 0])
    for it in items:
        by[it["source"]][0] += 1
        by[it["source"]][1] += it["bytes"]
    return {s: tuple(by[s]) for s in SOURCES if s in by}


LABELS = {"core": "core", "extra": "extra", "omarchy": "omarchy repo", "aur": "AUR", "flatpak": "flatpak apps",
          "runtime": "flatpak runtimes", "appimage": "AppImages", "omarchy-plugin": "omarchy plugins",
          "hypr-plugin": "hyprland plugins", "mise": "mise toolchains", "local-bin": "~/.local/bin"}


def source_colors(pal):
    """One theme colour (hex) per source, shared by every inventory design."""
    g = lambda *keys: next(pal[k] for k in keys + ("foreground",) if isinstance(pal.get(k), str))  # noqa: E731
    return {"core": g("blue"), "extra": g("cyan"), "omarchy": g("accent"), "aur": g("magenta"),
            "flatpak": g("yellow"), "runtime": g("orange", "bright_yellow"), "appimage": g("red"),
            "omarchy-plugin": g("green"), "hypr-plugin": g("bright_magenta", "magenta"),
            "mise": g("bright_red", "red"), "local-bin": g("bright_cyan", "cyan")}


def human(n):
    for u in ("B", "KB", "MB", "GB", "TB"):
        if n < 1000 or u == "TB":
            return f"{n:.0f} {u}" if u in ("B", "KB") else f"{n:.1f} {u}"
        n /= 1000


if __name__ == "__main__":
    inv = load(refresh="--refresh" in sys.argv)
    for s, (n, b) in summary(inv).items():
        print(f"{s:15s} {n:5d}  {human(b):>9s}")
    print(f"{'total':15s} {len(inv):5d}  {human(sum(i['bytes'] for i in inv)):>9s}")
