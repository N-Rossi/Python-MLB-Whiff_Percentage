"""Shared constants for the v2 API — pitch-type labels and role enums."""

from __future__ import annotations

# Statcast pitch-type codes → human-readable labels. Mirrors TABLES.md.
PITCH_TYPE_LABELS: dict[str, str] = {
    "FF": "4-Seam Fastball",
    "SI": "Sinker",
    "FC": "Cutter",
    "SL": "Slider",
    "ST": "Sweeper",
    "SV": "Slurve",
    "CU": "Curveball",
    "KC": "Knuckle-Curve",
    "CS": "Slow Curve",
    "CH": "Changeup",
    "FS": "Splitter",
    "FO": "Forkball",
    "SC": "Screwball",
    "KN": "Knuckleball",
    "EP": "Eephus",
    "PO": "Pitchout",
}

# Default minimum sample sizes from SAMPLE_SIZES.md. Endpoints expose these
# as query params so the frontend can relax or tighten them.
DEFAULT_MIN_SEQUENCE_N = 10
DEFAULT_MIN_PITCHER_N = 50
DEFAULT_MIN_BATTER_SWINGS = 30
