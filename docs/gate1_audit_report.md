# Gate 1: Acquisition Audit Report

## 1. Current Acquisition Code
The repository currently uses:
- `getDataFromWattTimeApi.py` to retrieve WattTime MOER forecasts.
- `real_data_collection/watttime_data_collection_v2.py` which downloads both WattTime historical MOER data (using an embedded JWT token or prompting for a new one) and CAISO OASIS Day-Ahead LMP (price) and Generation (renewables) data.

## 2. Credentials Expected
- **WattTime API:** Requires a valid `WATTTIME_USERNAME` and `WATTTIME_PASSWORD` in the `.env` file to retrieve an active JWT token.
- **CAISO OASIS:** No authentication or credentials required. The API is completely public.

## 3. Provider Accessibility & Rate Limits
- **WattTime:** 
  - **Status:** **BLOCKED**. An attempt to fetch historical data for `CAISO_NORTH` using the provided credentials in `.env` resulted in a `403 Forbidden`. The current credentials lack the necessary permissions or subscription to access historical MOER data.
- **CAISO OASIS:**
  - **Status:** **ACCESSIBLE**. Historical queries for early 2021 return `200 OK`. However, the API enforces strict rate limits (rapid successive queries resulted in `429 Too Many Requests`). Data retrieval will need careful pacing, bounded chunks, and retry mechanisms.

## 4. Source Licensing & Restrictions
- **WattTime:** Data is proprietary. Redistribution is generally restricted unless an explicit academic/open-data license is granted. Derived metrics may be allowed, but raw data redistribution requires verifying the specific WattTime terms of service for the account.
- **CAISO OASIS:** Data is public sector and generally open for reuse and redistribution without explicit licensing constraints.

## 5. Actual Local Coverage
- Currently, no historical regime-shift raw data exists in the local directories (`data/regime_shift/raw/`). The existing artifacts are strictly from previous small-scale single-day or simulation-based experiments.
