import pandas as pd
import numpy as np

def validate_scenario(scen: dict, base_df: pd.DataFrame) -> dict:
    errors = []
    
    # row count
    if len(scen['timestamp_utc']) != len(base_df):
        errors.append("Row count mismatch")
        
    # timestamp exact match
    if not (scen['timestamp_utc'].values == base_df['timestamp_utc'].values).all():
        errors.append("Timestamps mismatch base")
        
    # site id match
    if not (scen['site_id'].values == base_df['site_id'].values).all():
        errors.append("Site IDs changed")
        
    tau_exact = scen['tau_exact']
    if tau_exact not in list(scen['timestamp_utc']):
        errors.append("Tau not in timestamp index")
        
    tau_idx = scen['timestamp_utc'][scen['timestamp_utc'] == tau_exact].index[0]
    
    # Pre-tau invariance
    if not np.allclose(scen['shifted_carbon_kg_per_kwh'].iloc[:tau_idx], base_df['carbon_kg_per_kwh'].iloc[:tau_idx]):
        errors.append("Carbon pre-tau changed")
        
    if not np.allclose(scen['shifted_price_usd_per_kwh'].iloc[:tau_idx], base_df['price_usd_per_kwh'].iloc[:tau_idx]):
        errors.append("Price pre-tau changed")
        
    # Unaffected field invariance
    if not scen['affected_carbon']:
        if not np.allclose(scen['shifted_carbon_kg_per_kwh'], base_df['carbon_kg_per_kwh']):
            errors.append("Unaffected carbon changed")
            
    if not scen['affected_price']:
        if not np.allclose(scen['shifted_price_usd_per_kwh'], base_df['price_usd_per_kwh']):
            errors.append("Unaffected price changed")
            
    return {
        "scenario_id": scen['scenario_id'],
        "valid": len(errors) == 0,
        "errors": errors
    }

def validate_all(scenarios, base_df):
    results = []
    all_valid = True
    for s in scenarios:
        res = validate_scenario(s, base_df)
        results.append(res)
        if not res["valid"]:
            all_valid = False
            
    return all_valid, results
