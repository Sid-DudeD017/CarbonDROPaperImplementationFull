import numpy as np
import pandas as pd
import ruptures as rpt
from typing import Dict, List, Tuple, Any, Optional

def apply_abrupt_mean_shift(series: pd.Series, tau_idx: int, delta: float) -> pd.Series:
    shifted = series.copy()
    shifted.iloc[tau_idx:] = shifted.iloc[tau_idx:] * (1.0 + delta)
    return shifted

def apply_variance_shift(series: pd.Series, tau_idx: int, alpha: float, pre_mean: float, non_negative: bool = False) -> Tuple[pd.Series, int]:
    shifted = series.copy()
    shifted_part = pre_mean + alpha * (shifted.iloc[tau_idx:] - pre_mean)
    clipped_count = 0
    if non_negative:
        clipped_count = (shifted_part < 0).sum()
        shifted_part = shifted_part.clip(lower=0.0)
    shifted.iloc[tau_idx:] = shifted_part
    return shifted, clipped_count

def apply_gradual_drift(series: pd.Series, tau_idx: int, duration: int, delta: float) -> pd.Series:
    shifted = series.copy()
    n_post = len(series) - tau_idx
    ramp = np.linspace(0, delta, num=min(duration, n_post))
    
    ramp_full = np.zeros(n_post)
    ramp_full[:len(ramp)] = ramp
    if len(ramp_full) > len(ramp):
        ramp_full[len(ramp):] = delta
        
    shifted.iloc[tau_idx:] = shifted.iloc[tau_idx:] * (1.0 + ramp_full)
    return shifted

def apply_recurring_shift(series: pd.Series, tau_idx: int, delta: float, period: int = 72) -> Tuple[pd.Series, List[int]]:
    shifted = series.copy()
    transitions = [tau_idx]
    
    current_idx = tau_idx
    shift_on = True
    while current_idx < len(series):
        end_idx = min(current_idx + period, len(series))
        if shift_on:
            shifted.iloc[current_idx:end_idx] = shifted.iloc[current_idx:end_idx] * (1.0 + delta)
        
        current_idx += period
        shift_on = not shift_on
        if current_idx < len(series):
            transitions.append(current_idx)
            
    return shifted, transitions

def run_pelt(series: np.ndarray, pen: float = 10.0) -> Optional[int]:
    algo = rpt.Pelt(model="l2", min_size=24).fit(series)
    try:
        result = algo.predict(pen=pen)
        if len(result) > 1:
            return result[0]
        return None
    except Exception:
        return None

def run_cusum(series: np.ndarray, threshold: float = 5.0, drift: float = 0.5) -> Optional[int]:
    # Use first 24 points as baseline
    baseline = series[:24] if len(series) >= 24 else series
    mean_val = np.mean(baseline)
    std_val = np.std(baseline)
    if std_val == 0: std_val = 1.0
    
    z = (series - mean_val) / std_val
    pos_sum, neg_sum = 0.0, 0.0
    
    for i in range(24, len(z)):
        val = z[i]
        pos_sum = max(0, pos_sum + val - drift)
        neg_sum = max(0, neg_sum - val - drift)
        
        if pos_sum > threshold or neg_sum > threshold:
            return i
            
    return None

def compute_wasserstein_1(a: np.ndarray, b: np.ndarray) -> float:
    from scipy.stats import wasserstein_distance
    return wasserstein_distance(a, b)
