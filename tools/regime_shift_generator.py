import pandas as pd
import numpy as np
from typing import List, Dict, Any
from tools.regime_shift_core import (
    apply_abrupt_mean_shift,
    apply_variance_shift,
    apply_gradual_drift,
    apply_recurring_shift
)

def generate_controlled_scenarios(ho_df: pd.DataFrame, cal_df: pd.DataFrame) -> List[Dict[str, Any]]:
    scenarios = []
    
    n_ho = len(ho_df)
    taus = {
        "25%": int(0.25 * n_ho),
        "50%": int(0.50 * n_ho),
        "75%": int(0.75 * n_ho)
    }
    
    # Pre-compute calibration means for variance shifts
    cal_carbon_mean = cal_df['carbon_kg_per_kwh'].mean()
    cal_price_mean = cal_df['price_usd_per_kwh'].mean()

    # Shift types:
    # A. Abrupt carbon mean: +0.10, +0.20, -0.10
    # B. Abrupt price mean: +0.10, +0.20, -0.10
    # C. Carbon variance: alpha = 1.25, 1.50
    # D. Price variance: alpha = 1.25, 1.50
    # E. Gradual carbon drift: 24h, 168h with +10%, +20%
    # F. Recurring carbon regime: +15% for 72h
    # G. Compound carbon-and-price shift: +10% mean, 1.25 dev for both.

    base_carbon = ho_df['carbon_kg_per_kwh']
    base_price = ho_df['price_usd_per_kwh']

    seed = 42
    
    for pos_name, tau_idx in taus.items():
        tau_ts = ho_df['timestamp_utc'].iloc[tau_idx]
        
        # A. Abrupt carbon mean
        for delta in [0.10, 0.20, -0.10]:
            sid = f"carbon_abrupt_{delta}_{pos_name}_s{seed}"
            scen = _init_scenario(sid, ho_df, tau_ts, pos_name)
            scen['shift_type'] = 'abrupt_mean'
            scen['affected_carbon'] = True
            scen['transformation_parameters'] = {'delta': delta, 'metric': 'carbon'}
            scen['shifted_carbon_kg_per_kwh'] = apply_abrupt_mean_shift(base_carbon, tau_idx, delta)
            scen['shifted_price_usd_per_kwh'] = base_price.copy()
            scenarios.append(scen)
            
        # B. Abrupt price mean
        for delta in [0.10, 0.20, -0.10]:
            sid = f"price_abrupt_{delta}_{pos_name}_s{seed}"
            scen = _init_scenario(sid, ho_df, tau_ts, pos_name)
            scen['shift_type'] = 'abrupt_mean'
            scen['affected_price'] = True
            scen['transformation_parameters'] = {'delta': delta, 'metric': 'price'}
            scen['shifted_carbon_kg_per_kwh'] = base_carbon.copy()
            scen['shifted_price_usd_per_kwh'] = apply_abrupt_mean_shift(base_price, tau_idx, delta)
            scenarios.append(scen)
            
        # C. Carbon variance
        for alpha in [1.25, 1.50]:
            sid = f"carbon_var_{alpha}_{pos_name}_s{seed}"
            scen = _init_scenario(sid, ho_df, tau_ts, pos_name)
            scen['shift_type'] = 'variance'
            scen['affected_carbon'] = True
            scen['transformation_parameters'] = {'alpha': alpha, 'metric': 'carbon'}
            scen['shifted_carbon_kg_per_kwh'], clipped = apply_variance_shift(base_carbon, tau_idx, alpha, cal_carbon_mean, True)
            scen['shifted_price_usd_per_kwh'] = base_price.copy()
            scen['transformation_parameters']['clipped_count'] = int(clipped)
            scenarios.append(scen)
            
        # D. Price variance
        for alpha in [1.25, 1.50]:
            sid = f"price_var_{alpha}_{pos_name}_s{seed}"
            scen = _init_scenario(sid, ho_df, tau_ts, pos_name)
            scen['shift_type'] = 'variance'
            scen['affected_price'] = True
            scen['transformation_parameters'] = {'alpha': alpha, 'metric': 'price'}
            scen['shifted_carbon_kg_per_kwh'] = base_carbon.copy()
            scen['shifted_price_usd_per_kwh'], _ = apply_variance_shift(base_price, tau_idx, alpha, cal_price_mean, False)
            scenarios.append(scen)
            
        # E. Gradual carbon drift
        for duration in [24, 168]:
            for delta in [0.10, 0.20]:
                sid = f"carbon_gradual_{duration}h_{delta}_{pos_name}_s{seed}"
                scen = _init_scenario(sid, ho_df, tau_ts, pos_name)
                scen['shift_type'] = 'gradual_drift'
                scen['affected_carbon'] = True
                scen['transformation_parameters'] = {'duration': duration, 'delta': delta, 'metric': 'carbon'}
                scen['shifted_carbon_kg_per_kwh'] = apply_gradual_drift(base_carbon, tau_idx, duration, delta)
                scen['shifted_price_usd_per_kwh'] = base_price.copy()
                scenarios.append(scen)

        # F. Recurring carbon regime
        sid = f"carbon_recurring_0.15_72h_{pos_name}_s{seed}"
        scen = _init_scenario(sid, ho_df, tau_ts, pos_name)
        scen['shift_type'] = 'recurring'
        scen['affected_carbon'] = True
        scen['shifted_carbon_kg_per_kwh'], transitions = apply_recurring_shift(base_carbon, tau_idx, 0.15, 72)
        scen['shifted_price_usd_per_kwh'] = base_price.copy()
        scen['transformation_parameters'] = {'delta': 0.15, 'period': 72, 'metric': 'carbon', 'transitions': transitions}
        scenarios.append(scen)
        
        # G. Compound
        sid = f"compound_10pct_1.25var_{pos_name}_s{seed}"
        scen = _init_scenario(sid, ho_df, tau_ts, pos_name)
        scen['shift_type'] = 'compound'
        scen['affected_carbon'] = True
        scen['affected_price'] = True
        scen['transformation_parameters'] = {
            'carbon_delta': 0.10, 'carbon_alpha': 1.25,
            'price_delta': 0.10, 'price_alpha': 1.25,
            'order': ['mean_shift', 'variance_shift']
        }
        c1 = apply_abrupt_mean_shift(base_carbon, tau_idx, 0.10)
        scen['shifted_carbon_kg_per_kwh'], _ = apply_variance_shift(c1, tau_idx, 1.25, cal_carbon_mean, True)
        p1 = apply_abrupt_mean_shift(base_price, tau_idx, 0.10)
        scen['shifted_price_usd_per_kwh'], _ = apply_variance_shift(p1, tau_idx, 1.25, cal_price_mean, False)
        scenarios.append(scen)
        
    return scenarios

def _init_scenario(sid: str, ho_df: pd.DataFrame, tau_ts: pd.Timestamp, pos_name: str) -> Dict[str, Any]:
    return {
        'scenario_id': sid,
        'tau_exact': tau_ts,
        'tau_pos': pos_name,
        'affected_carbon': False,
        'affected_price': False,
        'timestamp_utc': ho_df['timestamp_utc'].copy(),
        'site_id': ho_df['site_id'].copy(),
        'base_carbon_kg_per_kwh': ho_df['carbon_kg_per_kwh'].copy(),
        'base_price_usd_per_kwh': ho_df['price_usd_per_kwh'].copy(),
        'seed': 42
    }

