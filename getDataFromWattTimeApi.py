import os
import requests
from requests.auth import HTTPBasicAuth
from dotenv import load_dotenv

load_dotenv()

# 1. Obtain the Token
login_url = "https://api.watttime.org/login"
auth = HTTPBasicAuth(os.getenv("WATTTIME_USERNAME"), os.getenv("WATTTIME_PASSWORD"))

response = requests.get(login_url, auth=auth)
token = response.json().get("token")

print("--- WATTTIME ACCESS TOKEN OBTAINED (NOT DISPLAYED FOR SECURITY) ---")
print("---------------------------------\n")

# 2. Fetch CO2 Emissions Forecast for CAISO_NORTH
headers = {"Authorization": f"Bearer {token}"}
params = {
    "region": "CAISO_NORTH",
    "signal_type": "co2_moer"
}

forecast_url = "https://api.watttime.org/v3/forecast"
forecast_response = requests.get(forecast_url, headers=headers, params=params)

print("--- Real-time / Forecast Data ---")
print(forecast_response.json())