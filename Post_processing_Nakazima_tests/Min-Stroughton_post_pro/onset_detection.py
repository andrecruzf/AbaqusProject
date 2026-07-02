#!/usr/bin/env python3
"""Step 7: Objective onset detection from C_pm(t).

Implements the Min-Stoughton persistence criterion: onset at frame K if
C_pm(k) > C_pm_P(k) + Delta for n consecutive frames k = K..K+n-1.

Paper reference:
    Min et al. (2017), Sec. 2.1 / p.245:
    "when C_pm(K) - C_pm_P(K) is larger than a threshold value of Delta
     at the following n consecutive frames, namely,
         C_pm(k) > C_pm_P(k) + Delta
     (K <= k <= K + n - 1), the K-th frame is considered as the crucial
     frame associated with the onset of localized necking"

    where:
        C_pm_P(K) = linear regression of C_pm(l) for M+1 <= l <= K-1
        Delta = SAC / 10
        n = 8

Usage:
    from onset_detection import OnsetConfig, detect_onset

    result = detect_onset(signal)
    print(result.report())
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

import numpy as np

from circle_fitting import CurvatureSignal


# ---------------------------------------------------------------------------
#  Configuration
# ---------------------------------------------------------------------------

@dataclass
class OnsetConfig:
    """Configuration for onset detection."""

    # Number of consecutive frames required above threshold
    n_consecutive: int = 8

    # Threshold Delta [1/mm].  None = k_SAC / 10 (paper default).
    delta: Optional[float] = None

    # Minimum number of baseline frames before a candidate can be tested
    min_baseline_frames: int = 8

    # Regression variable: "time" (physical seconds) or "index" (frame count)
    regression_variable: str = "time"


# ---------------------------------------------------------------------------
#  Result container
# ---------------------------------------------------------------------------

@dataclass
class OnsetDetectionResult:
    """Result of the persistence-based onset detection."""

    # --- Detection outcome ---
    onset_found: bool
    reason: str                        # "ok", "insufficient_frames", etc.

    # --- Onset location (None if not found) ---
    onset_fit_index: Optional[int]     # index into CurvatureSignal arrays
    onset_global_frame_index: Optional[int]  # index into full DIC time axis
    onset_frame_id: Optional[int]
    onset_time: Optional[float]

    # --- Values at onset ---
    C_pm_at_onset: float               # C_pm[K]
    C_pm_predicted_at_onset: float     # C_pm_P[K]
    margin_at_onset: float             # C_pm[K] - C_pm_P[K] - Delta

    # --- Configuration used ---
    delta: float                       # threshold Delta [1/mm]
    n_consecutive: int
    k_SAC: float

    # --- Diagnostic arrays (n_fit,) ---
    C_pm: np.ndarray                   # raw C_pm
    C_pm_predicted: np.ndarray         # C_pm_P from rolling regression
    threshold_curve: np.ndarray        # C_pm_P + Delta
    exceedance: np.ndarray             # bool: C_pm > threshold
    consecutive_count: np.ndarray      # running count of consecutive exceedances
    time: np.ndarray
    frame_ids: np.ndarray

    # --- Quality indicators ---
    max_exceedance_margin: float       # max(C_pm - threshold) over all frames
    n_frames_above_after_onset: int    # how many frames stay above after K
    MSR_pm_at_onset: float
    MSR_pm_change_near_onset: float    # MSR[K] / median(MSR[before K])
    C_pm_std_at_onset: float           # cross-column std at onset

    # --- Source ---
    signal: CurvatureSignal

    warnings: List[str] = field(default_factory=list)

    def report(self) -> str:
        lines = [
            f"OnsetDetectionResult",
            f"",
            f"  onset found:              {self.onset_found}",
        ]
        if self.onset_found:
            lines += [
                f"  onset frame:              {self.onset_frame_id} "
                f"(fit index {self.onset_fit_index})",
                f"  onset time:               {self.onset_time:.3f} s",
                f"  C_pm at onset:            {self.C_pm_at_onset:.6f} mm^-1",
                f"  C_pm_P at onset:          {self.C_pm_predicted_at_onset:.6f} mm^-1",
                f"  margin (C_pm-C_pm_P-D):   {self.margin_at_onset:.6f} mm^-1",
                f"  frames above after onset: {self.n_frames_above_after_onset}",
                f"  MSR at onset:             {self.MSR_pm_at_onset:.2e}",
                f"  MSR change at onset:      {self.MSR_pm_change_near_onset:.2f}x",
                f"  C_pm_std at onset:        {self.C_pm_std_at_onset:.6f}",
            ]
        else:
            lines += [
                f"  reason:                   {self.reason}",
            ]
        lines += [
            f"",
            f"  delta (threshold):        {self.delta:.2e} mm^-1",
            f"  n_consecutive:            {self.n_consecutive}",
            f"  k_SAC:                    {self.k_SAC:.2e} mm^-1",
            f"  max exceedance margin:    {self.max_exceedance_margin:.6f} mm^-1",
            f"",
            f"  warnings:                 "
            f"{', '.join(self.warnings) if self.warnings else 'none'}",
        ]
        return "\n".join(lines)

    def __repr__(self) -> str:
        if self.onset_found:
            return (
                f"OnsetDetectionResult(onset=frame {self.onset_frame_id}, "
                f"t={self.onset_time:.3f}s)"
            )
        return f"OnsetDetectionResult(onset_found=False, reason='{self.reason}')"


# ---------------------------------------------------------------------------
#  Plotting helper
# ---------------------------------------------------------------------------

def plot_onset(result: OnsetDetectionResult, path: str, title: str = "") -> None:
    """Save a two-panel diagnostic plot (raw + corrected) of C_pm onset.

    Left panel:  raw convention  (C_pm includes SAC offset)
    Right panel: corrected       (C_pm − SAC, starts near 0)

    Both panels use a single consistent convention per panel.
    The detection itself operates in raw space; the corrected panel
    simply subtracts k_SAC from all three curves.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    t = result.time
    cpm_raw = result.C_pm
    pred_raw = result.C_pm_predicted
    thresh_raw = result.threshold_curve
    exc = result.exceedance
    k_SAC = result.k_SAC

    # --- Assertion: every exceedance marker must satisfy cpm > thresh ---
    exc_valid = exc & np.isfinite(cpm_raw) & np.isfinite(thresh_raw)
    if exc_valid.any():
        assert np.all(cpm_raw[exc_valid] > thresh_raw[exc_valid]), (
            "Plot inconsistency: exceedance markers where "
            "C_pm <= threshold. Check convention (raw vs corrected)."
        )

    # Corrected arrays (subtract SAC from all three curves consistently)
    cpm_corr = cpm_raw - k_SAC
    pred_corr = pred_raw - k_SAC
    thresh_corr = thresh_raw - k_SAC

    # Corrected assertion (algebraically identical, but verify)
    if exc_valid.any():
        assert np.all(cpm_corr[exc_valid] > thresh_corr[exc_valid]), (
            "Corrected plot inconsistency."
        )

    finite_cpm = np.isfinite(cpm_raw)
    finite_pred = np.isfinite(pred_raw)
    finite_thresh = np.isfinite(thresh_raw)
    sig = result.signal

    fig, (ax_raw, ax_corr) = plt.subplots(1, 2, figsize=(14, 4.5))

    # ── Left panel: raw ─────────────────────────────────────────────
    ax_raw.plot(t[finite_cpm], cpm_raw[finite_cpm], "o-", ms=3, lw=1,
                color="black", label=r"$C_{pm}$ raw")
    if finite_pred.any():
        ax_raw.plot(t[finite_pred], pred_raw[finite_pred], "o", ms=2.5,
                    color="tab:blue", label=r"$C_{pm,P}$ raw")
    if finite_thresh.any():
        ax_raw.plot(t[finite_thresh], thresh_raw[finite_thresh], ":", lw=1.2,
                    color="tab:blue", label=r"$C_{pm,P}$ raw $+ \Delta$")
    if exc_valid.any():
        ax_raw.scatter(t[exc_valid], cpm_raw[exc_valid], s=20, color="red",
                       zorder=4, label="above threshold")
    if result.onset_found:
        ax_raw.axvline(result.onset_time, ls="--", lw=1.2, color="red",
                       label=f"onset (frame {result.onset_frame_id})")
    ax_raw.set_xlabel("Time [s]")
    ax_raw.set_ylabel(r"$C_{pm}$ raw [mm$^{-1}$]")
    ax_raw.legend(fontsize=7, loc="upper left")
    ax_raw.grid(True, alpha=0.3)
    ax_raw.set_title("raw (incl. SAC offset)")

    # MSR on twin axis
    ax_msr = ax_raw.twinx()
    msr = sig.MSR_pm
    finite_msr = np.isfinite(msr)
    if finite_msr.any():
        ax_msr.plot(sig.time[finite_msr], msr[finite_msr], "-", lw=0.8,
                    color="darkred", alpha=0.4)
        ax_msr.set_ylabel(r"MSR [mm$^2$]", color="darkred", fontsize=8)
        ax_msr.tick_params(axis="y", labelcolor="darkred", labelsize=7)

    # ── Right panel: corrected ──────────────────────────────────────
    ax_corr.plot(t[finite_cpm], cpm_corr[finite_cpm], "o-", ms=3, lw=1,
                 color="black", label=r"$C_{pm}$ corrected")
    if finite_pred.any():
        ax_corr.plot(t[finite_pred], pred_corr[finite_pred], "o", ms=2.5,
                     color="tab:blue", label=r"$C_{pm,P}$ corrected")
    if finite_thresh.any():
        ax_corr.plot(t[finite_thresh], thresh_corr[finite_thresh], ":", lw=1.2,
                     color="tab:blue",
                     label=r"$C_{pm,P}$ corrected $+ \Delta$")
    if exc_valid.any():
        ax_corr.scatter(t[exc_valid], cpm_corr[exc_valid], s=20, color="red",
                        zorder=4, label="above threshold")
    if result.onset_found:
        ax_corr.axvline(result.onset_time, ls="--", lw=1.2, color="red",
                        label=f"onset (frame {result.onset_frame_id})")
    ax_corr.axhline(0, ls="-", lw=0.5, color="gray", alpha=0.5)
    ax_corr.set_xlabel("Time [s]")
    ax_corr.set_ylabel(r"$C_{pm} - k_{\mathrm{SAC}}$ [mm$^{-1}$]")
    ax_corr.legend(fontsize=7, loc="upper left")
    ax_corr.grid(True, alpha=0.3)
    ax_corr.set_title(f"corrected (SAC = {k_SAC:.1e} removed)")

    if title:
        fig.suptitle(title, fontsize=11, y=1.02)

    fig.tight_layout()
    fig.savefig(path, dpi=200, bbox_inches="tight")
    plt.close(fig)


