"""Sign a finished Blender render with the Omarchy wordmark + caption (the same corner signature as 11)."""
import subprocess

from appfield import brand


def sign(path, pal, s, caption, corner="southwest"):
    subprocess.run(["magick", str(path), *brand(pal, s, caption, corner), str(path)], check=True)
