import os
import requests
import json
try:
    from dotenv import load_dotenv
except ImportError:
    pass

def run_diagnostic():
    try:
        load_dotenv()
    except Exception:
        # manual parsing if dotenv fails
        with open(".env") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ[k.strip()] = v.strip()

    username = os.getenv("WATTTIME_USERNAME")
    password = os.getenv("WATTTIME_PASSWORD")

    if not username or not password:
        return {"status": "error", "message": "No credentials"}

    login_url = "https://api.watttime.org/login"
    resp = requests.get(login_url, auth=(username, password))
    if resp.status_code != 200:
        return {"status": "error", "message": f"Login failed: {resp.status_code}"}

    token = resp.json().get("token")
    headers = {"Authorization": f"Bearer {token}"}

    # my-access
    access_url = "https://api.watttime.org/v3/my-access"
    access_resp = requests.get(access_url, headers=headers)
    
    diagnostic = {
        "status": "success",
        "authorized_models": [],
        "historical_access": None,
        "ca_north_access": False
    }

    if access_resp.status_code == 200:
        access_data = access_resp.json()
        signal_types = access_data.get("signal_types", [])
        
        # Check if co2_moer in CAISO_NORTH is accessible historically
        # The /my-access endpoint returns regions and endpoints.
        # Format varies, just store summarized data safely.
        diagnostic["metadata_summary"] = str(access_data)[:500] # Safe snippet
    else:
        diagnostic["my_access_status"] = access_resp.status_code

    # test bounded requests
    test_dates = ["2025-08-05", "2021-01-01"]
    hist_url = "https://api.watttime.org/v3/historical"
    
    diagnostic["tests"] = {}
    for d in test_dates:
        params = {
            "region": "CAISO_NORTH",
            "start": f"{d}T07:00:00Z",
            "end": f"{d}T08:00:00Z",
            "signal_type": "co2_moer"
        }
        r = requests.get(hist_url, headers=headers, params=params)
        count = len(r.json().get("data", [])) if r.status_code == 200 else 0
        diagnostic["tests"][d] = {
            "status": r.status_code,
            "record_count": count
        }
        
    return diagnostic

if __name__ == "__main__":
    res = run_diagnostic()
    out_path = "artifacts/regime_shift/watttime_access_report.json"
    os.makedirs("artifacts/regime_shift", exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(res, f, indent=2)
