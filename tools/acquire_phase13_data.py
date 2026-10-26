#!/usr/bin/env python3
"""
Phase 13: Paper-Aligned Real-Data Acquisition and Preprocessing

Acquires authentic carbon intensity (WattTime MOER) and electricity price
(CAISO OASIS DAM LMP) data, normalizes them into the P11 GridDataset schema,
and produces reproducible provenance and data-quality artifacts.

Usage:
    python tools/acquire_phase13_data.py \
        --start 2024-08-01 \
        --end 2025-09-01 \
        --watttime-region CAISO_NORTH \
        --caiso-node TH_NP15_GEN-APND \
        --output-dir data/phase13

    python tools/acquire_phase13_data.py --validate-only --output-dir data/phase13
"""

import argparse
import csv
import datetime
import zoneinfo
import hashlib
import json
import os
import sys
import time
import statistics
from typing import Any, Dict, List, Optional, Tuple
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

LB_TO_KG = 0.45359237
MWH_TO_KWH = 1000.0

# Site identity for CAISO NP15 region
# Coordinates: approximate geographic center of the NP15 trading hub area
# (Sacramento area, California). Source: CAISO NP15 zone documentation.
SITE_ID = "CAISO_NP15"
SITE_LAT = 38.58
SITE_LON = -121.49
COORDINATE_SOURCE = "visualization-only representative coordinate; not a data-center location"

# California is UTC-8 (PST) / UTC-7 (PDT). Aug is PDT.
CA_PDT_OFFSET = datetime.timedelta(hours=-7)
CA_PST_OFFSET = datetime.timedelta(hours=-8)

WATTTIME_API_BASE = "https://api.watttime.org"
CAISO_OASIS_BASE = "https://oasis.caiso.com/oasisapi/SingleZip"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def california_market_date_to_utc_range(market_date_str: str) -> Tuple[datetime.datetime, datetime.datetime]:
    tz = zoneinfo.ZoneInfo("America/Los_Angeles")
    dt = datetime.date.fromisoformat(market_date_str)
    local_start = datetime.datetime.combine(dt, datetime.time(0, 0), tzinfo=tz)
    utc_start = local_start.astimezone(datetime.timezone.utc)
    next_dt = dt + datetime.timedelta(days=1)
    local_end = datetime.datetime.combine(next_dt, datetime.time(0, 0), tzinfo=tz)
    utc_end = local_end.astimezone(datetime.timezone.utc)
    return utc_start, utc_end


def format_utc(dt) -> str:
    if isinstance(dt, str):
        return dt
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# WattTime acquisition
# ---------------------------------------------------------------------------

def watttime_login(username: str, password: str, timeout: int = 30) -> str:
    """Authenticate with WattTime and return a bearer token."""
    import urllib.request
    import base64

    creds = base64.b64encode(f"{username}:{password}".encode()).decode()
    req = urllib.request.Request(
        f"{WATTTIME_API_BASE}/login",
        headers={"Authorization": f"Basic {creds}"}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode())
            return data["token"]
    except Exception as e:
        raise RuntimeError(f"WattTime login failed: {e}")


def watttime_fetch_historical(
    token: str,
    region: str,
    start: datetime.datetime,
    end: datetime.datetime,
    output_dir: str,
    timeout: int = 60,
    max_retries: int = 3,
    backoff_base: float = 2.0,
) -> List[str]:
    """Fetch WattTime historical MOER data in bounded windows.

    Returns list of raw response file paths.
    """
    import urllib.request
    import urllib.parse

    raw_dir = os.path.join(output_dir, "raw", "watttime")
    os.makedirs(raw_dir, exist_ok=True)

    # WattTime API supports up to 32 days per request
    WINDOW_DAYS = 30
    saved_files = []
    current = start

    while current < end:
        window_end = min(current + datetime.timedelta(days=WINDOW_DAYS), end)

        filename = f"moer_{region}_{current.strftime('%Y%m%d')}_{window_end.strftime('%Y%m%d')}.json"
        filepath = os.path.join(raw_dir, filename)

        # Cache: skip if already downloaded and valid
        if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
            try:
                with open(filepath, "r") as f:
                    data = json.load(f)
                if not isinstance(data, (dict, list)):
                    raise ValueError
                if isinstance(data, dict) and "data" not in data:
                    raise ValueError
                print(f"  [cache] {filename}")
                saved_files.append(filepath)
                current = window_end
                continue
            except (json.JSONDecodeError, ValueError):
                print(f"  [cache invalid] {filename} is corrupt, re-fetching")
                os.unlink(filepath)

        params = urllib.parse.urlencode({
            "region": region,
            "start": format_utc(current),
            "end": format_utc(window_end),
            "signal_type": "co2_moer",
        })
        url = f"{WATTTIME_API_BASE}/v3/historical?{params}"

        for attempt in range(max_retries):
            try:
                req = urllib.request.Request(
                    url,
                    headers={"Authorization": f"Bearer {token}"}
                )
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    raw_data = resp.read()
                    with open(filepath, "wb") as f:
                        f.write(raw_data)
                    print(f"  [ok] {filename} ({len(raw_data)} bytes)")
                    saved_files.append(filepath)
                    break
            except Exception as e:
                if attempt < max_retries - 1:
                    wait = backoff_base ** (attempt + 1)
                    print(f"  [retry {attempt+1}] {filename}: {e}, waiting {wait}s")
                    time.sleep(wait)
                else:
                    raise RuntimeError(f"WattTime fetch failed after {max_retries} attempts for {filename}: {e}")

        current = window_end
        time.sleep(0.5)  # Rate limiting courtesy

    return saved_files


