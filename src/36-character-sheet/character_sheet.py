"""36 — Character Sheet: this machine as a D&D adventurer.

A line drawing of a hero (knight, wizard or orc) stands in the middle of a
character sheet. Callouts around them name the gear they have equipped, and
every piece of gear is a real installed package (src/inventory.py): hyprland is
the helm, limine the boots, git the gauntlets, docker the belt of holding.
Item names are coloured by rarity, which is where the package came from (core =
common, extra = uncommon, AUR = rare, flatpak = epic, mise = artifact, omarchy =
legendary, local plugins and scripts = homebrew). The left page has the ability
scores, worked out from the inventory (STR = gigabytes carried, WIS = AI agents
consulted ...); the backpack on the right lists every other explicit install.

The figures are hand-written SVG paths; the sheet is one SVG rasterised by
rsvg-convert over a numpy background.

Usage: python3 src/36-character-sheet/character_sheet.py [--hero knight|wizard|orc|all] [--scheme omarchy|all] [--scale 0.25]
"""
import argparse
import getpass
import hashlib
import math
import pathlib
import re
import subprocess
import sys
from xml.sax.saxutils import escape

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import github_stats  # noqa: E402
import inventory  # noqa: E402
from appfield import brand, write  # noqa: E402
from common import H, ROOT, W, hex2arr, out_path, scheme_args, value_noise  # noqa: E402

# (scheme, hero) pairs rendered by --scheme all
VARIANTS = [("omarchy", "knight"), ("omarchy", "wizard"), ("omarchy", "orc"),
            ("gruvbox", "orc"), ("nord", "knight"), ("catppuccin", "wizard")]
HEROES = ["knight", "wizard", "orc"]
MONO = "Iosevka Nerd Font Mono"
DISPLAY = "SpaceMono Nerd Font Mono"

# source -> (rarity, palette key)
RARITY = {"core": ("common", "foreground"), "runtime": ("common", "foreground"),
          "extra": ("uncommon", "green"), "aur": ("rare", "blue"),
          "flatpak": ("epic", "magenta"), "appimage": ("epic", "magenta"),
          "mise": ("artifact", "red"), "omarchy": ("legendary", "bright_yellow"),
          "omarchy-plugin": ("homebrew", "cyan"), "hypr-plugin": ("homebrew", "cyan"), "local-bin": ("homebrew", "cyan")}
LEGEND = {"common": "core · runtimes", "uncommon": "extra", "rare": "AUR", "epic": "flatpak · AppImage",
          "artifact": "mise", "legendary": "omarchy repo", "homebrew": "plugins · scripts"}
RARITY_ORDER = ["common", "uncommon", "rare", "epic", "artifact", "legendary", "homebrew"]

# slot -> candidate packages, first one installed wins; {weapon}/{offhand} etc. come from the hero
SLOTS = {
    "head": (["hyprland"], "{helm} of Tiling"),
    "neck": (["omarchy"], "Amulet of Omakase"),
    "shoulders": (["tmux", "zellij"], "{shoulders} of Many Panes"),
    "cloak": (["ghostty", "kitty", "alacritty", "foot"], "{cloak} of the Terminal"),
    "chest": (["linux-omarchy", "linux", "linux-zen", "linux-lts"], "{chest} of the Kernel"),
    "hands": (["git"], "{hands} of Commitment"),
    "ring": (["claude", "codex", "gemini", "opencode"], "Ring of Reasoning"),
    "belt": (["docker", "podman"], "Belt of Holding (containers)"),
    "main": (["omarchy-nvim", "neovim", "visual-studio-code-bin", "helix"], "{weapon} of Modal Editing"),
    "off": (None, None),                                   # per hero
    "legs": (["btrfs-progs", "snapper"], "{legs} of Snapshots"),
    "boots": (["limine", "grub", "systemd"], "Boots of Booting"),
}
SLOT_TITLE = {"head": "HEAD", "neck": "NECK", "shoulders": "SHOULDERS", "cloak": "BACK", "chest": "CHEST",
              "hands": "HANDS", "ring": "FINGER", "belt": "WAIST", "main": "MAIN HAND", "off": "OFF HAND",
              "legs": "LEGS", "boots": "FEET"}


# ---------------------------------------------------------------- figures
# Drawn in figure units: x in about ±450 around the centre line, y from 0 (top) to ~1560 (the ground).
# Each part is (style, shape): style f = filled with the background (occludes what is behind),
# d = thin detail line, a = accent line, g = ground. Shapes are SVG path strings with absolute
# "x,y" pairs only, so mirror() can flip them; ("e", cx, cy, rx, ry) is an ellipse.

def mirror(d):
    if isinstance(d, tuple):
        return (d[0], -d[1], *d[2:])
    return re.sub(r"(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)", lambda m: f"{-float(m.group(1)):g},{m.group(2)}", d)


def both(style, d):
    return [(style, d), (style, mirror(d))]


