"""Schematic of the Min-Stoughton point matrix and the Nakazima D / R_out
transformation. Original drawing adapted from Min et al. (2017), generated for
the report so no copyrighted figure is reproduced.

Run from the report/img directory:
    python3 make_ms_matrix_fig.py
"""

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import FancyArrowPatch, Rectangle

plt.rcParams.update({
    "font.size": 11,
    "mathtext.fontset": "cm",
    "axes.linewidth": 0.8,
})

fig, (axL, axR) = plt.subplots(1, 2, figsize=(10, 4.2))

# ---------------------------------------------------------------------------
# Panel (a): point matrix on the neck band
# ---------------------------------------------------------------------------
N_X, N_Y = 5, 9          # columns across band, points along band
dX, dY = 1.0, 1.0
xs = (np.arange(N_X) - (N_X - 1) / 2) * dX
ys = (np.arange(N_Y) - (N_Y - 1) / 2) * dY
XX, YY = np.meshgrid(xs, ys)

# faint specimen / band background
axL.add_patch(Rectangle((-4.5, -5.5), 9, 11, facecolor="0.95",
                        edgecolor="none", zorder=0))

# crack / neck line (orientation of the band, along Y)
axL.plot([0, 0], [-5.2, 5.2], color="0.55", lw=1.4, ls="--", zorder=1)
axL.text(0.15, 5.0, "crack / neck line", color="0.4", fontsize=9, rotation=90,
         va="top", ha="left")

# matrix points, one column highlighted
for j in range(N_X):
    col_color = "#c1121f" if j == N_X // 2 else "#1d3557"
    axL.scatter(XX[:, j], YY[:, j], s=24, color=col_color, zorder=3)

# neck centre O
axL.scatter([0], [0], s=70, facecolor="white", edgecolor="#c1121f",
            linewidth=1.8, zorder=4)
axL.annotate("$O$ (neck centre)", (0, 0), (1.4, 0.6),
             fontsize=10, color="#c1121f",
             arrowprops=dict(arrowstyle="->", color="#c1121f", lw=1.0))

# W_X dimension (across band)
y0 = -5.0
axL.add_patch(FancyArrowPatch((xs[0], y0), (xs[-1], y0),
              arrowstyle="<->", mutation_scale=12, color="black", lw=1.0))
axL.text(0, y0 - 0.45, "$W_X$  ($N_X$ columns)", ha="center", va="top")

# W_Y dimension (along band)
x0 = -4.0
axL.add_patch(FancyArrowPatch((x0, ys[0]), (x0, ys[-1]),
              arrowstyle="<->", mutation_scale=12, color="black", lw=1.0))
axL.text(x0 - 0.3, 0, "$W_Y$  ($N_Y$ points)", ha="right", va="center",
         rotation=90)

# grid-spacing callout
axL.add_patch(FancyArrowPatch((xs[2], ys[5]), (xs[3], ys[5]),
              arrowstyle="<->", mutation_scale=8, color="0.3", lw=0.8))
axL.text(xs[2] + 0.5, ys[5] + 0.25, "$d_X$", fontsize=9, color="0.3")

axL.set_title("(a) Point matrix on the neck band")
axL.set_xlim(-5.2, 5.2)
axL.set_ylim(-6.2, 5.8)
axL.set_aspect("equal")
axL.axis("off")

# ---------------------------------------------------------------------------
# Panel (b): Nakazima D / R_out transformation
# ---------------------------------------------------------------------------
R = 4.0                       # punch radius (schematic)
Oc = np.array([0.0, -0.4])    # punch centre O'
th = np.linspace(np.deg2rad(55), np.deg2rad(125), 200)
arc = np.c_[Oc[0] + R * np.cos(th), Oc[1] + R * np.sin(th)]

# dome surface with a small local dimple near the apex
apex_th = np.deg2rad(90)
dimple = -0.45 * np.exp(-((th - apex_th) ** 2) / (2 * np.deg2rad(7) ** 2))
surf = np.c_[Oc[0] + (R + dimple) * np.cos(th),
             Oc[1] + (R + dimple) * np.sin(th)]

axR.plot(arc[:, 0], arc[:, 1], color="0.7", lw=1.2, ls="--",
         label="ideal dome (punch)")
axR.plot(surf[:, 0], surf[:, 1], color="#1d3557", lw=2.0,
         label="measured surface")

# punch centre O'
axR.scatter(*Oc, s=45, color="black", zorder=5)
axR.text(Oc[0] + 0.12, Oc[1] - 0.05, "$O'$ (punch centre)", fontsize=10,
         va="top")

# sample a DIC point on the surface, show R_out and D
ip = np.argmin(np.abs(th - np.deg2rad(108)))
P = surf[ip]
axR.scatter(*P, s=35, color="#c1121f", zorder=6)
axR.add_patch(FancyArrowPatch(tuple(Oc), tuple(P), arrowstyle="->",
              mutation_scale=12, color="#c1121f", lw=1.2))
mid = (Oc + P) / 2
axR.text(mid[0] - 0.15, mid[1] + 0.15, "$R_{\\mathrm{out}}$", color="#c1121f",
         fontsize=11, ha="right")

# D = arc length along the surface from the apex to P
apex_idx = np.argmin(np.abs(th - apex_th))
lo, hi = sorted((apex_idx, ip))
axR.plot(surf[lo:hi + 1, 0], surf[lo:hi + 1, 1], color="#2a9d8f", lw=4,
         alpha=0.6, solid_capstyle="round")
axR.text(surf[(lo + hi) // 2, 0] - 0.1, surf[(lo + hi) // 2, 1] + 0.35,
         "$D$ (arc length)", color="#2a9d8f", fontsize=10, ha="center")

# apex / pole marker
axR.scatter(*surf[apex_idx], s=30, facecolor="white", edgecolor="#1d3557",
            zorder=6)
axR.text(surf[apex_idx, 0], surf[apex_idx, 1] + 0.2, "pole", fontsize=9,
         ha="center", va="bottom", color="#1d3557")

axR.set_title("(b) Nakazima coordinates $D$ and $R_{\\mathrm{out}}$")
axR.set_aspect("equal")
axR.set_xlim(-3.6, 3.6)
axR.set_ylim(-1.2, 4.4)
axR.axis("off")
axR.legend(loc="upper left", fontsize=8.5, frameon=False, ncol=1)

fig.tight_layout()
fig.savefig("ms_point_matrix.pdf", bbox_inches="tight")
fig.savefig("ms_point_matrix.png", dpi=200, bbox_inches="tight")
print("wrote ms_point_matrix.pdf and ms_point_matrix.png")