def parse_watttime_responses(raw_files: List[str]) -> Tuple[List[Dict[str, Any]], Dict[str, Any], Dict[str, Any]]:

    observations_map = {}
    meta_info = {}

    wt_stats = {
        "raw_observations": 0,
        "unique_observations": 0,
        "identical_duplicates": 0,
        "conflicting_duplicates": 0,
        "imputed_true": 0,
        "imputed_false": 0,
        "imputed_unavailable": 0
    }

    expected_region = "CAISO_NORTH"
    expected_signal = "co2_moer"
    expected_units = "lbs_co2_per_mwh"
    expected_freq = 300

    for fpath in sorted(raw_files):
        try:
            with open(fpath, "r") as f:
                data = json.load(f)
        except json.JSONDecodeError:
            raise RuntimeError(f"Invalid JSON in cache file {fpath}")

        if isinstance(data, dict):
            if "meta" in data:
                m = data["meta"]
                if m.get("region") != expected_region:
                    raise RuntimeError(f"Unexpected region {m.get('region')} in {fpath}")
                if m.get("signal_type") != expected_signal:
                    raise RuntimeError(f"Unexpected signal {m.get('signal_type')} in {fpath}")
                if m.get("units") != expected_units:
                    raise RuntimeError(f"Unexpected units {m.get('units')} in {fpath}")
                if m.get("data_point_period_seconds") != expected_freq:
                    raise RuntimeError(f"Unexpected frequency {m.get('data_point_period_seconds')} in {fpath}")

                if "model" in m:
                    if "model" in meta_info and meta_info["model"] != m["model"]:
                        print(f"Warning: Model transition detected: {meta_info['model']} -> {m['model']}")

                meta_info.update(m)

            records = data.get("data", [])
        elif isinstance(data, list):
            records = data
        else:
            raise ValueError(f"Unexpected WattTime response format in {fpath}")

        for rec in records:
            wt_stats["raw_observations"] += 1

            pt = rec.get("point_time") or rec.get("timestamp")
            if pt is None:
                raise RuntimeError(f"Missing point_time in {fpath}: {rec}")

            val = rec.get("value")
            if val is None:
                val = rec.get("moer")
            if val is None:
                raise RuntimeError(f"Missing value in {fpath}: {rec}")
            if not isinstance(val, (int, float)):
                raise RuntimeError(f"Non-numeric value in {fpath}: {rec}")

            ts_str = str(pt).strip()
            if ts_str.endswith("Z"):
                ts = datetime.datetime.fromisoformat(ts_str[:-1]).replace(tzinfo=datetime.timezone.utc)
            else:
                try:
                    ts = datetime.datetime.fromisoformat(ts_str)
                except ValueError:
                    raise RuntimeError(f"Malformed timestamp {ts_str} in {fpath}")
                if ts.tzinfo is None:
                    raise RuntimeError(f"Naive timestamp {ts_str} in {fpath}")
                ts = ts.astimezone(datetime.timezone.utc)

            imputed = rec.get("imputed_data_used")
            if imputed is True:
                wt_stats["imputed_true"] += 1
            elif imputed is False:
                wt_stats["imputed_false"] += 1
            else:
                wt_stats["imputed_unavailable"] += 1

            ts_key = format_utc(ts)

            new_val = float(val)

            if ts_key in observations_map:
                existing_val = observations_map[ts_key]["value_lb_per_mwh"]
                if abs(existing_val - new_val) < 1e-6:
                    wt_stats["identical_duplicates"] += 1
                else:
                    # check last_updated if available
                    old_rec = observations_map[ts_key]
                    if rec.get("last_updated") and old_rec.get("last_updated"):
                        if rec["last_updated"] > old_rec["last_updated"]:
                            observations_map[ts_key] = {
                                "point_time_utc": ts,
                                "value_lb_per_mwh": new_val,
                                "imputed_data_used": imputed,
                                "last_updated": rec.get("last_updated")
                            }
                            wt_stats["conflicting_duplicates"] += 1
                        elif rec["last_updated"] < old_rec["last_updated"]:
                            wt_stats["conflicting_duplicates"] += 1
                        else:
                            raise RuntimeError(f"Conflicting duplicate at {ts_key} with same last_updated: {existing_val} vs {new_val}")
                    else:
                        raise RuntimeError(f"Conflicting duplicate without resolution rule at {ts_key}: {existing_val} vs {new_val}")
                continue

            observations_map[ts_key] = {
                "point_time_utc": ts,
                "value_lb_per_mwh": new_val,
                "imputed_data_used": imputed,
                "last_updated": rec.get("last_updated")
            }

    wt_stats["unique_observations"] = len(observations_map)
    observations = list(observations_map.values())
    observations.sort(key=lambda x: x["point_time_utc"])

    return observations, meta_info, wt_stats