def knight():
    p = []
    p += [("g", ("e", 0, 1555, 330, 20))]
    # cape behind everything
    p += [("f", "M -150,300 C -240,600 -300,1000 -330,1420 Q -270,1395 -215,1425 Q -150,1395 -90,1428 "
                "Q -30,1400 30,1428 Q 90,1398 150,1426 Q 215,1396 270,1424 Q 300,1410 330,1420 "
                "C 300,1000 240,600 150,300 Z"),
          ("d", "M -200,700 C -230,950 -250,1150 -270,1400"), ("d", "M 200,700 C 230,950 250,1150 270,1400")]
    # legs
    for s in (1, -1):
        leg = [("f", "M -125,690 L -25,690 L -32,985 L -115,985 Z"),
               ("d", "M -120,760 L -28,760"), ("d", "M -118,880 L -30,880"),
               ("f", "M -115,1045 C -127,1150 -112,1300 -106,1425 L -42,1425 C -36,1300 -26,1150 -32,1045 Z"),
               ("d", "M -74,1060 C -76,1200 -74,1320 -74,1420"),
               ("f", "M -108,1420 L -40,1420 C -33,1470 -42,1515 -62,1548 L -182,1552 "
                     "C -180,1520 -152,1478 -110,1462 Z"),
               ("d", "M -106,1450 L -38,1452"), ("d", "M -112,1480 L -40,1484"), ("d", "M -130,1510 L -48,1515"),
               ("f", ("e", -72, 1012, 48, 38)), ("f", "M -120,1000 Q -158,1012 -130,1046 Q -120,1030 -118,1015 Z"),
               ("d", ("e", -72, 1012, 18, 14))]
        p += leg if s == 1 else [(st, mirror(d)) for st, d in leg]
    # arms behind the torso
    p += [("f", "M 125,330 L 178,330 L 196,470 L 140,470 Z"), ("f", ("e", 168, 492, 34, 28)),
          ("f", "M 145,508 L 196,508 L 236,600 L 186,612 Z")]
    p += [("f", "M -178,330 L -125,330 L -140,470 L -196,470 Z"), ("f", ("e", -168, 492, 34, 28)),
          ("d", ("e", -168, 492, 12, 10)),
          ("f", "M -196,512 L -145,512 L -190,600 L -238,592 Z"), ("d", "M -192,540 L -150,543")]
    # skirt and tassets
    p += [("f", "M -125,585 L 125,585 L 140,640 L -140,640 Z"), ("f", "M -140,640 L 140,640 L 150,695 L -150,695 Z")]
    p += both("f", "M -152,692 L -38,692 L -46,792 Q -100,808 -148,786 Z")
    p += both("d", "M -146,730 L -42,732")
    # breastplate, belt, gorget
    p += [("f", "M -120,290 C -126,380 -131,470 -118,562 Q 0,612 118,562 C 131,470 126,380 120,290 Z"),
          ("d", "M 0,300 C 4,400 4,500 0,595"), ("d", "M -102,420 Q 0,472 102,420"),
          ("d", "M -110,330 Q -60,345 -40,400"), ("d", "M 110,330 Q 60,345 40,400"),
          ("f", "M -122,562 Q 0,608 122,562 L 126,592 Q 0,638 -126,592 Z"),
          ("f", "M -22,582 L 22,582 L 22,618 L -22,618 Z"), ("d", "M -10,592 L 10,592 L 10,608 L -10,608 Z"),
          ("f", "M -72,248 L 72,248 L 88,302 Q 0,324 -88,302 Z"), ("d", "M -80,276 Q 0,294 80,276")]
    # pauldrons
    for s in (1, -1):
        pd = [("f", "M -230,362 C -232,388 -226,404 -214,414 C -186,408 -160,402 -140,394 L -126,356 "
                    "C -152,370 -196,372 -230,362 Z"),
              ("f", "M -60,280 C -132,254 -218,280 -230,362 C -196,374 -152,370 -126,356 "
                    "C -120,322 -96,302 -60,300 Z"),
              ("d", "M -82,290 C -140,280 -190,300 -208,345"),
              ("d", ("e", -100, 318, 4, 4)), ("d", ("e", -150, 300, 4, 4)), ("d", ("e", -196, 322, 4, 4))]
        p += pd if s == 1 else [(st, mirror(d)) for st, d in pd]
    # helm and plume
    p += [("f", "M 0,52 C 18,-6 112,-30 196,8 C 156,14 124,40 108,78 C 92,48 60,38 30,56 Z"),
          ("d", "M 30,50 C 70,20 120,10 170,12"), ("d", "M 50,52 C 85,34 115,32 140,36"),
          ("f", "M -80,240 L -82,140 C -82,80 -45,46 0,46 C 45,46 82,80 82,140 L 80,240 Q 0,262 -80,240 Z"),
          ("d", "M -82,120 Q 0,108 82,120"), ("d", "M 0,48 L 0,252"),
          ("a", "M -68,150 L -12,150"), ("a", "M 12,150 L 68,150"),
          ("d", "M -68,166 L -12,166"), ("d", "M 12,166 L 68,166")]
    p += [("d", ("e", x, y, 3.5, 3.5)) for x in (30, 46, 62) for y in (200, 216)]
    # sword, planted point down, hand on the grip
    p += [("f", "M -268,712 L -232,712 L -232,1478 L -250,1530 L -268,1478 Z"), ("d", "M -250,730 L -250,1450"),
          ("f", "M -334,682 Q -250,698 -166,682 L -164,706 Q -250,720 -336,706 Z"),
          ("f", ("e", -250, 572, 18, 18)), ("f", "M -260,588 L -240,588 L -240,684 L -260,684 Z"),
          ("f", "M -226,590 C -206,604 -208,650 -214,676 L -286,676 C -296,640 -282,600 -250,590 Z"),
          ("d", "M -288,616 L -212,616"), ("d", "M -290,638 L -210,638"), ("d", "M -288,658 L -212,658")]
    # kite shield on the far arm
    p += [("f", "M 108,520 Q 230,488 352,520 C 356,700 322,862 230,1002 C 138,862 104,700 108,520 Z"),
          ("d", "M 130,540 Q 230,513 330,540 C 333,700 302,845 230,972 C 158,845 127,700 130,540 Z"),
          ("a", "M 150,700 L 230,628 L 310,700"), ("a", "M 150,744 L 230,672 L 310,744")]
    anchors = {"head": (-70, 190, "L"), "hands": (-170, 556, "L"), "ring": (-212, 668, "L"),
               "main": (-250, 1180, "L"), "cloak": (-302, 1330, "L"), "boots": (-150, 1530, "L"),
               "neck": (60, 285, "R"), "shoulders": (200, 330, "R"), "chest": (80, 450, "R"),
               "belt": (100, 586, "R"), "off": (300, 780, "R"), "legs": (74, 1200, "R")}
    names = {"helm": "Great Helm", "shoulders": "Pauldrons", "cloak": "Cape", "chest": "Breastplate",
             "hands": "Gauntlets", "weapon": "Longsword", "legs": "Greaves"}
    off = (["ufw", "firewalld"], "Kite Shield of Denial")
    return p, anchors, names, off


