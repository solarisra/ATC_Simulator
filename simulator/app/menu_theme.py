"""System appearance detection for the Arcade menu."""

import subprocess
import sys

import darkdetect


def system_theme():
    if sys.platform.startswith("linux"):
        result = subprocess.run(
            ["gsettings", "get", "org.gnome.desktop.interface", "color-scheme"],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
        if result.returncode == 0:
            preference = result.stdout.strip().strip("'").lower()
            if preference == "prefer-dark":
                return "Dark"
            if preference == "prefer-light":
                return "Light"
            if preference != "default":
                raise ValueError(f"Unknown desktop color scheme: {preference}")

        result = subprocess.run(
            ["gsettings", "get", "org.gnome.desktop.interface", "gtk-theme"],
            capture_output=True,
            text=True,
            timeout=3,
            check=True,
        )
        theme = result.stdout.strip().strip("'")
        if not theme:
            raise ValueError("Desktop GTK theme is empty")
        return "Dark" if "dark" in theme.lower() else "Light"

    theme = darkdetect.theme()
    if theme not in ("Light", "Dark"):
        raise ValueError(f"System appearance is unavailable: {theme!r}")
    return theme
