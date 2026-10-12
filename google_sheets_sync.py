"""
Google Sheets Sync Module for Multi-Branch Sales Scraper.
Supports both:
1. Google Apps Script Webhook (Recommended: zero-config, 100% free, no Google Cloud setup)
2. Direct Google Sheets API via gspread (Service Account credentials.json)
"""

import os
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
import requests

logger = logging.getLogger("GoogleSheetsSync")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")


def load_config() -> dict:
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading config.json: {e}")
    return {}


def get_current_time_slot() -> str:
    """Returns the formatted current hour slot, e.g. '1:00 PM', '2:00 PM'."""
    now = datetime.now()
    # Format hour with AM/PM (e.g. '1:00 PM', '10:00 AM')
    hour_12 = now.strftime("%I").lstrip("0")
    if not hour_12:
        hour_12 = "12"
    am_pm = now.strftime("%p")
    return f"{hour_12}:00 {am_pm}"


def get_slot_date(is_eod: bool = False) -> str:
    """Returns date string e.g. 'October 12, 2026'."""
    target_dt = datetime.now()
    if is_eod:
        target_dt -= timedelta(days=1)
    # Format: Month Day, Year (e.g., 'October 12, 2026')
    return target_dt.strftime("%B %d, %Y")


def format_branch_data(results_or_stores: List[Dict[str, Any]], config: Optional[dict] = None) -> List[Dict[str, Any]]:
    """
    Standardizes store results into 4-branch structured data:
    Angeles City, Quezon City, Caloocan City, San Fernando City.
    """
    cfg = config or load_config()
    branches = cfg.get("branches", [])
    
    # Map store id to latest amount
    store_map = {}
    for item in results_or_stores:
        sid = item.get("store_id") or item.get("id")
        amt = float(item.get("amount", item.get("last_amount", 0.0)))
        store_map[sid] = amt

    branch_payload = []
    # Standard 4 branches in sheet display order:
    ordered_branch_ids = ["angeles", "qc", "caloocan", "san_fernando"]
    branch_dict = {b["id"]: b for b in branches}

    for bid in ordered_branch_ids:
        b_info = branch_dict.get(bid, {})
        b_name = b_info.get("name", bid)
        # Clean branch display name for matching sheet
        short_name = "ANGELES CITY" if "angeles" in bid else \
                     "QUEZON CITY" if "qc" in bid else \
                     "CALOOCAN CITY" if "caloocan" in bid else \
                     "SAN FERNANDO"

        grab_sid = b_info.get("grab_store_id")
        panda_sid = b_info.get("panda_store_id")

        grab_amt = store_map.get(grab_sid, 0.0)
        panda_amt = store_map.get(panda_sid, 0.0)

        branch_payload.append({
            "id": bid,
            "name": short_name,
            "display_name": b_name,
            "panda": round(panda_amt, 2),
            "grab": round(grab_amt, 2),
            "total": round(panda_amt + grab_amt, 2)
        })

    return branch_payload