def wizard():
    p = [("g", ("e", 0, 1555, 360, 20))]
    # robe
    p += [("f", "M -70,350 C -132,355 -166,380 -176,420 C -200,700 -282,1100 -332,1522 "
                "Q -166,1552 0,1536 Q 166,1552 332,1522 C 282,1100 200,700 176,420 C 166,380 132,355 70,350 Z"),
          ("d", "M -70,820 C -92,1100 -116,1300 -140,1530"), ("d", "M 50,780 C 70,1100 96,1300 120,1534"),
          ("d", "M -12,900 C -8,1200 -4,1350 0,1536"), ("d", "M -200,1000 C -230,1200 -250,1350 -270,1520"),
          ("d", "M 220,1050 C 240,1250 260,1380 280,1522")]
    p += both("f", "M -150,1534 Q -200,1548 -232,1528 Q -196,1566 -128,1560 Z")
    # sash and pouch
    p += [("f", "M -192,690 Q 0,722 192,690 L 196,732 Q 0,764 -196,732 Z"),
          ("f", "M 40,740 L 30,890 L 58,878 L 74,742 Z"), ("f", "M 70,742 L 82,860 L 104,850 L 100,740 Z"),
          ("f", "M 112,740 L 174,740 L 168,818 Q 142,834 116,818 Z"), ("d", "M 112,764 L 174,764"),
          ("d", ("e", 143, 776, 6, 6))]
    # far arm: sleeve, book, hand
    p += [("f", "M 150,396 C 214,440 238,520 226,590 L 132,616 Q 104,580 128,550 C 146,510 148,470 142,440 Z"),
          ("f", "M 92,520 L 236,542 L 220,666 L 76,644 Z"), ("f", "M 86,640 L 222,662 L 220,680 L 82,658 Z"),
          ("d", "M 96,530 L 82,650"), ("a", ("e", 158, 594, 26, 22)), ("a", "M 158,574 L 158,614"),
          ("f", "M 166,572 Q 206,574 212,606 Q 196,628 166,620 Z")]
    # beard, face, hat
    p += [("f", "M -60,312 C -64,362 -50,392 0,402 C 50,392 64,362 60,312 Z"),
          ("d", "M -36,346 Q -25,339 -14,346"), ("d", "M 14,346 Q 25,339 36,346"),
          ("d", "M -42,332 L -12,336"), ("d", "M 12,336 L 42,332"), ("d", "M 0,346 L -9,380 L 6,384"),
          ("f", "M -66,368 C -94,450 -84,560 -42,650 Q 0,724 42,650 C 84,560 94,450 66,368 Q 30,410 0,404 "
                "Q -30,410 -66,368 Z"),
          ("d", "M -30,430 C -40,500 -30,580 -12,660"), ("d", "M 26,440 C 36,510 30,580 14,660"),
          ("d", "M 0,420 C 2,500 2,600 0,700"), ("d", "M -52,440 C -60,500 -52,560 -36,620"),
          ("f", "M -46,394 Q -20,384 0,392 Q 20,384 46,394 Q 30,412 0,404 Q -30,412 -46,394 Z"),
          ("f", ("e", 0, 566, 15, 15)), ("a", ("e", 0, 566, 7, 7)), ("d", "M -40,470 Q 0,540 40,470"),
          ("f", "M -112,292 C -96,200 -40,120 20,70 C 62,40 112,40 156,6 C 124,60 92,110 96,170 "
                "C 100,230 110,270 112,292 Q 0,306 -112,292 Z"),
          ("f", "M -110,270 Q 0,286 110,270 L 113,294 Q 0,308 -113,294 Z"),
          ("f", "M -196,302 Q 0,250 196,302 Q 0,354 -196,302 Z"),
          ("a", "M -20,190 L -14,206 L 2,206 L -10,216 L -6,232 L -20,222 L -34,232 L -30,216 L -42,206 L -26,206 Z"),
          ("a", ("e", 40, 140, 5, 5)), ("a", ("e", 60, 220, 4, 4))]
    # staff with an orb, then the near sleeve and hand
    p += [("f", "M -284,170 L -262,170 L -238,1550 L -258,1550 Z"), ("d", "M -276,400 L -268,410"),
          ("d", "M -262,900 L -254,912"), ("d", "M -256,1200 L -248,1210"),
          ("a", ("e", -274, 104, 44, 44)), ("a", ("e", -274, 104, 22, 22)),
          ("f", "M -300,176 C -334,130 -330,80 -306,52 L -296,62 C -314,90 -314,130 -286,170 Z"),
          ("f", "M -248,176 C -214,130 -218,80 -242,52 L -252,62 C -234,90 -234,130 -262,170 Z"),
          ("f", "M -162,400 C -222,440 -252,520 -262,580 L -318,640 Q -270,668 -214,640 L -194,610 "
                "C -178,540 -158,470 -144,440 Z"), ("d", "M -316,640 Q -268,656 -216,640"),
          ("f", "M -292,646 C -300,666 -296,690 -282,704 L -244,702 C -238,682 -240,662 -246,646 Z"),
          ("d", "M -294,666 L -242,666"), ("d", "M -292,686 L -240,686")]
    anchors = {"head": (-70, 220, "L"), "main": (-274, 104, "L"), "hands": (-290, 690, "L"),
               "cloak": (-300, 1330, "L"), "legs": (-110, 1180, "L"), "boots": (-200, 1544, "L"),
               "neck": (12, 566, "R"), "shoulders": (160, 410, "R"), "ring": (196, 606, "R"),
               "off": (230, 600, "R"), "belt": (150, 800, "R"), "chest": (180, 1000, "R")}
    names = {"helm": "Pointed Hat", "shoulders": "Mantle", "cloak": "Robe", "chest": "Vestments",
             "hands": "Gloves", "weapon": "Staff", "legs": "Hose"}
    off = (["obsidian", "logseq", "zettlr", "xournalpp"], "Tome of Notes")
    return p, anchors, names, off