# ---------------------------------------------------------------------------
#  Rolling linear regression
# ---------------------------------------------------------------------------

def _rolling_regression(
    x: np.ndarray,
    y: np.ndarray,
    min_points: int,
) -> tuple:
    """For each index k, fit y = a*x + b using points 0..k-1.

    Returns
    -------
    predicted : (n,) predicted y[k] from regression on 0..k-1
    """
    n = len(x)
    predicted = np.full(n, np.nan)

    for k in range(min_points, n):
        x_hist = x[:k]
        y_hist = y[:k]
        ok = np.isfinite(x_hist) & np.isfinite(y_hist)
        if np.count_nonzero(ok) < min_points:
            continue
        try:
            coeffs = np.polyfit(x_hist[ok], y_hist[ok], 1)
            predicted[k] = float(np.polyval(coeffs, x[k]))
        except (np.linalg.LinAlgError, ValueError):
            continue

    return predicted


# ---------------------------------------------------------------------------
#  Consecutive exceedance counter
# ---------------------------------------------------------------------------

def _consecutive_count(exc: np.ndarray) -> np.ndarray:
    """For each index, count how many consecutive True values starting there."""
    n = len(exc)
    count = np.zeros(n, dtype=int)
    # Work backwards
    if n == 0:
        return count
    if exc[-1]:
        count[-1] = 1
    for i in range(n - 2, -1, -1):
        if exc[i]:
            count[i] = count[i + 1] + 1
        else:
            count[i] = 0
    return count


