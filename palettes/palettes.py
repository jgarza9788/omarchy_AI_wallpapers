"""Extract color schemes from installed Omarchy themes.

Run directly to (re)generate palettes.json; import `load()` from generators.
"""
import json
import pathlib
import tomllib

THEMES_DIR = pathlib.Path("/usr/share/omarchy/themes")
HERE = pathlib.Path(__file__).resolve().parent
JSON_PATH = HERE / "palettes.json"

ANSI = ["black", "red", "green", "yellow", "blue", "magenta", "cyan", "white"]


def extract():
    out = {}
    for toml in sorted(THEMES_DIR.glob("*/colors.toml")):
        data = tomllib.loads(toml.read_text())
        pal = {k: v for k, v in data.items() if isinstance(v, str) and v.startswith("#")}
        pal["mode"] = data.get("mode", "dark")
        # Normalise: some themes name ANSI slots color0..15 instead of names.
        for i, name in enumerate(ANSI):
            if name not in pal and f"color{i}" in pal:
                pal[name] = pal[f"color{i}"]
            if f"bright_{name}" not in pal and f"color{i + 8}" in pal:
                pal[f"bright_{name}"] = pal[f"color{i + 8}"]
        pal.setdefault("accent", pal.get("blue", pal["foreground"]))
        pal.setdefault("black", pal.get("darker_background", pal["background"]))
        pal.setdefault("white", pal.get("bright_foreground", pal["foreground"]))
        pal.setdefault("bright_black", pal.get("muted", pal["black"]))
        pal.setdefault("bright_white", pal.get("light_foreground", pal["white"]))
        out[toml.parent.name] = pal
    out["omarchy"] = official(out)
    return out


# Omarchy publishes no colour spec (omarchy.us/brand only has logos). The de facto
# official scheme: the default theme (Tokyo Night, set by install/user/theme.sh) with
# the brand green that every official logo is filled with as the accent.
OMA_GREENS = ["#daecc6", "#bbdd97", "#9ece6a", "#678549", "#39482e"]   # oma-logo.svg bands, light -> dark


def official(themes):
    pal = dict(themes["tokyo-night"])
    pal.update({
        "accent": "#9ece6a",            # logo / wordmark fill
        "selection": "#39482e",
        "oma_bands": OMA_GREENS,
    })
    return pal


def load():
    if not JSON_PATH.exists():
        JSON_PATH.write_text(json.dumps(extract(), indent=2))
    return json.loads(JSON_PATH.read_text())


def rgb(hex_color):
    h = hex_color.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


if __name__ == "__main__":
    data = extract()
    JSON_PATH.write_text(json.dumps(data, indent=2))
    for name, pal in data.items():
        missing = [k for k in ["background", "foreground", "accent", *ANSI] if k not in pal]
        print(f"{name:18} {pal['mode']:5} bg={pal['background']} fg={pal['foreground']} "
              f"accent={pal['accent']}" + (f"  MISSING {missing}" if missing else ""))