def sync_via_webhook(webhook_url: str, payload: dict) -> dict:
    """Sends structured sales payload to Google Apps Script Webhook."""
    try:
        response = requests.post(webhook_url, json=payload, timeout=20)
        if response.status_code in (200, 302):
            try:
                res_json = response.json()
                return {"success": True, "data": res_json, "message": "Synced successfully"}
            except Exception:
                return {"success": True, "message": response.text}
        else:
            return {"success": False, "error": f"HTTP {response.status_code}: {response.text}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def sync_via_gspread(credentials_file: str, sheet_name: str, payload: dict) -> dict:
    """Fallback syncing via gspread Service Account."""
    try:
        import gspread
        gc = gspread.service_account(filename=credentials_file)
        # Open sheet by name or URL
        spreadsheet = gc.open(sheet_name)
        # Tab name
        worksheet = spreadsheet.worksheet("Sales Report - AirKitchen")
        
        is_eod = payload.get("is_eod", False)
        time_slot = payload.get("time_slot", "1:00 PM")
        date_str = payload.get("date_str", "")
        branches = payload.get("branches", [])

        # Hardcoded cell coordinates corresponding to sheet layout
        table_coords = {
            "1:00 AM":  {"header_row": 12, "branch_row": 14, "panda_col": 3, "grab_col": 4, "date_col": 3},
            "2:00 AM":  {"header_row": 20, "branch_row": 22, "panda_col": 3, "grab_col": 4, "date_col": 3},
            "3:00 AM":  {"header_row": 28, "branch_row": 30, "panda_col": 3, "grab_col": 4, "date_col": 3},
            "4:00 AM":  {"header_row": 36, "branch_row": 38, "panda_col": 3, "grab_col": 4, "date_col": 3},
            "5:00 AM":  {"header_row": 44, "branch_row": 46, "panda_col": 3, "grab_col": 4, "date_col": 3},
            "6:00 AM":  {"header_row": 4,  "branch_row": 6,  "panda_col": 9, "grab_col": 10, "date_col": 9},
            "7:00 AM":  {"header_row": 12, "branch_row": 14, "panda_col": 9, "grab_col": 10, "date_col": 9},
            "8:00 AM":  {"header_row": 20, "branch_row": 22, "panda_col": 9, "grab_col": 10, "date_col": 9},
            "9:00 AM":  {"header_row": 28, "branch_row": 30, "panda_col": 9, "grab_col": 10, "date_col": 9},
            "10:00 AM": {"header_row": 28, "branch_row": 30, "panda_col": 9, "grab_col": 10, "date_col": 9},
            "11:00 AM": {"header_row": 36, "branch_row": 38, "panda_col": 9, "grab_col": 10, "date_col": 9},
            "12:00 PM": {"header_row": 44, "branch_row": 46, "panda_col": 9, "grab_col": 10, "date_col": 9},
            "1:00 PM":  {"header_row": 4,  "branch_row": 6,  "panda_col": 14, "grab_col": 15, "date_col": 14},
            "2:00 PM":  {"header_row": 12, "branch_row": 14, "panda_col": 14, "grab_col": 15, "date_col": 14},
            "3:00 PM":  {"header_row": 20, "branch_row": 22, "panda_col": 14, "grab_col": 15, "date_col": 14},
            "4:00 PM":  {"header_row": 28, "branch_row": 30, "panda_col": 14, "grab_col": 15, "date_col": 14},
            "5:00 PM":  {"header_row": 36, "branch_row": 38, "panda_col": 14, "grab_col": 15, "date_col": 14},
            "6:00 PM":  {"header_row": 44, "branch_row": 46, "panda_col": 14, "grab_col": 15, "date_col": 14},
            "7:00 PM":  {"header_row": 4,  "branch_row": 6,  "panda_col": 20, "grab_col": 21, "date_col": 20},
            "8:00 PM":  {"header_row": 12, "branch_row": 14, "panda_col": 20, "grab_col": 21, "date_col": 20},
            "9:00 PM":  {"header_row": 20, "branch_row": 22, "panda_col": 20, "grab_col": 21, "date_col": 20},
            "10:00 PM": {"header_row": 28, "branch_row": 30, "panda_col": 20, "grab_col": 21, "date_col": 20},
            "11:00 PM": {"header_row": 36, "branch_row": 38, "panda_col": 20, "grab_col": 21, "date_col": 20},
            "EOD":      {"header_row": 44, "branch_row": 46, "panda_col": 20, "grab_col": 21, "date_col": 20}
        }

        key = "EOD" if is_eod else time_slot
        coord = table_coords.get(key)
        if not coord:
            return {"success": False, "error": f"No cell coordinates mapped for slot '{key}'"}

        # 1. Update date in header
        worksheet.update_cell(coord["header_row"], coord["date_col"], date_str)

        # 2. Update 4 branch rows (Panda and Grab columns)
        cells_to_update = []
        for idx, b in enumerate(branches):
            r = coord["branch_row"] + idx
            worksheet.update_cell(r, coord["panda_col"], b["panda"])
            worksheet.update_cell(r, coord["grab_col"], b["grab"])

        return {"success": True, "message": f"Updated {key} table in Google Sheet."}
    except Exception as e:
        return {"success": False, "error": str(e)}


def sync_sales_to_google_sheet(
    results_or_stores: List[Dict[str, Any]],
    is_eod: bool = False,
    time_slot: Optional[str] = None,
    date_str: Optional[str] = None,
    log_func: Optional[Any] = None
) -> dict:
    """
    Main entry point to synchronize scraped sales to Google Sheet.
    Pulls configuration from config.json.
    """
    cfg = load_config()
    gs_cfg = cfg.get("google_sheets") or cfg.get("general", {}).get("google_sheets", {})

    # Automatically enabled if webhook_url is present, unless explicitly false
    is_enabled = gs_cfg.get("enabled")
    if is_enabled is None:
        is_enabled = bool(gs_cfg.get("webhook_url"))

    if not is_enabled:
        msg = "[Google Sheets] Sync is currently disabled in settings."
        if log_func:
            log_func(msg, "INFO")
        return {"success": False, "skipped": True, "message": msg}

    slot = "EOD" if is_eod else (time_slot or get_current_time_slot())
    date_label = date_str or get_slot_date(is_eod=is_eod)
    branches = format_branch_data(results_or_stores, cfg)

    payload = {
        "sheet_name": gs_cfg.get("sheet_name", "Sales Report - AirKitchen"),
        "is_eod": is_eod,
        "time_slot": slot,
        "date_str": date_label,
        "branches": branches,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }

    method = gs_cfg.get("method", "webhook").lower()
    log_msg = f"[Google Sheets] Syncing '{slot}' ({date_label}) to Google Sheet via {method.upper()}..."
    if log_func:
        log_func(log_msg, "INFO")
    else:
        logger.info(log_msg)

    if method == "webhook":
        webhook_url = gs_cfg.get("webhook_url", "").strip()
        if not webhook_url:
            err = "[Google Sheets] Webhook URL is empty. Please paste your Google Apps Script Webhook URL."
            if log_func:
                log_func(err, "WARNING")
            return {"success": False, "error": err}
        res = sync_via_webhook(webhook_url, payload)
    else:
        cred_file = os.path.join(BASE_DIR, gs_cfg.get("credentials_json", "google_credentials.json"))
        sheet_name = gs_cfg.get("spreadsheet_name", "Sales Report")
        res = sync_via_gspread(cred_file, sheet_name, payload)

    if res.get("success"):
        ok_msg = f"[Google Sheets] Successfully updated table for [{slot}] in sheet '{payload['sheet_name']}'!"
        if log_func:
            log_func(ok_msg, "SUCCESS")
        else:
            logger.info(ok_msg)
    else:
        fail_msg = f"[Google Sheets] Failed to update: {res.get('error')}"
        if log_func:
            log_func(fail_msg, "ERROR")
        else:
            logger.error(fail_msg)

    return res


if __name__ == "__main__":
    # Test script with dummy data
    test_results = [
        {"store_id": "grab_1", "amount": 37376.80},
        {"store_id": "panda_1", "amount": 4926.00},
        {"store_id": "grab_2", "amount": 18500.00},
        {"store_id": "panda_2", "amount": 3400.00},
        {"store_id": "grab_3_caloocan", "amount": 25100.00},
        {"store_id": "panda_3", "amount": 6200.00},
        {"store_id": "grab_4_san_fernando", "amount": 14200.00},
        {"store_id": "panda_4", "amount": 2800.00},
    ]
    branches = format_branch_data(test_results)
    print("Formatted branches payload:")
    print(json.dumps(branches, indent=2))
    print(f"Current time slot: {get_current_time_slot()}")
    print(f"Date: {get_slot_date()}")