# ---------------------------------------------------------------------------
#  Main entry point
# ---------------------------------------------------------------------------

def detect_onset(
    signal: CurvatureSignal,
    cfg: Optional[OnsetConfig] = None,
) -> OnsetDetectionResult:
    """Detect necking onset using the Min-Stoughton persistence criterion.

    Parameters
    ----------
    signal : CurvatureSignal
        Output of compute_curvature_signal() (Step 6).
    cfg : OnsetConfig, optional

    Returns
    -------
    OnsetDetectionResult with onset frame (if found) and diagnostics.
    """
    if cfg is None:
        cfg = OnsetConfig()

    warnings: List[str] = []

    k_SAC = signal.k_SAC
    delta = cfg.delta if cfg.delta is not None else k_SAC / 10.0
    n_con = cfg.n_consecutive

    cpm = signal.C_pm.copy()
    t = signal.time.copy()
    n_fit = len(cpm)

    # --- Check we have enough frames ---
    finite_mask = np.isfinite(cpm) & np.isfinite(t)
    n_finite = int(np.count_nonzero(finite_mask))

    if n_finite < cfg.min_baseline_frames + n_con:
        return _no_onset(
            signal, cpm, t, delta, n_con, k_SAC,
            reason="insufficient_frames",
            warnings=[f"Only {n_finite} finite C_pm values, need "
                      f"{cfg.min_baseline_frames + n_con}"],
        )

    # --- Regression variable ---
    if cfg.regression_variable == "time":
        x_var = t
    else:
        x_var = np.arange(n_fit, dtype=float)

    # --- Rolling linear regression ---
    predicted = _rolling_regression(x_var, cpm, cfg.min_baseline_frames)

    # --- Threshold and exceedance ---
    threshold = predicted + delta
    exceedance = np.isfinite(cpm) & np.isfinite(threshold) & (cpm > threshold)
    consec = _consecutive_count(exceedance)

    # --- Find first frame with n_con consecutive exceedances ---
    onset_fit_idx = None
    for i in range(n_fit):
        if consec[i] >= n_con:
            onset_fit_idx = i
            break

    if onset_fit_idx is None:
        if np.any(exceedance):
            reason = "no_sustained_exceedance"
            max_consec = int(consec.max())
            warnings.append(
                f"Max consecutive exceedance: {max_consec} "
                f"(need {n_con})"
            )
        else:
            reason = "no_exceedance"
        return _no_onset(
            signal, cpm, t, delta, n_con, k_SAC,
            reason=reason,
            warnings=warnings,
            predicted=predicted,
            threshold=threshold,
            exceedance=exceedance,
            consec=consec,
        )

    # --- Onset found ---
    onset_global_idx = int(signal.frame_indices[onset_fit_idx])
    onset_frame_id = int(signal.frame_ids[onset_fit_idx])
    onset_time = float(t[onset_fit_idx])
    cpm_at = float(cpm[onset_fit_idx])
    pred_at = float(predicted[onset_fit_idx])
    margin_at = cpm_at - pred_at - delta

    # Count how many frames stay above after onset
    n_above_after = int(np.sum(exceedance[onset_fit_idx:]))

    # MSR at onset
    msr_at = float(signal.MSR_pm[onset_fit_idx]) if np.isfinite(signal.MSR_pm[onset_fit_idx]) else 0.0

    # MSR change: ratio of MSR at onset to median MSR before onset
    msr_before = signal.MSR_pm[:onset_fit_idx]
    msr_before_finite = msr_before[np.isfinite(msr_before)]
    if len(msr_before_finite) > 0 and np.median(msr_before_finite) > 0:
        msr_change = msr_at / float(np.median(msr_before_finite))
    else:
        msr_change = 1.0

    # C_pm_std at onset
    cpm_std_at = float(signal.C_pm_std[onset_fit_idx]) if np.isfinite(signal.C_pm_std[onset_fit_idx]) else 0.0

    # Max exceedance margin
    margins = cpm - threshold
    max_margin = float(np.nanmax(margins[np.isfinite(margins)])) if np.any(np.isfinite(margins)) else 0.0

    return OnsetDetectionResult(
        onset_found=True,
        reason="ok",
        onset_fit_index=onset_fit_idx,
        onset_global_frame_index=onset_global_idx,
        onset_frame_id=onset_frame_id,
        onset_time=onset_time,
        C_pm_at_onset=cpm_at,
        C_pm_predicted_at_onset=pred_at,
        margin_at_onset=margin_at,
        delta=delta,
        n_consecutive=n_con,
        k_SAC=k_SAC,
        C_pm=cpm,
        C_pm_predicted=predicted,
        threshold_curve=threshold,
        exceedance=exceedance,
        consecutive_count=consec,
        time=t,
        frame_ids=signal.frame_ids,
        max_exceedance_margin=max_margin,
        n_frames_above_after_onset=n_above_after,
        MSR_pm_at_onset=msr_at,
        MSR_pm_change_near_onset=msr_change,
        C_pm_std_at_onset=cpm_std_at,
        signal=signal,
        warnings=warnings,
    )


