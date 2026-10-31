"""Shared helpers for the Burnout 3 x Revenge mashup tools (stdlib only)."""
from pathlib import Path

ROOT = ISOS = EXTRACTED = REPORTS = None   # vendored copy: no PS2 workspace folders

# Serial -> short game key. Serials are read from SYSTEM.CNF on the disc.
# CRCs are the PCSX2 game CRCs published in Nahelam/PS2-Game-Mods pnach
# filenames; we recompute them from the ELF as an integrity check.
KNOWN = {
    "SLUS_210.50": ("b3", "Burnout 3: Takedown (NTSC-U)", 0xBEBF8793),
    "SLUS_212.42": ("rev", "Burnout Revenge (NTSC-U)", 0xD224D348),
}
