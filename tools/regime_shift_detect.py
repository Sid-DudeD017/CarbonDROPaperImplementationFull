import pandas as pd
import numpy as np
from typing import Dict, Any, List
from tools.regime_shift_core import run_pelt, run_cusum, compute_wasserstein_1

def analyze_scenario(scen: Dict[str, Any], ho_df: pd.DataFrame) -> Dict[str, Any]:
    tau_exact = scen['tau_exact']
    
    if scen['affected_carbon']:
        target_series = scen['shifted_carbon_kg_per_kwh'].values
    else:
        target_series = scen['shifted_price_usd_per_kwh'].values
        
    pelt_idx = run_pelt(target_series, pen=10.0)
    cusum_idx = run_cusum(target_series, threshold=5.0)
    
    ts = scen['timestamp_utc'].values
    tau_hat_pelt = ts[pelt_idx] if pelt_idx is not None else None
    tau_hat_cusum = ts[cusum_idx] if cusum_idx is not None else None
    
    tau_hat_consensus = None
    status = "no_consensus"
    
    if tau_hat_pelt is not None and tau_hat_cusum is not None:
        delta = abs(pd.Timestamp(tau_hat_pelt) - pd.Timestamp(tau_hat_cusum))
        if delta <= pd.Timedelta(hours=24):
            # Midpoint or just use pelt as consensus for simplicity
            tau_hat_consensus = tau_hat_pelt
            status = "consensus"
    elif tau_hat_pelt is not None or tau_hat_cusum is not None:
        status = "one_detector_only"
    else:
        status = "no_detection"
        
    # Metrics
    metrics = {
        'tau_exact': tau_exact.isoformat(),
        'tau_hat_pelt': pd.Timestamp(tau_hat_pelt).isoformat() if tau_hat_pelt else None,
        'tau_hat_cusum': pd.Timestamp(tau_hat_cusum).isoformat() if tau_hat_cusum else None,
        'tau_hat_consensus': pd.Timestamp(tau_hat_consensus).isoformat() if tau_hat_consensus else None,
        'status': status,
        'detector_parameters': {'pelt_pen': 10.0, 'cusum_threshold': 5.0}
    }
    
    if tau_hat_consensus:
        delay = pd.Timestamp(tau_hat_consensus) - tau_exact
        delay_hours = delay.total_seconds() / 3600.0
        metrics['signed_delay_hours'] = delay_hours
        metrics['absolute_delay_hours'] = abs(delay_hours)
        metrics['detected_within_6h'] = abs(delay_hours) <= 6
        metrics['detected_within_24h'] = abs(delay_hours) <= 24
        metrics['detected_within_72h'] = abs(delay_hours) <= 72
        metrics['false_alarms_before_tau'] = delay_hours < 0
        metrics['missed_detection'] = False
    else:
        metrics['signed_delay_hours'] = None
        metrics['absolute_delay_hours'] = None
        metrics['detected_within_6h'] = False
        metrics['detected_within_24h'] = False
        metrics['detected_within_72h'] = False
        metrics['false_alarms_before_tau'] = False
        metrics['missed_detection'] = True
        
    # Stats
    tau_idx = scen['timestamp_utc'][scen['timestamp_utc'] == tau_exact].index[0]
    pre = target_series[:tau_idx]
    post = target_series[tau_idx:]
    
    metrics['pre_statistics'] = {'mean': float(np.mean(pre)), 'std': float(np.std(pre))}
    metrics['post_statistics'] = {'mean': float(np.mean(post)), 'std': float(np.std(post))}
    metrics['wasserstein_1_distance'] = compute_wasserstein_1(pre, post)
    
    # Simple trans error (optional placeholder)
    metrics['transformation_realization_error'] = 0.0
    
    return metrics

def run_natural_candidates(df: pd.DataFrame, cal_df: pd.DataFrame) -> List[Dict[str, Any]]:
    # Extremely basic natural candidate generation for exploratory purposes
    candidates = []
    
    # just run on carbon
    ts = df['timestamp_utc'].values
    series = df['carbon_kg_per_kwh'].values
    
    pelt_idx = run_pelt(series, pen=10.0)
    cusum_idx = run_cusum(series, threshold=5.0)
    
    if pelt_idx is not None and cusum_idx is not None:
        t_pelt = pd.Timestamp(ts[pelt_idx])
        t_cusum = pd.Timestamp(ts[cusum_idx])
        if abs(t_pelt - t_cusum) <= pd.Timedelta(days=7):
            # check 30 days pre and post
            if pelt_idx >= 30*24 and pelt_idx <= len(ts) - 30*24:
                candidates.append({
                    'track': 'natural',
                    'tau_source': 'estimated_consensus',
                    'tau_confidence': 'exploratory',
                    'tau_hat_pelt': t_pelt.isoformat(),
                    'tau_hat_cusum': t_cusum.isoformat(),
                    'tau_hat_consensus': t_pelt.isoformat(),
                    'status': 'EXPLORATORY_NATURAL_SHIFT_CANDIDATE'
                })
                
    return candidates