def resample_watttime_to_hourly(
    observations: List[Dict], min_coverage: int = 12
) -> Tuple[List[Dict], List[Dict]]:
    # Group by hour and minute
    hourly_buckets: Dict[datetime.datetime, Dict[int, float]] = {}
    for obs in observations:
        ts = obs["point_time_utc"]
        hour_start = ts.replace(minute=0, second=0, microsecond=0)
        hourly_buckets.setdefault(hour_start, {})[ts.minute] = obs["value_lb_per_mwh"]

    complete = []
    incomplete = []
    valid_minutes = {0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55}

    for hour_start in sorted(hourly_buckets.keys()):
        obs_map = hourly_buckets[hour_start]
        if not all(m in valid_minutes for m in obs_map.keys()):
            incomplete.append({"timestamp_utc": hour_start, "reason": "invalid_minute_offset", "sample_count": len(obs_map)})
            continue

        if len(obs_map) == 12:
            vals = list(obs_map.values())
            record = {
                "timestamp_utc": hour_start,
                "carbon_lb_per_mwh": sum(vals) / 12.0,
                "carbon_kg_per_kwh": (sum(vals) / 12.0) * LB_TO_KG / MWH_TO_KWH,
                "sample_count": 12,
            }
            complete.append(record)
        else:
            incomplete.append({"timestamp_utc": hour_start, "reason": "incomplete_count", "sample_count": len(obs_map)})

    return complete, incomplete


# ---------------------------------------------------------------------------
# CAISO acquisition
# ---------------------------------------------------------------------------

def caiso_fetch_dam_lmp(
    node: str,
    start_date: str,
    end_date: str,
    output_dir: str,
    timeout: int = 120,
    max_retries: int = 3,
    backoff_base: float = 3.0,
) -> List[str]:
    import urllib.request
    import urllib.parse

    raw_dir = os.path.join(output_dir, "raw", "caiso")
    os.makedirs(raw_dir, exist_ok=True)

    start = datetime.date.fromisoformat(start_date)
    end = datetime.date.fromisoformat(end_date)
    WINDOW_DAYS = 30

    saved_files = []
    current = start

    while current < end:
        window_end = min(current + datetime.timedelta(days=WINDOW_DAYS), end)

        filename = f"dam_lmp_{node}_{current.isoformat()}_{window_end.isoformat()}.zip"
        filepath = os.path.join(raw_dir, filename)

        if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
            import zipfile
            try:
                with zipfile.ZipFile(filepath) as zf:
                    if not any(name.endswith(".csv") for name in zf.namelist()):
                        raise ValueError
                print(f"  [cache] {filename}")
                saved_files.append(filepath)
                current = window_end
                continue
            except (zipfile.BadZipFile, ValueError):
                print(f"  [cache invalid] {filename} is corrupt or missing CSV, re-fetching")
                os.unlink(filepath)

        # Compute UTC start/end for the local day
        utc_start, _ = california_market_date_to_utc_range(current.isoformat())
        _, utc_end = california_market_date_to_utc_range((window_end - datetime.timedelta(days=1)).isoformat())

        params = {
            "queryname": "PRC_LMP",
            "startdatetime": f"{utc_start.strftime('%Y%m%dT%H:00-0000')}",
            "enddatetime": f"{utc_end.strftime('%Y%m%dT%H:00-0000')}",
            "market_run_id": "DAM",
            "node": node,
            "resultformat": "6",
            "version": "1",
        }

        url = f"{CAISO_OASIS_BASE}?{urllib.parse.urlencode(params)}"

        for attempt in range(max_retries):
            try:
                req = urllib.request.Request(url)
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    raw_data = resp.read()

                    # Detect XML error payloads
                    if raw_data.startswith(b"<?xml") and b"<m:ERROR>" in raw_data:
                        raise RuntimeError(f"CAISO API returned an error: {raw_data.decode(errors='replace')}")

                    with open(filepath, "wb") as f:
                        f.write(raw_data)

                    print(f"  [ok] {filename}")
                    saved_files.append(filepath)
                    break
            except Exception as e:
                if attempt < max_retries - 1:
                    wait = backoff_base ** (attempt + 1)
                    print(f"  [retry {attempt+1}] {filename}: {e}, waiting {wait}s")
                    time.sleep(wait)
                else:
                    raise RuntimeError(f"CAISO fetch failed after {max_retries} attempts for {filename}: {e}")

        current = window_end
        time.sleep(1.0)

    return saved_files

