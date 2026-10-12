"""
Background Google Sheets Auto-Sync Daemon.
Continuously monitors http://localhost:5000/api/status.
Whenever a new scrape finishes (live or EOD), it automatically updates the respective table on Google Sheets!
"""
import time
import logging
import requests
from datetime import datetime
import google_sheets_sync

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [Watcher] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("SheetsWatcher")


def run_watcher():
    logger.info("Google Sheets Auto-Sync Watcher is now active.")
    last_live_update = None
    last_eod_update = None

    while True:
        data = None
        for port in (5001, 5000):
            try:
                resp = requests.get(f"http://localhost:{port}/api/status", timeout=2)
                if resp.status_code == 200:
                    data = resp.json()
                    break
            except Exception:
                continue

        if data:
            try:
                # 1. Check for new Live Scrape
                current_live = data.get("last_updated")
                if current_live and current_live not in ("Not Synced Yet", "") and current_live != last_live_update:
                    if last_live_update is not None:
                        logger.info(f"New live scrape detected: {current_live}. Syncing to Google Sheet...")
                        stores = data.get("stores", [])
                        if stores:
                            res = google_sheets_sync.sync_sales_to_google_sheet(stores, is_eod=False)
                            logger.info(f"Sync result: {res.get('message') or res.get('error')}")
                    last_live_update = current_live

                # 2. Check for new EOD Scrape
                current_eod = data.get("eod_last_updated")
                if current_eod and current_eod not in ("Not recorded yet", "Saved EOD", "") and current_eod != last_eod_update:
                    if last_eod_update is not None:
                        logger.info(f"New EOD scrape detected: {current_eod}. Syncing to S44 in Google Sheet...")
                        eod_stores = data.get("eod_stores", [])
                        if eod_stores:
                            res = google_sheets_sync.sync_sales_to_google_sheet(eod_stores, is_eod=True)
                            logger.info(f"EOD Sync result: {res.get('message') or res.get('error')}")
                    last_eod_update = current_eod
            except Exception as ex:
                logger.warning(f"Watcher sync notice: {ex}")

        time.sleep(3)


if __name__ == "__main__":
    run_watcher()
