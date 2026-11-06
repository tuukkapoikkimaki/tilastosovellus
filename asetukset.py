"""Sovelluksen yhteiset asetukset."""

import os
import sys
from pathlib import Path


def _datakansio():
    """Käyttöjärjestelmän tavallinen paikka sovellusten datalle."""
    if sys.platform == "win32":
        # Windows: %LOCALAPPDATA%\tilastosovellus
        juuri = os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local"
    else:
        # Linux ja macOS (XDG): ~/.local/share/tilastosovellus
        juuri = os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share"
    return Path(juuri) / "tilastosovellus"


DATAKANSIO = _datakansio()
TIETOKANTA = DATAKANSIO / "tilastot.db"