def parse_caiso_dam_csv(raw_files: List[str], node: str) -> Tuple[List[Dict[str, Any]], int, int]:
    records_map = {}
    identical_dups = 0
    conflicting_dups = 0

    for fpath in sorted(raw_files):
        content = ""
        import zipfile
        if zipfile.is_zipfile(fpath):
            found_csv = False
            with zipfile.ZipFile(fpath) as zf:
                for name in zf.namelist():
                    if name.endswith(".csv"):
                        content = zf.read(name).decode("utf-8-sig", errors="replace")
                        found_csv = True
                        break
            if not found_csv:
                raise RuntimeError(f"Expected CSV missing in ZIP: {fpath}")
        else:
            try:
                with open(fpath, "r", encoding="utf-8-sig") as f:
                    content = f.read()
            except UnicodeDecodeError:
                with open(fpath, "r", encoding="latin-1") as f:
                    content = f.read()

            if content.startswith("<?xml") and "<m:ERROR>" in content:
                raise RuntimeError(f"CAISO raw file contains XML error: {fpath}")

        if not content:
            continue

        reader = csv.DictReader(content.strip().splitlines())

        for row in reader:
            r = {k.strip().upper(): v.strip() if isinstance(v, str) else v for k, v in row.items()}

            row_node = r.get("NODE", r.get("NODE_ID", r.get("RESOURCE_NAME", "")))
            if node.upper() not in row_node.upper():
                continue

            lmp_type = r.get("LMP_TYPE", r.get("LMP_PRC_TYPE", ""))
            if lmp_type.upper() != "LMP":
                continue

            ts_str = r.get("INTERVALSTARTTIME_GMT", r.get("GMT_START", ""))
            end_ts_str = r.get("INTERVALENDTIME_GMT", r.get("GMT_END", ""))
            if not ts_str:
                raise RuntimeError(f"Missing INTERVALSTARTTIME_GMT in {fpath}")
            if not end_ts_str:
                raise RuntimeError(f"Missing INTERVALENDTIME_GMT in {fpath}")

            def parse_caiso_ts(tstr):
                tstr = tstr.strip()
                if tstr.endswith("Z"):
                    t = datetime.datetime.fromisoformat(tstr[:-1]).replace(tzinfo=datetime.timezone.utc)
                else:
                    t = datetime.datetime.fromisoformat(tstr)
                    if t.tzinfo is None:
                        t = t.replace(tzinfo=datetime.timezone.utc)
                    else:
                        t = t.astimezone(datetime.timezone.utc)
                return t

            ts_utc = parse_caiso_ts(ts_str)
            end_utc = parse_caiso_ts(end_ts_str)

            if end_utc <= ts_utc:
                raise RuntimeError(f"Interval end {end_utc} not > start {ts_utc} in {fpath}")
            duration = (end_utc - ts_utc).total_seconds()
            if duration != 3600:
                raise RuntimeError(f"Interval duration not 1 hour: {duration}s in {fpath}")

            interval_key = format_utc(ts_utc)

            price_str = r.get("PRC", r.get("MW", r.get("VALUE", "")))
            try:
                price_usd_per_mwh = float(price_str)
            except (ValueError, TypeError):
                continue

            if interval_key in records_map:
                existing_price = records_map[interval_key]["price_usd_per_mwh"]
                if abs(existing_price - price_usd_per_mwh) < 1e-6:
                    identical_dups += 1
                else:
                    conflicting_dups += 1
                    raise RuntimeError(f"Conflicting duplicate CAISO LMP at {interval_key}: {existing_price} vs {price_usd_per_mwh}")
                continue

            records_map[interval_key] = {
                "timestamp_utc": ts_utc,
                "interval_end_utc": end_utc,
                "price_usd_per_mwh": price_usd_per_mwh,
                "price_usd_per_kwh": price_usd_per_mwh / MWH_TO_KWH,
                "node": node,
                "market": "DAM",
                "lmp_type": "LMP",
            }

    records = list(records_map.values())
    records.sort(key=lambda x: x["timestamp_utc"])
    return records, identical_dups, conflicting_dups

def join_carbon_price(
    carbon_hourly: List[Dict],
    price_records: List[Dict],
) -> Tuple[List[Dict], List[Dict]]:
    """Join carbon and price by UTC hour. Return (joined, dropped)."""
    carbon_by_hour = {format_utc(r["timestamp_utc"]): r for r in carbon_hourly}
    price_by_hour = {format_utc(r["timestamp_utc"]): r for r in price_records}

    common_hours = sorted(set(carbon_by_hour.keys()) & set(price_by_hour.keys()))

    joined = []
    dropped = []

    # Track why hours were dropped
    all_hours = sorted(set(carbon_by_hour.keys()) | set(price_by_hour.keys()))
    for h in all_hours:
        if h in carbon_by_hour and h in price_by_hour:
            c = carbon_by_hour[h]
            p = price_by_hour[h]
            joined.append({
                "timestamp_utc": h,
                "site_id": SITE_ID,
                "latitude": SITE_LAT,
                "longitude": SITE_LON,
                "carbon_kg_per_kwh": c["carbon_kg_per_kwh"],
                "carbon_lb_per_mwh": c["carbon_lb_per_mwh"],
                "price_usd_per_kwh": p["price_usd_per_kwh"],
                "price_usd_per_mwh": p["price_usd_per_mwh"],
            })
        else:
            reason = "missing_carbon" if h not in carbon_by_hour else "missing_price"
            dropped.append({"timestamp_utc": h, "reason": reason})

    return joined, dropped