def _no_onset(
    signal, cpm, t, delta, n_con, k_SAC,
    reason, warnings,
    predicted=None, threshold=None, exceedance=None, consec=None,
) -> OnsetDetectionResult:
    """Build a no-onset result."""
    n = len(cpm)
    if predicted is None:
        predicted = np.full(n, np.nan)
    if threshold is None:
        threshold = np.full(n, np.nan)
    if exceedance is None:
        exceedance = np.zeros(n, dtype=bool)
    if consec is None:
        consec = np.zeros(n, dtype=int)

    margins = cpm - threshold
    finite_margins = margins[np.isfinite(margins)]
    max_margin = float(np.nanmax(finite_margins)) if len(finite_margins) > 0 else 0.0

    return OnsetDetectionResult(
        onset_found=False,
        reason=reason,
        onset_fit_index=None,
        onset_global_frame_index=None,
        onset_frame_id=None,
        onset_time=None,
        C_pm_at_onset=float("nan"),
        C_pm_predicted_at_onset=float("nan"),
        margin_at_onset=float("nan"),
        delta=delta,
        n_consecutive=n_con,
        k_SAC=k_SAC,
        C_pm=cpm,
        C_pm_predicted=predicted,
        threshold_curve=threshold,
        exceedance=exceedance,
        consecutive_count=consec,
        time=t,
        frame_ids=signal.frame_ids,
        max_exceedance_margin=max_margin,
        n_frames_above_after_onset=0,
        MSR_pm_at_onset=float("nan"),
        MSR_pm_change_near_onset=float("nan"),
        C_pm_std_at_onset=float("nan"),
        signal=signal,
        warnings=warnings,
    )

