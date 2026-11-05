"""Sovelluksen yhteiset asetukset."""

import os
from pathlib import Path

# Tietokanta käyttäjän datakansiossa (XDG): ~/.local/share/tilastosovellus/tilastot.db
DATAKANSIO = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share") / "tilastosovellus"
TIETOKANTA = DATAKANSIO / "tilastot.db"