def orc():
    p = [("g", ("e", 0, 1555, 360, 20))]
    for s in (1, -1):
        leg = [("f", "M -162,740 C -178,850 -172,950 -160,1052 L -58,1052 C -52,950 -44,850 -38,740 Z"),
               ("f", "M -158,1048 C -166,1200 -160,1350 -150,1452 L -68,1452 C -64,1350 -58,1200 -60,1048 Z"),
               ("d", "M -158,1100 L -62,1130"), ("d", "M -160,1160 L -62,1190"), ("d", "M -158,1220 L -62,1250"),
               ("d", "M -156,1280 L -64,1310"), ("d", "M -154,1340 L -66,1370"),
               ("f", "M -156,1440 L -66,1440 C -52,1482 -48,1520 -58,1552 L -206,1552 "
                     "C -210,1512 -184,1480 -156,1462 Z"),
               ("f", "M -164,1430 Q -140,1416 -110,1432 Q -84,1416 -58,1432 L -60,1462 Q -110,1452 -162,1462 Z"),
               ("d", "M -150,880 Q -110,930 -60,890")]
        p += leg if s == 1 else [(st, mirror(d)) for st, d in leg]
    # torso
    p += [("f", "M -95,330 C -170,340 -236,380 -242,452 C -232,560 -182,640 -152,702 L 152,702 "
                "C 182,640 232,560 242,452 C 236,380 170,340 95,330 Z"),
          ("d", "M -152,470 Q -80,524 -10,482"), ("d", "M 10,482 Q 80,524 152,470"), ("d", "M 0,500 L 0,690"),
          ("d", "M -60,580 Q -30,590 -6,580"), ("d", "M 6,580 Q 30,590 60,580"),
          ("d", "M -60,630 Q -30,640 -6,630"), ("d", "M 6,630 Q 30,640 60,630"),
          ("a", "M -128,420 L -70,548"), ("a", "M -116,450 L -96,440"), ("a", "M -102,480 L -82,470"),
          ("a", "M -88,512 L -68,502"),
          ("f", "M -180,378 L -146,366 L 190,672 L 160,698 Z"), ("d", ("e", -30, 504, 7, 7)), ("d", ("e", 70, 594, 7, 7))]
    # belt with a skull buckle, loincloth
    p += [("f", "M -50,740 L 50,740 L 62,904 Q 0,924 -62,904 Z"), ("d", "M -30,760 L -36,900"), ("d", "M 30,760 L 36,900"),
          ("f", "M -166,690 L 166,690 L 170,744 L -170,744 Z"),
          ("f", "M -24,694 C -32,676 -20,658 0,658 C 20,658 32,676 24,694 L 18,742 L -18,742 Z"),
          ("d", ("e", -9, 690, 6, 6)), ("d", ("e", 9, 690, 6, 6)), ("d", "M -8,724 L -8,738 M 0,724 L 0,738 M 8,724 L 8,738")]
    # head
    p += both("f", "M -74,252 L -146,212 L -88,296 Z")
    p += [("f", "M -14,148 C -24,100 -10,62 12,46 C 2,86 24,112 16,148 Z"),
          ("f", "M -70,220 C -76,170 -44,140 0,140 C 44,140 76,170 70,220 L 96,302 C 102,352 70,392 0,397 "
                "C -70,392 -102,352 -96,302 Z"),
          ("a", "M -62,240 Q -32,224 -8,246"), ("a", "M 8,246 Q 32,224 62,240"),
          ("d", "M -46,264 L -20,268"), ("d", "M 20,268 L 46,264"),
          ("d", "M -8,272 Q -16,302 0,308 Q 16,302 8,272"), ("d", "M -48,342 Q 0,358 48,342")]
    p += both("f", "M -36,348 L -46,296 L -24,344 Z")
    p += [("d", "M -70,384 Q 0,436 70,384")] + [("f", f"M {x},{y} L {x + 8},{y + 22} L {x + 16},{y}") for x, y in
                                                ((-50, 398), (-24, 410), (0, 414), (24, 410))]
    # fur mantle over the far shoulder
    p += [("f", "M 116,350 C 180,316 284,336 304,420 Q 294,444 272,432 Q 266,456 244,444 Q 232,466 212,450 "
                "Q 196,464 182,446 Q 156,452 146,432 Q 116,420 116,350 Z"),
          ("d", "M 160,370 L 176,398"), ("d", "M 210,360 L 222,392"), ("d", "M 256,376 L 262,404")]
    # arms
    for s in (1, -1):
        arm = [("f", "M -214,400 C -290,410 -322,480 -318,562 L -256,572 C -250,500 -226,462 -200,442 Z"),
               ("f", "M -318,560 C -332,620 -328,680 -312,732 L -250,736 C -244,680 -248,620 -256,570 Z"),
               ("f", "M -326,620 L -250,626 L -248,690 L -322,686 Z"), ("d", "M -324,644 L -249,650"),
               ("d", "M -323,666 L -248,670"), ("d", "M -300,470 Q -270,490 -258,530")]
        p += arm if s == 1 else [(st, mirror(d)) for st, d in arm]
    # axe in the near hand, torch in the far hand
    axe = "translate(-329,470) rotate(-8.3) scale(0.8)"                 # local y runs down the haft from its top
    p += [("f", "M -239.1,1011.6 L -318.1,471.6 L -339.9,468.4 L -260.9,1008.4 Z"), ("f", ("e", -253, 1030, 15, 15)),
          ("f", "M -10,30 L -42,36 C -86,10 -118,14 -138,-4 C -156,60 -156,120 -138,186 C -118,168 -86,172 -42,146 "
                "L -10,152 Z", axe),
          ("d", "M -24,48 C -70,34 -104,40 -124,24 C -136,72 -136,112 -124,160 C -104,146 -70,150 -24,136", axe),
          ("f", "M 10,62 L 62,92 L 10,122 Z", axe), ("f", "M -12,20 L 12,20 L 12,162 L -12,162 Z", axe),
          ("d", "M -12,60 L 12,60 M -12,124 L 12,124", axe),
          ("f", "M -322,734 C -338,762 -322,802 -292,808 L -246,802 C -236,776 -240,748 -250,734 Z"),
          ("d", "M -326,758 L -246,760"), ("d", "M -324,782 L -244,782")]
    p += [("f", "M 276,640 L 294,640 L 290,900 L 280,900 Z"),
          ("f", "M 322,734 C 338,762 322,802 292,808 L 246,802 C 236,776 240,748 250,734 Z"),
          ("d", "M 326,758 L 246,760"), ("d", "M 324,782 L 244,782"),
          ("f", "M 266,640 L 304,640 L 308,598 L 262,598 Z"), ("d", "M 264,612 L 306,612"),
          ("a", "M 285,470 C 304,510 324,540 314,575 C 304,600 266,600 256,575 C 246,545 272,520 285,470 Z"),
          ("a", "M 285,530 C 294,548 300,566 292,580 C 284,590 276,580 278,566 C 280,554 284,546 285,530 Z")]
    anchors = {"head": (-50, 180, "L"), "shoulders": (-150, 382, "L"), "hands": (-300, 650, "L"),
               "main": (-425, 557, "L"), "legs": (-110, 900, "L"), "boots": (-170, 1530, "L"),
               "neck": (40, 412, "R"), "cloak": (276, 400, "R"), "off": (300, 520, "R"),
               "chest": (140, 520, "R"), "belt": (20, 680, "R"), "ring": (300, 790, "R")}
    names = {"helm": "Warhelm", "shoulders": "Bandolier", "cloak": "Fur Mantle", "chest": "Warpaint",
             "hands": "Bracers", "weapon": "Greataxe", "legs": "Wraps"}
    off = (["firefox", "chromium", "brave-bin"], "Torch of the Open Web")
    return p, anchors, names, off


