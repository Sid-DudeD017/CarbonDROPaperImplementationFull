import pandas as pd
import hashlib

def main():
    file_path = "/Users/siddharthbhakta/phase13_real_data_worktree/data/phase13/processed/grid_normalized.csv"
    
    # Checksum
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            sha256.update(chunk)
    checksum = sha256.hexdigest()

    df = pd.read_csv(file_path)
    
    # timestamps
    df['timestamp_utc'] = pd.to_datetime(df['timestamp_utc'])
    
    print("Columns:", list(df.columns))
    print("Row count:", len(df))
    print("Min timestamp:", df['timestamp_utc'].min())
    print("Max timestamp:", df['timestamp_utc'].max())
    
    freq = df['timestamp_utc'].diff().mode()[0]
    print("Timestamp frequency:", freq)
    
    dups = df['timestamp_utc'].duplicated().sum()
    print("Duplicated timestamps:", dups)
    
    # Missing timestamps
    expected_range = pd.date_range(start=df['timestamp_utc'].min(), end=df['timestamp_utc'].max(), freq='1h')
    missing_ts = len(expected_range) - len(df['timestamp_utc'].unique())
    print("Missing timestamps (vs hourly index):", missing_ts)
    
    missing_vals = df.isnull().sum().to_dict()
    print("Missing values per column:", missing_vals)
    
    print("Site IDs:", df['site_id'].unique())
    print("Monotonic timestamps:", df['timestamp_utc'].is_monotonic_increasing)
    print("Checksum SHA-256:", checksum)

if __name__ == "__main__":
    main()
