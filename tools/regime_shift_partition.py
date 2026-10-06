import pandas as pd
import json

def partition_data(df: pd.DataFrame) -> tuple:
    df['timestamp_utc'] = pd.to_datetime(df['timestamp_utc'], utc=True)
    df = df.sort_values('timestamp_utc').reset_index(drop=True)
    
    cal_start = pd.to_datetime("2024-08-01T07:00:00Z")
    cal_end = pd.to_datetime("2025-04-30T23:59:59Z")
    
    val_start = pd.to_datetime("2025-05-01T00:00:00Z")
    val_end = pd.to_datetime("2025-06-30T23:59:59Z")
    
    ho_start = pd.to_datetime("2025-07-01T00:00:00Z")
    ho_end = pd.to_datetime("2025-09-01T06:00:00Z")

    cal_df = df[(df['timestamp_utc'] >= cal_start) & (df['timestamp_utc'] <= cal_end)].copy().reset_index(drop=True)
    val_df = df[(df['timestamp_utc'] >= val_start) & (df['timestamp_utc'] <= val_end)].copy().reset_index(drop=True)
    ho_df = df[(df['timestamp_utc'] >= ho_start) & (df['timestamp_utc'] <= ho_end)].copy().reset_index(drop=True)

    manifest = {
        "calibration": {
            "requested_start": cal_start.isoformat(),
            "requested_end": cal_end.isoformat(),
            "actual_start": cal_df['timestamp_utc'].min().isoformat() if not cal_df.empty else None,
            "actual_end": cal_df['timestamp_utc'].max().isoformat() if not cal_df.empty else None,
            "row_count": len(cal_df)
        },
        "validation": {
            "requested_start": val_start.isoformat(),
            "requested_end": val_end.isoformat(),
            "actual_start": val_df['timestamp_utc'].min().isoformat() if not val_df.empty else None,
            "actual_end": val_df['timestamp_utc'].max().isoformat() if not val_df.empty else None,
            "row_count": len(val_df)
        },
        "held_out": {
            "requested_start": ho_start.isoformat(),
            "requested_end": ho_end.isoformat(),
            "actual_start": ho_df['timestamp_utc'].min().isoformat() if not ho_df.empty else None,
            "actual_end": ho_df['timestamp_utc'].max().isoformat() if not ho_df.empty else None,
            "row_count": len(ho_df)
        }
    }
    
    return cal_df, val_df, ho_df, manifest