def write_normalized_csv(records: List[Dict], filepath: str) -> str:
    """Write P11-compatible normalized CSV. Returns SHA-256 checksum."""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    fieldnames = [
        "timestamp_utc", "site_id", "latitude", "longitude",
        "carbon_kg_per_kwh", "price_usd_per_kwh"
    ]
    with open(filepath, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in records:
            writer.writerow({k: r[k] for k in fieldnames})
    return sha256_file(filepath)


def write_audit_csv(records: List[Dict], filepath: str, fields: List[str]):
    """Write an intermediate audit CSV preserving original units."""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for r in records:
            writer.writerow({k: r.get(k, "") for k in fields})


def extract_paper_day(records: List[Dict], paper_date: str = "2025-08-05") -> List[Dict]:
    """Extract the paper-day slice.

    Paper day: August 5, 2025. During PDT (UTC-7), this is:
    2025-08-05T07:00:00Z through 2025-08-06T06:00:00Z (24 hours).
    """
    utc_start, utc_end = california_market_date_to_utc_range(paper_date)
    start_str = format_utc(utc_start)
    end_str = format_utc(utc_end)

    return [r for r in records if start_str <= r["timestamp_utc"] < end_str]


# ---------------------------------------------------------------------------
# Data quality report
# ---------------------------------------------------------------------------

def compute_data_quality(
    joined: List[Dict],
    dropped: List[Dict],
    wt_stats: Dict,
    carbon_complete_count: int,
    carbon_incomplete_count: int,
    price_raw_count: int,
    price_duplicate_count: int,
    price_conflicting_count: int,
    paper_day: List[Dict],
    normalized_checksum: str,
    start_date: str,
    end_date: str,
) -> Dict[str, Any]:
    """Compute comprehensive data quality statistics."""
    if not joined:
        return {
            "sites": 1,
            "requested_range": f"{start_date} to {end_date}",
            "actual_range": "N/A",
            "final_row_count": 0,
            "error": "No joined data available",
        }

    carbon_vals = [r["carbon_kg_per_kwh"] for r in joined]
    price_vals = [r["price_usd_per_kwh"] for r in joined]
    timestamps = [r["timestamp_utc"] for r in joined]

    # Check strict monotonicity
    is_monotonic = all(timestamps[i] < timestamps[i+1] for i in range(len(timestamps)-1))

    # Expected hourly intervals
    first_ts = datetime.datetime.fromisoformat(timestamps[0][:-1]).replace(tzinfo=datetime.timezone.utc)
    last_ts = datetime.datetime.fromisoformat(timestamps[-1][:-1]).replace(tzinfo=datetime.timezone.utc)
    expected_hours = int((last_ts - first_ts).total_seconds() / 3600) + 1
    dense = (len(joined) == expected_hours)

    neg_price_count = sum(1 for p in price_vals if p < 0)

    return {
        "sites": 1,
        "site_id": SITE_ID,
        "requested_range": f"{start_date} to {end_date}",
        "first_utc_timestamp": timestamps[0],
        "last_utc_timestamp": timestamps[-1],
        "resolution": "hourly",
        "expected_hourly_count": expected_hours,
        "watttime_raw_observation_count": wt_stats["raw_observations"],
        "watttime_unique_observation_count": wt_stats["unique_observations"],
        "watttime_identical_duplicate_count": wt_stats["identical_duplicates"],
        "watttime_conflicting_duplicate_count": wt_stats["conflicting_duplicates"],
        "watttime_imputed_true_count": wt_stats["imputed_true"],
        "watttime_imputed_false_count": wt_stats["imputed_false"],
        "watttime_imputed_unavailable_count": wt_stats["imputed_unavailable"],
        "carbon_complete_hours": carbon_complete_count,
        "carbon_incomplete_hours": carbon_incomplete_count,
        "caiso_price_observation_count": price_raw_count,
        "caiso_price_duplicate_count": price_duplicate_count,
        "caiso_price_conflicting_count": price_conflicting_count,
        "unmatched_hours": len(dropped),
        "dropped_hours": len(dropped),
        "interpolation_count": 0,
        "final_row_count": len(joined),
        "strict_chronological_monotonicity": is_monotonic,
        "dense_coverage": dense,
        "coordinate_validation": {
            "latitude": SITE_LAT,
            "longitude": SITE_LON,
            "source": COORDINATE_SOURCE,
            "valid_range": -90 <= SITE_LAT <= 90 and -180 <= SITE_LON <= 180,
        },
        "carbon_stats": {
            "min": min(carbon_vals),
            "median": statistics.median(carbon_vals),
            "mean": statistics.mean(carbon_vals),
            "max": max(carbon_vals),
            "std": statistics.stdev(carbon_vals) if len(carbon_vals) > 1 else 0.0,
        },
        "price_stats": {
            "min": min(price_vals),
            "median": statistics.median(price_vals),
            "mean": statistics.mean(price_vals),
            "max": max(price_vals),
            "std": statistics.stdev(price_vals) if len(price_vals) > 1 else 0.0,
        },
        "negative_price_count": neg_price_count,
        "paper_day_row_count": len(paper_day),
        "normalized_checksum_sha256": normalized_checksum,
    }


# ---------------------------------------------------------------------------
# Provenance
# ---------------------------------------------------------------------------

def build_provenance(
    start_date: str,
    end_date: str,
    watttime_region: str,
    caiso_node: str,
    watttime_meta: Dict,
    wt_stats: Dict,
    raw_checksums: Dict[str, str],
    normalized_checksum: str,
    paper_day_info: Dict[str, Any],
    watttime_available: bool,
    caiso_available: bool,
    retrieval_ts: str,
) -> Dict[str, Any]:
    return {
        "dataset_id": f"phase13_{SITE_ID}_{start_date}_{end_date}",
        "dataset_status": "VERIFIED_REAL",
        "providers": {
            "carbon": {
                "name": "WattTime",
                "signal": "Marginal Operating Emissions Rate (MOER)",
                "region": watttime_region,
                "endpoint": f"{WATTTIME_API_BASE}/v3/historical",
                "model_version": watttime_meta.get("model", {}).get("type", "unknown"),
                "model_date": watttime_meta.get("model", {}).get("date", "unknown"),
                "original_unit": "lb CO2/MWh",
                "normalized_unit": "kg CO2/kWh",
                "conversion": f"value_lb_per_mwh * {LB_TO_KG} / {MWH_TO_KWH}",
                "native_resolution": "5 minutes",
                "resampling_rule": "arithmetic mean of aligned 5-min observations per hour",
                "hourly_completeness_threshold": "12 of 12 unique five-minute observations at offsets 00,05,...,55",
                "access": "authenticated API" if watttime_available else "UNAVAILABLE",
                "terms": "https://watttime.org/legal/terms-of-use/",
                "note": "Historical MOER values depend on the model version active at query time. "
                        "Values may differ from those used in the original paper if the model has been updated.",
            },
            "price": {
                "name": "California ISO (CAISO)",
                "signal": "Day-Ahead Market Locational Marginal Price (total LMP)",
                "node": caiso_node,
                "market": "DAM",
                "endpoint": CAISO_OASIS_BASE,
                "query_parameters": {
                    "queryname": "PRC_LMP",
                    "market_run_id": "DAM",
                    "node": caiso_node,
                    "resultformat": "6",
                },
                "original_unit": "USD/MWh",
                "normalized_unit": "USD/kWh",
                "conversion": f"value_usd_per_mwh / {MWH_TO_KWH}",
                "native_resolution": "hourly",
                "access": "public OASIS" if caiso_available else "UNAVAILABLE",
                "terms": "http://www.caiso.com/Pages/TermsOfUse.aspx",
                "license": "Public data, redistribution subject to CAISO terms",
            },
        },
        "site": {
            "site_id": SITE_ID,
            "carbon_region": watttime_region,
            "price_node": caiso_node,
            "latitude": SITE_LAT,
            "longitude": SITE_LON,
            "coordinate_source": COORDINATE_SOURCE,
        },
        "requested_range": {"start": start_date, "end": end_date},
        "timezone_notes": {
            "source_timezone": "California (Pacific Time)",
            "august_offset": "PDT (UTC-7)",
            "interval_semantics": "interval-starting",
            "canonical_format": "YYYY-MM-DDTHH:MM:SSZ (UTC)",
        },
        "missing_data_policy": "No interpolation, no backfill, no synthetic fallback",
        "retrieval_timestamp_utc": retrieval_ts,
        "watttime_imputation": {
            "imputed_true": wt_stats.get("imputed_true", 0),
            "imputed_false": wt_stats.get("imputed_false", 0),
            "imputed_unavailable": wt_stats.get("imputed_unavailable", 0)
        },
        "paper_day_evidence": paper_day_info,
        "raw_checksums": raw_checksums,
        "processed_checksum_sha256": normalized_checksum,
        "limitations": [
            "WattTime MOER model version may differ from the paper's original data.",
            "Single site representation of CAISO NP15 regional signals.",
            "Renewable fraction is not included (would be a derived proxy, not observed).",
        ],
        "is_exact_historical_reproduction": False,
        "reconstruction_note": "Current-model reconstruction using WattTime API at query time",
    }


# ---------------------------------------------------------------------------
# Partition manifest
# ---------------------------------------------------------------------------

def build_partition_manifest(
    joined: List[Dict],
    start_date: str,
    end_date: str,
) -> Dict[str, Any]:
    """Build partition boundaries using correct UTC conversions."""
    # Training: 2024-08-01 through end of 2025-06-30
    train_utc_start, _ = california_market_date_to_utc_range("2024-08-01")
    _, train_utc_end = california_market_date_to_utc_range("2025-06-30")

    # Validation: July 2025
    val_utc_start, _ = california_market_date_to_utc_range("2025-07-01")
    _, val_utc_end = california_market_date_to_utc_range("2025-07-31")

    # Test: August 2025
    test_utc_start, _ = california_market_date_to_utc_range("2025-08-01")
    _, test_utc_end = california_market_date_to_utc_range("2025-08-31")

    # Paper day: August 5, 2025
    pd_utc_start, pd_utc_end = california_market_date_to_utc_range("2025-08-05")

    return {
        "partitions": {
            "TRAIN": {
                "start_utc": format_utc(train_utc_start),
                "end_utc": format_utc(train_utc_end),
                "market_date_range": "2024-08-01 to 2025-06-30",
                "timezone_note": "Boundaries derived from California market dates under PDT/PST",
            },
            "VALIDATION": {
                "start_utc": format_utc(val_utc_start),
                "end_utc": format_utc(val_utc_end),
                "market_date_range": "2025-07-01 to 2025-07-31",
            },
            "TEST": {
                "start_utc": format_utc(test_utc_start),
                "end_utc": format_utc(test_utc_end),
                "market_date_range": "2025-08-01 to 2025-08-31",
            },
            "PAPER_DAY": {
                "start_utc": format_utc(pd_utc_start),
                "end_utc": format_utc(pd_utc_end),
                "market_date": "2025-08-05",
                "timezone_note": "PDT (UTC-7): 2025-08-05T07:00:00Z to 2025-08-06T06:00:00Z",
            },
        },
        "derivation_note": "UTC boundaries derived from California market dates accounting for PDT/PST transitions",
    }


# ---------------------------------------------------------------------------
# Validation-only mode
# ---------------------------------------------------------------------------

def validate_existing_output(output_dir: str) -> bool:
    """Validate previously generated P13 output without network access."""
    norm_path = os.path.join(output_dir, "processed", "grid_normalized.csv")
    if not os.path.exists(norm_path):
        print(f"ERROR: {norm_path} not found")
        return False

    # Attempt P11 adapter validation
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from scheduler.real_data_adapter import parse_normalized_grid_csv
    from scheduler.contracts import DatasetStatus

    dataset_id = "phase13_validation"
    try:
        ds = parse_normalized_grid_csv(
            norm_path,
            dataset_id=dataset_id,
            source_ids=("WattTime", "CAISO_OASIS"),
            status=DatasetStatus.VERIFIED_REAL,
        )
        ds.validate()
        print(f"P11 validation: PASS ({len(ds.timestamps_utc)} timestamps, {len(ds.site_ids)} sites)")
    except Exception as e:
        print(f"P11 validation: FAIL ({e})")
        return False

    # Check P12 metadata
    try:
        from scheduler.website_outputs import extract_metadata_from_grid_dataset
        sites, timestamps = extract_metadata_from_grid_dataset(ds)
        print(f"P12 metadata: {len(sites)} sites, {len(timestamps)} timestamps")
    except Exception as e:
        print(f"P12 metadata: FAIL ({e})")
        return False

    return True


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Phase 13 Real Data Acquisition")
    parser.add_argument("--start", default="2024-08-01", help="Start date YYYY-MM-DD")
    parser.add_argument("--end", default="2025-09-01", help="End date YYYY-MM-DD (exclusive)")
    parser.add_argument("--watttime-region", default="CAISO_NORTH")
    parser.add_argument("--caiso-node", default="TH_NP15_GEN-APND")
    parser.add_argument("--output-dir", default="data/phase13")
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()

    if args.validate_only:
        ok = validate_existing_output(args.output_dir)
        sys.exit(0 if ok else 1)

    retrieval_ts = format_utc(datetime.datetime.now(datetime.timezone.utc))
    raw_checksums = {}

    # ----- WattTime -----
    wt_username = os.environ.get("WATTTIME_USERNAME", "")
    wt_password = os.environ.get("WATTTIME_PASSWORD", "")
    watttime_available = bool(wt_username and wt_password)
    watttime_meta = {}
    carbon_hourly = []
    carbon_incomplete = []
    carbon_raw_count = 0

    if watttime_available:
        print("=== WattTime MOER Acquisition ===")
        try:
            token = watttime_login(wt_username, wt_password, timeout=args.timeout)
            print("  Login: OK")
        except Exception as e:
            print(f"  Login: FAILED ({e})")
            print("\nACTION REQUIRED: Set WATTTIME_USERNAME and WATTTIME_PASSWORD environment variables.")
            print("Register at https://watttime.org/api-documentation/#register")
            watttime_available = False

    if watttime_available:
        start_dt, _ = california_market_date_to_utc_range(args.start)
        # We need the end of the end_date market day, but end is exclusive
        end_minus_one = (datetime.date.fromisoformat(args.end) - datetime.timedelta(days=1)).isoformat()
        _, end_dt = california_market_date_to_utc_range(end_minus_one)

        wt_files = watttime_fetch_historical(
            token, args.watttime_region, start_dt, end_dt,
            args.output_dir, timeout=args.timeout
        )

        for fp in wt_files:
            raw_checksums[os.path.basename(fp)] = sha256_file(fp)

        observations, watttime_meta, wt_stats = parse_watttime_responses(wt_files)
        carbon_raw_count = len(observations)
        print(f"  Raw 5-min observations: {carbon_raw_count}")

        carbon_hourly, carbon_incomplete = resample_watttime_to_hourly(observations)
        print(f"  Complete hours: {len(carbon_hourly)}, Incomplete: {len(carbon_incomplete)}")

        # Write carbon audit
        write_audit_csv(
            carbon_hourly,
            os.path.join(args.output_dir, "intermediate", "watttime_hourly_audit.csv"),
            ["timestamp_utc", "carbon_lb_per_mwh", "carbon_kg_per_kwh", "sample_count"],
        )
        # Format timestamps for joining
        for r in carbon_hourly:
            if isinstance(r["timestamp_utc"], datetime.datetime):
                r["timestamp_utc"] = format_utc(r["timestamp_utc"])

    if not watttime_available:
        print("\n*** WattTime access unavailable ***")
        print("ACTION REQUIRED: Set environment variables WATTTIME_USERNAME and WATTTIME_PASSWORD")
        print("Register: https://watttime.org/api-documentation/#register")
        print("Continuing with CAISO-only acquisition...\n")

    # ----- CAISO -----
    print("=== CAISO DAM LMP Acquisition ===")
    caiso_available = True
    price_records = []
    price_raw_count = 0
    price_duplicate_count = 0

    try:
        caiso_files = caiso_fetch_dam_lmp(
            args.caiso_node, args.start, args.end,
            args.output_dir, timeout=args.timeout
        )

        for fp in caiso_files:
            raw_checksums[os.path.basename(fp)] = sha256_file(fp)

        price_records, price_duplicate_count, price_conflicting_count = parse_caiso_dam_csv(caiso_files, args.caiso_node)
        price_raw_count = len(price_records) + price_duplicate_count + price_conflicting_count
        print(f"  Price records: {price_raw_count}")

        # Write price audit
        write_audit_csv(
            price_records,
            os.path.join(args.output_dir, "intermediate", "caiso_dam_audit.csv"),
            ["timestamp_utc", "price_usd_per_mwh", "price_usd_per_kwh", "node", "market", "lmp_type"],
        )
        for r in price_records:
            if isinstance(r["timestamp_utc"], datetime.datetime):
                r["timestamp_utc"] = format_utc(r["timestamp_utc"])

    except Exception as e:
        print(f"  CAISO acquisition failed: {e}")
        caiso_available = False

    # ----- Join -----
    if watttime_available and caiso_available and carbon_hourly and price_records:
        print("=== Joining carbon + price ===")
        joined, dropped = join_carbon_price(carbon_hourly, price_records)
        print(f"  Joined hours: {len(joined)}, Dropped: {len(dropped)}")

        # Write alignment audit
        write_audit_csv(
            dropped,
            os.path.join(args.output_dir, "intermediate", "alignment_audit.csv"),
            ["timestamp_utc", "reason"],
        )

        # Normalized output
        norm_path = os.path.join(args.output_dir, "processed", "grid_normalized.csv")
        norm_checksum = write_normalized_csv(joined, norm_path)
        print(f"  Normalized CSV: {norm_path} (SHA-256: {norm_checksum})")

        # Paper day
        paper_day = extract_paper_day(joined)
        pd_path = os.path.join(args.output_dir, "processed", "paper_day_2025-08-05.csv")
        if paper_day:
            pd_checksum = write_normalized_csv(paper_day, pd_path)
            print(f"  Paper day: {len(paper_day)} hours (SHA-256: {pd_checksum})")

            wt_pd_raw = os.path.join(args.output_dir, "raw", "watttime", "moer_CAISO_NORTH_20250805_20250806.json")
            caiso_pd_raw = os.path.join(args.output_dir, "raw", "caiso", "dam_lmp_TH_NP15_GEN-APND_2025-08-05_2025-08-06.zip")
            paper_day_info = {
                "processed_filename": "paper_day_2025-08-05.csv",
                "processed_checksum_sha256": pd_checksum,
                "row_count": len(paper_day),
                "first_timestamp_utc": format_utc(paper_day[0]["timestamp_utc"]),
                "last_timestamp_utc": format_utc(paper_day[-1]["timestamp_utc"]),
                "wattime_raw_filename": "moer_CAISO_NORTH_20250805_20250806.json",
                "wattime_raw_checksum_sha256": sha256_file(wt_pd_raw) if os.path.exists(wt_pd_raw) else None,
                "caiso_raw_filename": "dam_lmp_TH_NP15_GEN-APND_2025-08-05_2025-08-06.zip",
                "caiso_raw_checksum_sha256": sha256_file(caiso_pd_raw) if os.path.exists(caiso_pd_raw) else None,
            }
        else:
            print(f"  Paper day: no data for 2025-08-05")
            pd_checksum = ""
            paper_day_info = {}

        # Data quality
        dq = compute_data_quality(
            joined, dropped,
            wt_stats, len(carbon_hourly), len(carbon_incomplete),
            price_raw_count, price_duplicate_count, price_conflicting_count,
            paper_day, norm_checksum, args.start, args.end
        )
        dq_path = os.path.join(args.output_dir, "metadata", "data_quality.json")
        os.makedirs(os.path.dirname(dq_path), exist_ok=True)
        with open(dq_path, "w") as f:
            json.dump(dq, f, indent=2, sort_keys=True, default=str)

        # Provenance
        prov = build_provenance(
            args.start, args.end, args.watttime_region, args.caiso_node,
            watttime_meta, wt_stats, raw_checksums, norm_checksum, paper_day_info,
            watttime_available, caiso_available, retrieval_ts
        )
        prov_path = os.path.join(args.output_dir, "metadata", "provenance.json")
        with open(prov_path, "w") as f:
            json.dump(prov, f, indent=2, sort_keys=True, default=str)

        # Sites
        sites = {
            "sites": [{
                "site_id": SITE_ID,
                "latitude": SITE_LAT,
                "longitude": SITE_LON,
                "carbon_region": args.watttime_region,
                "price_node": args.caiso_node,
                "coordinate_source": COORDINATE_SOURCE,
            }]
        }
        sites_path = os.path.join(args.output_dir, "metadata", "sites.json")
        with open(sites_path, "w") as f:
            json.dump(sites, f, indent=2)

        # Partitions
        partitions = build_partition_manifest(joined, args.start, args.end)
        part_path = os.path.join(args.output_dir, "metadata", "partitions.json")
        with open(part_path, "w") as f:
            json.dump(partitions, f, indent=2, sort_keys=True, default=str)

        # P11 validation
        print("\n=== P11 Validation ===")
        validate_existing_output(args.output_dir)

        print(f"\n=== Summary ===")
        print(f"  Final rows: {len(joined)}")
        print(f"  Checksum: {norm_checksum}")
        if dq.get("strict_chronological_monotonicity"):
            print(f"  Monotonicity: PASS")
        print(f"  Dense coverage: {dq.get('dense_coverage')}")
    else:
        if not watttime_available:
            print("\n=== RESULT: INCOMPLETE (WattTime unavailable) ===")
            print("The CAISO price data was acquired (if available).")
            print("Carbon intensity data requires WattTime API credentials.")
            print("\nRequired user action:")
            print("  1. Register at https://watttime.org/api-documentation/#register")
            print("  2. Set WATTTIME_USERNAME and WATTTIME_PASSWORD environment variables")
            print("  3. Re-run this command")
        elif not caiso_available:
            print("\n=== RESULT: INCOMPLETE (CAISO unavailable) ===")
        else:
            print("\n=== RESULT: INCOMPLETE (no data to join) ===")


if __name__ == "__main__":
    main()