FIGURES = {"knight": knight, "wizard": wizard, "orc": orc}


def shape_svg(shape, attrs, transform=None):
    if transform:
        attrs += f' transform="{transform}"'
    if isinstance(shape, tuple):
        _, cx, cy, rx, ry = shape
        return f'<ellipse cx="{cx}" cy="{cy}" rx="{rx}" ry="{ry}" {attrs}/>'
    return f'<path d="{shape}" {attrs}/>'


# ---------------------------------------------------------------- data

def col(pal, key):
    v = pal.get(key)
    return v if isinstance(v, str) and v.startswith("#") else pal["foreground"]


def base(name):
    return name.split("@")[0]


def find(inv, cands):
    for c in cands or []:
        hits = [i for i in inv if base(i["name"]) == c]
        if hits:
            return max(hits, key=lambda i: (i["version"], i["bytes"]))
    return None


def score(n, c):
    return int(max(3, min(20, round(8 + 3 * math.log2(1 + n / c)))))


def abilities(inv):
    ex = [i for i in inv if i["explicit"]]
    gb = sum(i["bytes"] for i in inv) / 1e9
    dev = re.compile(r"^(clang|llvm|cmake|meson|gcc|rust|go|python|node|ruby|lua\d*|dotnet.*|docker|git|tree-sitter.*|"
                     r"luarocks|base-devel|deno|bun|zig|java.*|jdk.*|php)(@|$)")
    agents = {"claude", "codex", "gemini", "copilot", "opencode", "crush", "grok", "cursor-agent", "pi", "hermes",
              "aider", "goose", "amp"}
    looks = re.compile(r"(font|theme|icon|cursor|wallpaper|wallsync|aether|gtk|kvantum)")
    plugins = [i for i in inv if i["source"] in ("omarchy-plugin", "hypr-plugin", "local-bin")]
    tools = {base(i["name"]) for i in ex if dev.search(i["name"])}
    ai = {base(i["name"]) for i in ex if base(i["name"]) in agents}
    core = [i for i in inv if i["source"] == "core"]
    style = [i for i in inv if looks.search(i["name"])]
    return [("STR", score(gb, 4), f"{gb:.1f} GB carried"),
            ("DEX", score(len(plugins), 6), f"{len(plugins)} plugins & scripts"),
            ("CON", score(len(core), 30), f"{len(core)} core packages"),
            ("INT", score(len(tools), 3), f"{len(tools)} toolchains"),
            ("WIS", score(len(ai), 1.5), f"{len(ai)} AI agents consulted"),
            ("CHA", score(len(style), 8), f"{len(style)} fonts & themes")]


