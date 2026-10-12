"""Shared figure style: palette roles, colormaps and matplotlib defaults.

Palette from the dataviz reference instance. The three categorical slots are
validated all-pairs on the light surface (CVD dE 9.2, normal-vision dE 24.0);
aqua is below 3:1 contrast on the surface, so every figure using it carries a
legend or direct labels. Sequential = one hue, light to dark; diverging = blue
and red arms with a gray midpoint.
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap  # noqa: E402

SURFACE = "#fcfcfb"
TEXT = "#0b0b0b"
TEXT_2 = "#52514e"
GRID = "#e4e3df"
MUTED = "#a9a8a2"

BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
RED = "#e34948"
MID_GRAY = "#f0efec"

# Categorical roles, fixed order (identity follows the entity, never rank)
INSTRUMENT_COLOR = {"vmp250": BLUE, "vmp5500": ORANGE}
GROUP_COLOR = {"VMP250 free fall": BLUE, "VMP5500": ORANGE, "VMP250 tow-yo": AQUA}

BLUE_RAMP = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]
# Second sequential context takes the next categorical hue (orange), one hue light to dark
ORANGE_RAMP = ["#fde3d6", "#f8bfa3", "#f39470", "#eb6834", "#c4501f", "#933a14", "#62260c"]

SEQ_EPSILON = LinearSegmentedColormap.from_list("seq_blue", BLUE_RAMP)
SEQ_CHI = LinearSegmentedColormap.from_list("seq_orange", ORANGE_RAMP)
DIVERGING = LinearSegmentedColormap.from_list(
    "div_blue_red", ["#184f95", "#6da7ec", MID_GRAY, "#ee9a99", "#a32322"])


def apply() -> None:
    plt.rcParams.update({
        "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
        "figure.dpi": 110, "savefig.dpi": 200, "savefig.bbox": "tight",
        "font.size": 9, "axes.titlesize": 10, "axes.labelsize": 9,
        "text.color": TEXT, "axes.labelcolor": TEXT_2, "axes.titlecolor": TEXT,
        "xtick.color": TEXT_2, "ytick.color": TEXT_2,
        "axes.edgecolor": MUTED, "axes.linewidth": 0.6,
        "axes.spines.top": False, "axes.spines.right": False,
        "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.5,
        "lines.linewidth": 1.0, "legend.frameon": False,
    })


def footer(fig, text: str) -> None:
    """Small provenance line along the bottom of a figure."""
    fig.text(0.01, -0.01, text, fontsize=6, color=TEXT_2, ha="left", va="top")