# ---------------------------------------------------------------- the sheet

def text(x, y, s, size, fill, family=MONO, weight="normal", anchor="start", spacing=0, opacity=1.0, style="normal"):
    return (f'<text x="{x:.0f}" y="{y:.0f}" font-family="{family}" font-size="{size}" font-weight="{weight}" '
            f'font-style="{style}" fill="{fill}" fill-opacity="{opacity}" text-anchor="{anchor}" '
            f'letter-spacing="{spacing}">{escape(s)}</text>')


def sheet_svg(pal, hero, inv, draw_figure=None):
    fg, dim, bg = pal["foreground"], col(pal, "dark_foreground"), pal["background"]
    acc = pal["accent"]
    rare = {r: col(pal, k) for r, k in RARITY.values()}
    parts, anchors, names, off = FIGURES[hero]()
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">',
           '<defs><filter id="glow" x="-20%" y="-20%" width="140%" height="140%">'
           '<feGaussianBlur stdDeviation="9"/></filter></defs>']

    # frame with notched corners
    for inset, sw, op in ((56, 3, 0.55), (72, 1.5, 0.35)):
        n = 26
        x0, y0, x1, y1 = inset, inset, W - inset, H - inset
        out.append(f'<path d="M {x0 + n},{y0} L {x1 - n},{y0} L {x1},{y0 + n} L {x1},{y1 - n} L {x1 - n},{y1} '
                   f'L {x0 + n},{y1} L {x0},{y1 - n} L {x0},{y0 + n} Z" fill="none" stroke="{dim}" '
                   f'stroke-width="{sw}" stroke-opacity="{op}"/>')

    # ---- figure
    fx, fy, k = 1920, 250, 1.06
    sw_main, sw_det = 5.2 / k, 2.6 / k

    def figure(glow):
        g = [f'<g transform="translate({fx},{fy}) scale({k})" stroke-linejoin="round" stroke-linecap="round"'
             + (' filter="url(#glow)" opacity="0.45"' if glow else '') + '>']
        for st, shp, *tf in parts:
            if st == "f":
                a = f'fill="{bg}" stroke="{acc if glow else fg}" stroke-width="{sw_main}"'
            elif st == "d":
                a = f'fill="none" stroke="{acc if glow else fg}" stroke-width="{sw_det}" stroke-opacity="0.8"'
            elif st == "a":
                a = f'fill="none" stroke="{acc}" stroke-width="{sw_main * 0.8}"'
            else:
                a = f'fill="{dim}" fill-opacity="0.25" stroke="none"'
                if glow:
                    continue
            g.append(shape_svg(shp, a, *tf))
        return g + ["</g>"]

    # ---- callouts: leader lines go behind the hero, the dots and labels in front
    gear = {}
    for slot, (cands, flavor) in SLOTS.items():
        if slot == "off":
            cands, flavor = off
        item = find(inv, cands)
        gear[slot] = (item, flavor.format(**names) if flavor else "")
    lines, labels = [], []
    for side in "LR":
        rows = sorted([(ay, ax, slot) for slot, (ax, ay, sd) in anchors.items() if sd == side])
        y_top, y_bot, gap = 330, 1830, 250
        ys = [min(max(fy + ay * k, y_top), y_bot) for ay, _, _ in rows]     # labels sit level with their anchor,
        for i in range(1, len(ys)):                                         # pushed apart where they would collide
            ys[i] = max(ys[i], ys[i - 1] + gap)
        ys[-1] = min(ys[-1], y_bot)
        for i in range(len(ys) - 2, -1, -1):
            ys[i] = min(ys[i], ys[i + 1] - gap)
        for (ay, ax, slot), ly in zip(rows, ys):
            px, py = fx + ax * k, fy + ay * k
            item, flavor = gear[slot]
            colr = rare[RARITY[item["source"]][0]] if item else dim
            edge = 1450 if side == "L" else 2390
            far = 950 if side == "L" else 2890
            tx, anc = (edge - 10, "end") if side == "L" else (edge + 10, "start")
            lines.append(f'<polyline points="{px:.0f},{py:.0f} {edge},{ly + 14:.0f} {far},{ly + 14:.0f}" fill="none" '
                         f'stroke="{dim}" stroke-width="2" stroke-opacity="0.85"/>')
            labels.append(f'<circle cx="{px:.0f}" cy="{py:.0f}" r="7" fill="{bg}" stroke="{colr}" stroke-width="3"/>')
            labels.append(f'<rect x="{edge - 6}" y="{ly + 8:.0f}" width="12" height="12" fill="{colr}" '
                          f'transform="rotate(45 {edge} {ly + 14:.0f})"/>')
            labels.append(text(tx, ly - 74, SLOT_TITLE[slot], 22, dim, anchor=anc, spacing=5))
            if item:
                rarity = RARITY[item["source"]][0]
                ver = item["version"].split("-")[0] if item["version"] else ""
                labels.append(text(tx, ly - 24, base(item["name"]), 44, colr, family=DISPLAY, weight="bold", anchor=anc))
                labels.append(text(tx, ly + 50, flavor, 24, fg, anchor=anc, style="italic", opacity=0.9))
                meta = "  ·  ".join(x for x in (inventory.human(item["bytes"]), f"v{ver}" if ver else "", rarity) if x)
                labels.append(text(tx, ly + 82, meta, 21, dim, anchor=anc, spacing=1))
            else:
                labels.append(text(tx, ly - 24, "— empty —", 40, dim, family=DISPLAY, anchor=anc))
    fig = draw_figure(parts, pal, fx, fy, k) if draw_figure else figure(True) + figure(False)
    under, fig = fig if isinstance(fig, tuple) else ([], fig)       # a renderer may put a backdrop under the leaders
    out += under + lines + fig + labels

    # ---- left page: name plate, abilities, vitals (+ GitHub), quest log, legend
    ex = [i for i in inv if i["explicit"]]
    pac = [i for i in inv if i["source"] in ("core", "extra", "omarchy", "aur")]
    gh = github_stats.load()
    x0, colw = 150, 706
    out.append(text(x0, 210, "CHARACTER SHEET", 24, dim, spacing=8))
    out.append(text(x0, 320, getpass.getuser(), 104, pal["foreground"], family=DISPLAY, weight="bold"))
    out.append(text(x0, 386, f"Level {len(ex)} {hero.title()}", 44, acc, family=DISPLAY, weight="bold"))
    sub = f"@{gh['login']}  ·  adventuring since {gh['since']}  ·  Arch · Omarchy" if gh else \
        "Arch Linux  ·  Omarchy  ·  chaotic rolling"
    out.append(text(x0, 436, sub, 26, dim))
    bw, bh, gap = 340, 176, 22
    for idx, (ab, val, note) in enumerate(abilities(inv)):
        bx, by = x0 + (idx % 2) * (bw + gap), 486 + (idx // 2) * (bh + gap)
        mod = (val - 10) // 2
        out.append(f'<rect x="{bx}" y="{by}" width="{bw}" height="{bh}" rx="14" fill="{bg}" fill-opacity="0.6" '
                   f'stroke="{dim}" stroke-width="2.5"/>')
        out.append(text(bx + 26, by + 46, ab, 30, dim, family=DISPLAY, weight="bold", spacing=6))
        out.append(text(bx + 26, by + 126, str(val), 84, fg, family=DISPLAY, weight="bold"))
        out.append(f'<rect x="{bx + bw - 120}" y="{by + 70}" width="94" height="56" rx="28" fill="none" '
                   f'stroke="{acc}" stroke-width="2.5"/>')
        out.append(text(bx + bw - 73, by + 109, f"{mod:+d}", 34, acc, family=DISPLAY, weight="bold", anchor="middle"))
        out.append(text(bx + 26, by + 160, note, 21, dim))
    vit = [("HP", f"{len(inv):,}", "items installed"), ("XP", inventory.human(sum(i['bytes'] for i in inv)), "on disk"),
           ("GP", f"{sum(not i['explicit'] for i in pac)}", "dependencies")]
    if gh:
        vit += [("QUESTS", f"{gh['contributions']:,}", "contributions / yr"), ("RENOWN", f"★{gh['stars']:,}", "stars earned"),
                ("PARTY", f"{gh['followers']}", "followers on GitHub")]
    vw, vh, vy = (colw - 2 * 20) / 3, 118, 486 + 3 * (bh + gap) + 14
    for idx, (lab, val, note) in enumerate(vit):
        bx, by = x0 + (idx % 3) * (vw + 20), vy + (idx // 3) * (vh + 16)
        out.append(f'<rect x="{bx:.0f}" y="{by}" width="{vw:.0f}" height="{vh}" rx="12" fill="none" '
                   f'stroke="{acc if idx >= 3 else dim}" stroke-opacity="{0.6 if idx >= 3 else 1}" stroke-width="2"/>')
        out.append(text(bx + 18, by + 34, lab, 22, dim, family=DISPLAY, weight="bold", spacing=4))
        out.append(text(bx + 18, by + 80, val, 40, fg, family=DISPLAY, weight="bold"))
        out.append(text(bx + 18, by + 106, note, 17, dim))
    ly = vy + ((len(vit) + 2) // 3) * (vh + 16) + 36
    if gh:                                           # the contribution calendar as a quest log
        out.append(text(x0, ly, "QUEST LOG", 22, dim, spacing=6))
        out.append(text(x0 + colw, ly, f"longest streak {gh['longest_streak']} days  ·  current {gh['current_streak']}",
                        19, dim, anchor="end"))
        days = gh["calendar"][-53 * 7:]
        hi = sorted(n for n in days if n)
        qs = [hi[int(len(hi) * q)] for q in (0.25, 0.5, 0.75)] if hi else [1, 2, 3]
        pitch, cell = colw / 53, colw / 53 - 3
        for i, n in enumerate(days):
            cx, cy = x0 + (i // 7) * pitch, ly + 16 + (i % 7) * pitch
            lvl = 0 if not n else 1 + sum(n > q for q in qs)
            c, o = (dim, 0.22) if lvl == 0 else (acc, (0.3, 0.5, 0.75, 1.0)[lvl - 1])
            out.append(f'<rect x="{cx:.1f}" y="{cy:.1f}" width="{cell:.1f}" height="{cell:.1f}" rx="2" '
                       f'fill="{c}" fill-opacity="{o}"/>')
        ly += 16 + 7 * pitch + 44
        if gh["top_repo"]:
            out.append(text(x0, ly, "FAMED DEED", 19, dim, spacing=4))
            out.append(text(x0 + 200, ly, f"{gh['top_repo'][0]}  ★{gh['top_repo'][1]}", 22, rare["legendary"],
                            family=DISPLAY, weight="bold"))
            ly += 36
        out.append(text(x0, ly, "SPELLS KNOWN", 19, dim, spacing=4))
        out.append(text(x0 + 200, ly, "  ".join(f"{n} {c}" for n, c in gh["languages"][:5]), 20, fg, opacity=0.9))
        ly += 64
    out.append(text(x0, ly, "LOOT RARITY", 22, dim, spacing=6))
    for idx, r in enumerate(RARITY_ORDER):
        xx, yy = x0 + (idx // 4) * (colw / 2), ly + 42 + (idx % 4) * 34
        out.append(f'<rect x="{xx:.0f}" y="{yy - 16}" width="16" height="16" fill="{rare[r]}" '
                   f'transform="rotate(45 {xx + 8:.0f} {yy - 8})"/>')
        out.append(text(xx + 32, yy, r, 23, rare[r], family=DISPLAY, weight="bold"))
        out.append(text(xx + 170, yy, LEGEND[r], 18, dim))

    # ---- right page: the backpack
    equipped = {base(i["name"]) for i, _ in gear.values() if i}
    groups = {}
    for i in ex:
        b = base(i["name"])
        if b in equipped or b.startswith("."):
            continue
        g = groups.setdefault(b, {"n": 0, "bytes": 0, "source": i["source"]})
        g["n"] += 1
        g["bytes"] += i["bytes"]
    pack = sorted(groups.items(), key=lambda kv: -kv[1]["bytes"])
    bx0, by0, bx1, by1 = 2960, 170, 3700, 1980
    out.append(f'<rect x="{bx0}" y="{by0}" width="{bx1 - bx0}" height="{by1 - by0}" rx="18" fill="none" '
               f'stroke="{dim}" stroke-width="2.5"/>')
    out.append(text(bx0 + 34, by0 + 64, "BACKPACK", 36, fg, family=DISPLAY, weight="bold", spacing=6))
    out.append(text(bx1 - 34, by0 + 64, f"{len(pack)} items · {inventory.human(sum(g['bytes'] for _, g in pack))}",
                    22, dim, anchor="end"))
    out.append(f'<line x1="{bx0 + 34}" y1="{by0 + 92}" x2="{bx1 - 34}" y2="{by0 + 92}" stroke="{dim}" stroke-width="1.5"/>')
    cols, lh, fs = 3, 21, 17
    cw = (bx1 - bx0 - 68) / cols
    rows = int((by1 - by0 - 140) // lh)
    chars = int(cw / (fs * 0.6)) - 1
    for idx, (b, g) in enumerate(pack[:cols * rows]):
        c, r = divmod(idx, rows)
        short = ".".join(b.split(".")[-2:]) if g["source"] == "flatpak" else b
        label = short + (f" ×{g['n']}" if g["n"] > 1 else "")
        if len(label) > chars:
            label = label[:chars - 1] + "…"
        out.append(text(bx0 + 34 + c * cw, by0 + 130 + r * lh, label, fs, rare[RARITY[g["source"]][0]], opacity=0.92))
    if len(pack) > cols * rows:
        out.append(text(bx1 - 34, by1 - 22, f"+{len(pack) - cols * rows} more", 19, dim, anchor="end"))
    out.append("</svg>")
    return "\n".join(out)


def render(name, pal, hero, s, folder="36-character-sheet", draw_figure=None, stem="sheet"):
    seed = int(hashlib.sha256(f"{name}{hero}".encode()).hexdigest()[:8], 16)
    rng = np.random.default_rng(seed)
    w, h = int(W * s), int(H * s)
    inv = inventory.load()
    bgc, dim, acc = hex2arr(pal["background"]), hex2arr(col(pal, "dark_foreground")), hex2arr(pal["accent"])

    # vellum: grain, a dotted grid like squared paper, a glow behind the hero, vignette
    grain = value_noise(h, w, max(int(6 * s), 2), rng, octaves=3)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    step = 48 * s
    gx, gy = np.abs((xx / step) % 1 - 0.5), np.abs((yy / step) % 1 - 0.5)
    dots = np.clip(1.6 - np.hypot(0.5 - gx, 0.5 - gy) * step / max(1.2 * s * 2, 1), 0, 1)
    glow = np.exp(-(((xx / w - 0.5) / 0.16) ** 2 + ((yy / h - 0.48) / 0.42) ** 2))
    vig = 1 - 0.35 * (((xx / w - 0.5) * 1.6) ** 2 + ((yy / h - 0.5) * 1.8) ** 2)
    img = bgc * (0.92 + 0.12 * grain[..., None]) * vig[..., None]
    img += dim * 0.10 * dots[..., None] + acc * 0.05 * glow[..., None]

    svg = ROOT / ".wip" / f"{folder}-{hero}--{name}.svg"
    svg.parent.mkdir(exist_ok=True)
    svg.write_text(sheet_svg(pal, hero, inv, draw_figure))
    png = svg.with_suffix(f".{s}.png")
    subprocess.run(["rsvg-convert", "-w", str(w), "-h", str(h), "-o", str(png), str(svg)], check=True)
    post = [str(png), "-composite"]
    post += brand(pal, s, f"CHARACTER SHEET  ·  {hero.upper()}  ·  {name.upper()}", corner="southwest")
    write(np.clip(img, 0, 1), out_path(folder, f"{stem}-{hero}--{name}", s), post)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("--hero", default="all")
    args, rest = ap.parse_known_args()
    names, scale, pals = scheme_args([v[0] for v in VARIANTS], rest)
    if "--scheme" not in " ".join(rest) or "all" in rest:
        jobs = [v for v in VARIANTS if args.hero in ("all", v[1])]
    else:
        jobs = [(n, h) for n in names for h in (HEROES if args.hero == "all" else [args.hero])]
    for nm, hero in jobs:
        render(nm, pals[nm], hero, scale)
