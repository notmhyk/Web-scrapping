import os
import sys
import json
import time
import queue
import threading
import webbrowser
from datetime import datetime
from flask import Flask, send_from_directory, jsonify, request, Response

from scraper_engine import ScraperEngine, CONFIG_FILE

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WEB_DIR = os.path.join(BASE_DIR, "web")

app = Flask(__name__, static_folder=WEB_DIR)

# Global State & Event Broadcasting
event_listeners = []
state_lock = threading.Lock()
EOD_FILE = os.path.join(BASE_DIR, "eod_yesterday.json")


def load_saved_eod() -> dict:
    """Loads saved EOD Yesterday records from disk."""
    if os.path.exists(EOD_FILE):
        try:
            with open(EOD_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_eod_data(data: dict):
    """Persists EOD Yesterday records to disk so viewers and restarts keep yesterday's figures."""
    try:
        data["eod_date"] = datetime.now().strftime("%Y-%m-%d")
        with open(EOD_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass


def is_eod_saved_for_today() -> bool:
    """Returns True if valid EOD data has already been recorded and saved for the current date."""
    saved_eod = load_saved_eod()
    if not saved_eod:
        return False
    
    today_str = datetime.now().strftime("%Y-%m-%d")
    ts = str(saved_eod.get("timestamp", ""))
    eod_date = str(saved_eod.get("eod_date", ""))
    
    # Check if recorded on today's date
    if today_str in ts or today_str in eod_date:
        stores = saved_eod.get("eod_stores", [])
        total = float(saved_eod.get("eod_total_sales", 0.0))
        if total > 0 or any(s.get("last_success") for s in stores):
            return True
    return False


app_state = {
    "branches": [],
    "stores": [],
    "total_sales": 0.0,
    "last_updated": "Not Synced Yet",
    "is_live_synced": False,
    "auto_running": False,
    "countdown_seconds": 0,
    "general": {},
    # Separate EOD Yesterday Store
    "eod_stores": [],
    "eod_total_sales": 0.0,
    "eod_last_updated": "Not recorded yet",
    "eod_recorded": False
}

task_queue = queue.Queue()
engine_ref = None


def broadcast_event(event_type: str, data: dict):
    """Sends SSE events to all connected browser clients."""
    msg = json.dumps({"type": event_type, **data})
    payload = f"data: {msg}\n\n"
    for listener in list(event_listeners):
        try:
            listener.put(payload)
        except Exception:
            event_listeners.remove(listener)


def log_listener(message: str, level: str = "INFO"):
    """Callback for ScraperEngine logs to stream directly to Web UI."""
    broadcast_event("log", {"message": message, "level": level})


def sync_sales_feed_file():
    """Writes static sales_feed.json in the web folder for static viewers and Cloudflare Pages sync."""
    try:
        feed_path = os.path.join(WEB_DIR, "sales_feed.json")
        with state_lock:
            snapshot = {
                "branches": app_state.get("branches", []),
                "stores": app_state.get("stores", []),
                "total_sales": app_state.get("total_sales", 0.0),
                "last_updated": app_state.get("last_updated", "Not Synced Yet"),
                "is_live_synced": app_state.get("is_live_synced", False),
                "auto_running": app_state.get("auto_running", False),
                "eod_stores": app_state.get("eod_stores", []),
                "eod_total_sales": app_state.get("eod_total_sales", 0.0),
                "eod_last_updated": app_state.get("eod_last_updated", "Not recorded yet"),
                "eod_recorded": app_state.get("eod_recorded", False),
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
        with open(feed_path, "w", encoding="utf-8") as f:
            json.dump(snapshot, f, indent=2)
    except Exception:
        pass


class PersistentScraperWorker(threading.Thread):
    """
    Dedicated worker thread that owns the ScraperEngine and Playwright instances.
    All Playwright calls execute exclusively on this thread for complete thread safety.
    """
    def __init__(self):
        super().__init__(daemon=True)
        self.engine = None
        self._running = True

    def run(self):
        global engine_ref
        self.engine = ScraperEngine(config_path=CONFIG_FILE, log_callback=log_listener)
        engine_ref = self.engine

        # Load clean fresh initial state into app_state (0 sales and Not Synced)
        with state_lock:
            app_state["branches"] = self.engine.config.get("branches", [])
            
            # Start clean with 0.00 sales on program launch (do not retain old previous session sales)
            raw_stores = self.engine.config.get("stores", [])
            fresh_stores = []
            for s in raw_stores:
                clean_store = json.loads(json.dumps(s))
                clean_store["last_amount"] = 0.0
                clean_store["last_raw_text"] = "Not Synced"
                clean_store["last_success"] = False
                clean_store["is_eod"] = False
                clean_store["status"] = "not_synced"
                fresh_stores.append(clean_store)
            
            app_state["stores"] = fresh_stores
            app_state["general"] = self.engine.config.get("general", {})
            app_state["google_sheets"] = self.engine.config.get("google_sheets", {})
            app_state["total_sales"] = 0.0
            app_state["last_updated"] = "Not Synced Yet"
            app_state["is_live_synced"] = False

            # Load persistent EOD records if available
            saved_eod = load_saved_eod()
            if saved_eod and saved_eod.get("eod_stores"):
                app_state["eod_stores"] = saved_eod.get("eod_stores", [])
                app_state["eod_total_sales"] = saved_eod.get("eod_total_sales", 0.0)
                app_state["eod_last_updated"] = saved_eod.get("eod_last_updated", "Saved EOD")
                app_state["eod_recorded"] = True
            else:
                app_state["eod_stores"] = json.loads(json.dumps(fresh_stores))
                app_state["eod_total_sales"] = 0.0
                app_state["eod_last_updated"] = "Not recorded yet"
                app_state["eod_recorded"] = False

        sync_sales_feed_file()

        def apply_store_result(res: dict, is_eod: bool = False):
            if not res or not res.get("store_id"):
                return
            sid = res.get("store_id")
            amt = float(res.get("amount", 0.0))
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            target_list = app_state["eod_stores"] if is_eod else app_state["stores"]

            with state_lock:
                for s in target_list:
                    if s["id"] == sid:
                        s["last_amount"] = amt
                        s["last_raw_text"] = res.get("raw_text", "")
                        s["last_success"] = res.get("success", False)
                        s["is_eod"] = is_eod
                        if res.get("cancelled"):
                            s["status"] = "idle"
                        elif res.get("success") and amt > 0:
                            s["status"] = "active"
                        elif amt == 0:
                            s["status"] = "check"
                        else:
                            s["status"] = "idle"

                # Check for shared store deduction (Caloocan Grab -> San Fernando Grab)
                shared = res.get("shared_sales")
                if shared and "caloocan" in str(sid).lower():
                    sf_amt = float(shared.get("san_fernando_sales", 0.0))
                    overall_amt = float(shared.get("overall_sales", 0.0))
                    cal_amt = float(shared.get("caloocan_sales", 0.0))
                    for s in target_list:
                        if "san_fernando" in s["id"].lower() and s.get("platform") == "grab":
                            s["last_amount"] = sf_amt
                            s["last_raw_text"] = f"₱{sf_amt:,.2f} (Overall ₱{overall_amt:,.2f} - Caloocan ₱{cal_amt:,.2f})"
                            s["last_success"] = True
                            s["is_eod"] = is_eod
                            s["status"] = "active" if sf_amt > 0 else "idle"

                if is_eod:
                    app_state["eod_total_sales"] = sum(s.get("last_amount", 0.0) for s in app_state["eod_stores"])
                    app_state["eod_last_updated"] = f"{now_str} (Yesterday EOD)"
                    app_state["eod_recorded"] = True
                    save_eod_data({
                        "eod_stores": app_state["eod_stores"],
                        "eod_total_sales": app_state["eod_total_sales"],
                        "eod_last_updated": app_state["eod_last_updated"],
                        "timestamp": now_str
                    })
                else:
                    app_state["total_sales"] = sum(s.get("last_amount", 0.0) for s in app_state["stores"])
                    app_state["last_updated"] = now_str
                    app_state["is_live_synced"] = True

            sync_sales_feed_file()
            broadcast_event("status_update", {
                "branches": app_state["branches"],
                "stores": app_state["stores"],
                "total_sales": app_state["total_sales"],
                "last_updated": app_state["last_updated"],
                "is_live_synced": app_state["is_live_synced"],
                "eod_stores": app_state["eod_stores"],
                "eod_total_sales": app_state["eod_total_sales"],
                "eod_last_updated": app_state["eod_last_updated"],
                "just_scraped": res
            })

        while self._running:
            try:
                task_type, args = task_queue.get(timeout=0.5)
            except queue.Empty:
                continue

            if task_type == "STOP":
                break

            try:
                if task_type == "launch_all":
                    self.engine.launch_all_browsers()
                elif task_type == "launch_single":
                    profile_id = args.get("profile_id", "grab_1")
                    self.engine.launch_profile_browser(profile_id, focus_url=True)

                elif task_type == "startup_eod_then_live":
                    self.engine.reset_stop()
                    force_eod = args.get("force_eod", False)
                    if not force_eod and is_eod_saved_for_today():
                        log_listener("[Startup Flow] EOD is already recorded for today. Skipping EOD scrape and starting Live Operations directly...", "INFO")
                    else:
                        # Step 1: Scrape & Save EOD Yesterday first with real-time per-store updates
                        log_listener("[Startup Flow] Step 1/2: Scraping and saving EOD Yesterday sales first...", "INFO")
                        with state_lock:
                            for s in app_state["eod_stores"]:
                                s["status"] = "scraping"
                        broadcast_event("status_update", {"stores": app_state["stores"], "eod_stores": app_state["eod_stores"]})

                        eod_results = self.engine.scrape_all(is_eod=True, on_store_scraped=lambda r: apply_store_result(r, is_eod=True))
                        
                        if self.engine.stop_requested:
                            continue

                        log_listener(f"[Startup Flow] EOD Yesterday recorded and saved: ₱{app_state['eod_total_sales']:,.2f}", "SUCCESS")
                        time.sleep(1.0)

                    # Step 2: Proceed to Live Scraping with real-time per-store updates
                    log_listener("[Live Scraping] Starting Live Operations scraping across all 4 cities...", "INFO")
                    with state_lock:
                        for s in app_state["stores"]:
                            s["status"] = "scraping"
                    broadcast_event("status_update", {"stores": app_state["stores"], "eod_stores": app_state["eod_stores"]})

                    live_results = self.engine.scrape_all(is_eod=False, on_store_scraped=lambda r: apply_store_result(r, is_eod=False))
                    
                    # Auto-sync live sales to Google Sheet
                    try:
                        from google_sheets_sync import sync_sales_to_google_sheet
                        with state_lock:
                            stores_snapshot = [dict(s) for s in app_state["stores"]]
                        sync_sales_to_google_sheet(stores_snapshot, is_eod=False, log_func=log_listener)
                    except Exception as ge:
                        log_listener(f"Google Sheets sync notice: {ge}", "WARNING")

                    broadcast_event("scrape_finished", {
                        "data": {
                            "branches": app_state["branches"],
                            "stores": app_state["stores"],
                            "total_sales": app_state["total_sales"],
                            "last_updated": app_state["last_updated"],
                            "is_live_synced": True,
                            "eod_stores": app_state["eod_stores"],
                            "eod_total_sales": app_state["eod_total_sales"],
                            "eod_last_updated": app_state["eod_last_updated"]
                        }
                    })

                elif task_type == "scrape_all":
                    self.engine.reset_stop()
                    with state_lock:
                        for s in app_state["stores"]:
                            s["status"] = "scraping"
                    broadcast_event("status_update", {"stores": app_state["stores"], "eod_stores": app_state["eod_stores"]})

                    results = self.engine.scrape_all(is_eod=False, on_store_scraped=lambda r: apply_store_result(r, is_eod=False))

                    # Auto-sync live sales to Google Sheet
                    try:
                        from google_sheets_sync import sync_sales_to_google_sheet
                        with state_lock:
                            stores_snapshot = [dict(s) for s in app_state["stores"]]
                        sync_sales_to_google_sheet(stores_snapshot, is_eod=False, log_func=log_listener)
                    except Exception as ge:
                        log_listener(f"Google Sheets sync notice: {ge}", "WARNING")

                    broadcast_event("scrape_finished", {
                        "data": {
                            "branches": app_state["branches"],
                            "stores": app_state["stores"],
                            "total_sales": app_state["total_sales"],
                            "last_updated": app_state["last_updated"],
                            "is_live_synced": True,
                            "eod_stores": app_state["eod_stores"],
                            "eod_total_sales": app_state["eod_total_sales"],
                            "eod_last_updated": app_state["eod_last_updated"]
                        }
                    })

                elif task_type == "scrape_eod":
                    self.engine.reset_stop()
                    with state_lock:
                        for s in app_state["eod_stores"]:
                            s["status"] = "scraping"
                    broadcast_event("status_update", {"stores": app_state["stores"], "eod_stores": app_state["eod_stores"]})

                    results = self.engine.scrape_all(is_eod=True, on_store_scraped=lambda r: apply_store_result(r, is_eod=True))

                    # Auto-sync EOD sales to Google Sheet (Table S44)
                    try:
                        from google_sheets_sync import sync_sales_to_google_sheet
                        with state_lock:
                            eod_snapshot = [dict(s) for s in app_state["eod_stores"]]
                        sync_sales_to_google_sheet(eod_snapshot, is_eod=True, log_func=log_listener)
                    except Exception as ge:
                        log_listener(f"Google Sheets sync notice: {ge}", "WARNING")

                    broadcast_event("eod_updated", {
                        "eod_stores": app_state["eod_stores"],
                        "eod_total_sales": app_state["eod_total_sales"],
                        "eod_last_updated": app_state["eod_last_updated"]
                    })
                    broadcast_event("scrape_finished", {
                        "data": {
                            "branches": app_state["branches"],
                            "stores": app_state["stores"],
                            "total_sales": app_state["total_sales"],
                            "last_updated": app_state["last_updated"],
                            "eod_stores": app_state["eod_stores"],
                            "eod_total_sales": app_state["eod_total_sales"],
                            "eod_last_updated": app_state["eod_last_updated"]
                        }
                    })

                elif task_type in ("scrape_single", "scrape_single_eod"):
                    self.engine.reset_stop()
                    store_id = args.get("store_id")
                    is_eod = (task_type == "scrape_single_eod") or args.get("is_eod", False)
                    target_list = app_state["eod_stores"] if is_eod else app_state["stores"]
                    with state_lock:
                        for s in target_list:
                            if s["id"] == store_id:
                                s["status"] = "scraping"
                    broadcast_event("status_update", {"stores": app_state["stores"], "eod_stores": app_state["eod_stores"]})

                    res = self.engine.scrape_store(store_id, is_eod=is_eod)
                    apply_store_result(res, is_eod=is_eod)

                elif task_type in ("scrape_branch", "scrape_branch_eod"):
                    self.engine.reset_stop()
                    branch_id = args.get("branch_id")
                    is_eod = (task_type == "scrape_branch_eod") or args.get("is_eod", False)
                    target_list = app_state["eod_stores"] if is_eod else app_state["stores"]
                    branch = next((b for b in app_state.get("branches", []) if b["id"] == branch_id), None)
                    if branch:
                        with state_lock:
                            for s in target_list:
                                if s["id"] in (branch.get("grab_store_id"), branch.get("panda_store_id")):
                                    s["status"] = "scraping"
                        broadcast_event("status_update", {"stores": app_state["stores"], "eod_stores": app_state["eod_stores"]})

                    b_res = self.engine.scrape_branch(branch_id, is_eod=is_eod, on_store_scraped=lambda r: apply_store_result(r, is_eod=is_eod))

                    broadcast_event("scrape_finished", {
                        "data": {
                            "branches": app_state["branches"],
                            "stores": app_state["stores"],
                            "total_sales": app_state["total_sales"],
                            "last_updated": app_state["last_updated"],
                            "eod_stores": app_state["eod_stores"],
                            "eod_total_sales": app_state["eod_total_sales"],
                            "eod_last_updated": app_state["eod_last_updated"]
                        }
                    })

                elif task_type == "train_single":
                    store_id = args.get("store_id")

                    def on_single_done(sel, sample_text):
                        broadcast_event("training_complete", {
                            "message": f"Successfully captured selector for [{store_id}]!\n\nSelector: {sel}\nSample: {sample_text}"
                        })

                    self.engine.train_single_picker(store_id, is_eod=False, on_selector_found=on_single_done)

                elif task_type == "train_eod":
                    store_id = args.get("store_id")

                    def on_eod_done(sel, sample_text):
                        with state_lock:
                            for s in app_state["stores"]:
                                if s["id"] == store_id:
                                    s["eod_selector"] = sel
                        broadcast_event("training_complete", {
                            "message": f"Successfully completed 3-Step EOD Training for [{store_id}]!\n\nEOD Sales Selector: {sel}\nSample: {sample_text}\n\nSaved permanently for all future EOD scrapes!"
                        })

                    self.engine.train_eod_wizard(store_id, on_complete=on_eod_done)

                elif task_type == "train_multi":
                    store_id = args.get("store_id")

                    def on_multi_done(selectors, total_sum, count):
                        with state_lock:
                            for s in app_state["stores"]:
                                if s["id"] == store_id:
                                    s["multi_selectors"] = selectors
                                    s["expected_count"] = count
                        broadcast_event("training_complete", {
                            "message": f"Successfully trained {count} stores for [{store_id}]!\n\nPreview Total: ₱{total_sum:,.2f}\n\nThese stores will be summed automatically on every scrape."
                        })

                    self.engine.train_multi_picker(store_id, on_complete=on_multi_done)

                elif task_type == "train_csv_export":
                    store_id = args.get("store_id")

                    def on_csv_done(steps, parsed_res):
                        msg = f"Successfully recorded {len(steps)} CSV Export step(s) for [{store_id}]!\n\n"
                        if parsed_res and parsed_res.get("success"):
                            msg += (
                                f"Initial CSV Parsed Successfully:\n"
                                f"• Total Stores: {parsed_res.get('total_stores_found', 0)}\n"
                                f"• Caloocan Total: ₱{parsed_res.get('caloocan_sales', 0):,.2f} ({parsed_res.get('caloocan_count', 0)} stores)\n"
                                f"• San Fernando Total: ₱{parsed_res.get('san_fernando_sales', 0):,.2f} ({parsed_res.get('san_fernando_count', 0)} stores)\n"
                                f"• Grand Combined Total: ₱{parsed_res.get('total_sales', 0):,.2f}\n\n"
                                f"These steps are saved permanently and will auto-download on every scrape!"
                            )
                        else:
                            msg += "Export steps saved! On the next scrape, the CSV will download and parse automatically."

                        broadcast_event("training_complete", {"message": msg})

                    self.engine.train_csv_export_steps(store_id, on_complete=on_csv_done)

                elif task_type == "tile_all":
                    self.engine.snap_all_windows()

                elif task_type == "update_settings":
                    gen = args.get("general", {})
                    if gen:
                        self.engine.config.setdefault("general", {}).update(gen)
                    gs = args.get("google_sheets", {})
                    if gs:
                        self.engine.config.setdefault("google_sheets", {}).update(gs)
                    self.engine.save_config()
                    with state_lock:
                        app_state["general"] = self.engine.config.get("general", {})
                        app_state["google_sheets"] = self.engine.config.get("google_sheets", {})

            except Exception as e:
                log_listener(f"Worker Error: {e}", "ERROR")
            finally:
                task_queue.task_done()

        if self.engine:
            try:
                self.engine.close_all()
            except Exception:
                pass


# Background Auto-Scrape & Hourly / Midnight Scheduler Thread
def auto_scrape_timer_loop():
    executed_eod_slots = set()
    executed_hourly_slots = set()
    while True:
        time.sleep(1)
        now = datetime.now()
        
        # 1. Automated Scheduled EOD at 12:00 AM Midnight and 1:00 AM daily
        if now.hour in (0, 1):
            slot_key = f"{now.strftime('%Y-%m-%d')}_{now.hour:02d}"
            if slot_key not in executed_eod_slots:
                executed_eod_slots.add(slot_key)
                hour_label = "12:00 AM Midnight" if now.hour == 0 else "1:00 AM"
                log_listener(f"[Scheduled EOD] Clock reached {hour_label}. Automatically scraping & recording Yesterday's EOD to Google Sheet (S44)...", "INFO")
                task_queue.put(("scrape_eod", {}))

        # 2. Automated Hourly Trigger at the top of every hour (:00)
        if now.minute == 0:
            hour_slot_key = now.strftime("%Y-%m-%d_%H")
            if hour_slot_key not in executed_hourly_slots:
                executed_hourly_slots.add(hour_slot_key)
                slot_name = now.strftime("%I:00 %p").lstrip("0")
                log_listener(f"[Hourly Auto-Trigger] Clock reached {slot_name}. Triggering automated scrape & Google Sheet update...", "INFO")
                task_queue.put(("scrape_all", {}))

        # 3. Periodic Auto-Scraping Countdown Interval (when enabled)
        with state_lock:
            running = app_state["auto_running"]
            if running:
                if app_state["countdown_seconds"] > 0:
                    app_state["countdown_seconds"] -= 1
                else:
                    interval_mins = app_state.get("general", {}).get("interval_minutes", 60)
                    app_state["countdown_seconds"] = interval_mins * 60
                    log_listener(f"Interval reached ({interval_mins} min). Triggering scrape across all 4 cities...", "INFO")
                    task_queue.put(("scrape_all", {}))


# --- Flask Routes & Public Tunnel Security Guard ---

def is_external_visitor() -> bool:
    """Checks if the incoming request is from a public Cloudflare Tunnel visitor vs local computer."""
    host = request.headers.get("Host", "").lower()
    cf_ip = request.headers.get("CF-Connecting-IP")
    cf_ray = request.headers.get("CF-Ray")
    x_forwarded = request.headers.get("X-Forwarded-For")
    
    # Any traffic routed through trycloudflare.com or Cloudflare reverse proxy is external
    if "trycloudflare.com" in host or "cloudflare" in host or cf_ip or cf_ray:
        return True
    
    # If host is not localhost or 127.0.0.1
    if host and not host.startswith("localhost") and not host.startswith("127.0.0.1"):
        return True
        
    return False


@app.before_request
def enforce_read_only_for_external():
    """
    Security Middleware:
    If a visitor connects from Cloudflare or outside your PC, they are STRICTLY LOCKED
    into the Read-Only Executive Viewer. Admin controls and action endpoints are blocked.
    """
    if is_external_visitor():
        path = request.path
        
        # 1. Block any write/action POST requests from external visitors
        if request.method != "GET":
            return jsonify({
                "error": "Forbidden",
                "message": "Read-Only Executive Mode is active on public links. Actions cannot be triggered externally."
            }), 403

        # 2. If an external visitor tries to load admin app.js or index.html directly, redirect to viewer
        if path in ("/index.html", "/app.js", "/static/app.js"):
            return send_from_directory(WEB_DIR, "viewer.html")


@app.after_request
def add_cors_headers(response):
    """Enable CORS so static cloud dashboards can read the live JSON feed."""
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type,Authorization"
    response.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
    return response


@app.route("/")
def index():
    """
    Root Route:
    - External Cloudflare visitors: ALWAYS see the Read-Only Viewer (even without /viewer in the URL!).
    - Local computer (you): Sees the full Admin Dashboard.
    """
    if is_external_visitor():
        return send_from_directory(WEB_DIR, "viewer.html")
    return send_from_directory(WEB_DIR, "index.html")


@app.route("/viewer")
@app.route("/boss")
@app.route("/view")
@app.route("/dashboard")
def viewer():
    """Serves the read-only executive dashboard without admin or control tools."""
    return send_from_directory(WEB_DIR, "viewer.html")


@app.route("/sales_feed.json")
def serve_sales_feed():
    """Serves static sales snapshot for static website integrations."""
    feed_path = os.path.join(WEB_DIR, "sales_feed.json")
    if os.path.exists(feed_path):
        return send_from_directory(WEB_DIR, "sales_feed.json")
    with state_lock:
        return jsonify(app_state)


@app.route("/static/<path:path>")
def serve_static(path):
    if is_external_visitor() and path == "app.js":
        return send_from_directory(WEB_DIR, "viewer.js")
    return send_from_directory(WEB_DIR, path)


@app.route("/<path:filename>")
def serve_root_file(filename):
    if is_external_visitor() and filename in ("index.html", "app.js"):
        return send_from_directory(WEB_DIR, "viewer.html")
    target = os.path.join(WEB_DIR, filename)
    if os.path.isfile(target):
        return send_from_directory(WEB_DIR, filename)
    return send_from_directory(WEB_DIR, "viewer.html" if is_external_visitor() else "index.html")


@app.route("/api/status", methods=["GET"])
def get_status():
    with state_lock:
        return jsonify(app_state)


@app.route("/api/events")
def sse_events():
    def event_stream():
        q = queue.Queue()
        event_listeners.append(q)
        try:
            while True:
                payload = q.get()
                yield payload
        except GeneratorExit:
            if q in event_listeners:
                event_listeners.remove(q)

    return Response(event_stream(), mimetype="text/event-stream")


@app.route("/api/launch_browsers", methods=["POST"])
def api_launch_browsers():
    task_queue.put(("launch_all", {}))
    return jsonify({"status": "queued"})


@app.route("/api/tile_browsers", methods=["POST"])
def api_tile_browsers():
    task_queue.put(("tile_all", {}))
    return jsonify({"status": "queued"})


@app.route("/api/scrape_all", methods=["POST"])
def api_scrape_all():
    global engine_ref
    if engine_ref:
        engine_ref.reset_stop()
    task_queue.put(("scrape_all", {}))
    return jsonify({"status": "queued"})


@app.route("/api/scrape_eod", methods=["POST"])
def api_scrape_eod():
    global engine_ref
    if engine_ref:
        engine_ref.reset_stop()
    task_queue.put(("scrape_eod", {}))
    return jsonify({"status": "queued"})


@app.route("/api/scrape_single/<store_id>", methods=["POST"])
def api_scrape_single(store_id):
    global engine_ref
    if engine_ref:
        engine_ref.reset_stop()
    task_queue.put(("scrape_single", {"store_id": store_id}))
    return jsonify({"status": "queued"})


@app.route("/api/scrape_single_eod/<store_id>", methods=["POST"])
def api_scrape_single_eod(store_id):
    global engine_ref
    if engine_ref:
        engine_ref.reset_stop()
    task_queue.put(("scrape_single_eod", {"store_id": store_id, "is_eod": True}))
    return jsonify({"status": "queued"})


@app.route("/api/scrape_branch/<branch_id>", methods=["POST"])
def api_scrape_branch(branch_id):
    global engine_ref
    if engine_ref:
        engine_ref.reset_stop()
    task_queue.put(("scrape_branch", {"branch_id": branch_id}))
    return jsonify({"status": "queued"})


@app.route("/api/scrape_branch_eod/<branch_id>", methods=["POST"])
def api_scrape_branch_eod(branch_id):
    global engine_ref
    if engine_ref:
        engine_ref.reset_stop()
    task_queue.put(("scrape_branch_eod", {"branch_id": branch_id, "is_eod": True}))
    return jsonify({"status": "queued"})


@app.route("/api/focus_browser/<profile_id>", methods=["POST"])
def api_focus_browser(profile_id):
    task_queue.put(("launch_single", {"profile_id": profile_id}))
    return jsonify({"status": "queued"})


@app.route("/api/train_single/<store_id>", methods=["POST"])
def api_train_single(store_id):
    task_queue.put(("train_single", {"store_id": store_id}))
    return jsonify({"status": "queued"})


@app.route("/api/train_eod/<store_id>", methods=["POST"])
def api_train_eod(store_id):
    task_queue.put(("train_eod", {"store_id": store_id}))
    return jsonify({"status": "queued"})


@app.route("/api/train_multi/<store_id>", methods=["POST"])
def api_train_multi(store_id):
    task_queue.put(("train_multi", {"store_id": store_id}))
    return jsonify({"status": "queued"})


@app.route("/api/train_csv_export/<store_id>", methods=["POST"])
def api_train_csv_export(store_id):
    task_queue.put(("train_csv_export", {"store_id": store_id}))
    return jsonify({"status": "queued"})


@app.route("/api/stop_scraping", methods=["POST"])
def api_stop_scraping():
    global engine_ref
    if engine_ref:
        engine_ref.request_stop()

    with state_lock:
        app_state["auto_running"] = False
        app_state["countdown_seconds"] = 0
        for s in app_state["stores"]:
            if s.get("status") in ("scraping", "retrying"):
                s["status"] = "active" if s.get("last_amount", 0.0) > 0 else "idle"
        for s in app_state["eod_stores"]:
            if s.get("status") in ("scraping", "retrying"):
                s["status"] = "active" if s.get("last_amount", 0.0) > 0 else "idle"

    # Clear pending tasks from queue
    while not task_queue.empty():
        try:
            task_queue.get_nowait()
            task_queue.task_done()
        except Exception:
            pass

    log_listener("[Stop] Scraping cancelled and stopped by user.", "WARNING")
    sync_sales_feed_file()
    broadcast_event("status_update", {
        "branches": app_state["branches"],
        "stores": app_state["stores"],
        "eod_stores": app_state["eod_stores"],
        "auto_running": False,
        "countdown_seconds": 0
    })
    return jsonify({"status": "success", "message": "Scraping cancelled and stopped"})


@app.route("/api/toggle_auto", methods=["POST"])
def api_toggle_auto():
    global engine_ref
    data = request.json or {}
    running = data.get("running", True)
    with state_lock:
        app_state["auto_running"] = running
        if running:
            if engine_ref:
                engine_ref.reset_stop()
            interval_mins = app_state.get("general", {}).get("interval_minutes", 1)
            app_state["countdown_seconds"] = interval_mins * 60
            if is_eod_saved_for_today():
                log_listener("[Auto Scrape] EOD is already recorded for today. Starting Live Operations...", "INFO")
                task_queue.put(("scrape_all", {}))
            else:
                log_listener("[Auto Scrape] No saved EOD found for today. Executing initial EOD Yesterday scrape before starting live cycle...", "INFO")
                task_queue.put(("startup_eod_then_live", {"force_eod": False}))
        else:
            app_state["countdown_seconds"] = 0
            if engine_ref:
                engine_ref.request_stop()
    return jsonify({"status": "success", "auto_running": running})


@app.route("/api/startup_eod_flow", methods=["POST"])
def api_startup_eod_flow():
    task_queue.put(("startup_eod_then_live", {}))
    return jsonify({"status": "queued"})


@app.route("/api/update_settings", methods=["POST"])
def api_update_settings():
    data = request.json or {}
    with state_lock:
        if "general" in data:
            app_state.setdefault("general", {}).update(data["general"])
            gen = data["general"]
            if "interval_minutes" in gen and app_state["auto_running"]:
                app_state["countdown_seconds"] = gen["interval_minutes"] * 60
        else:
            app_state.setdefault("general", {}).update(data)
            if "interval_minutes" in data and app_state["auto_running"]:
                app_state["countdown_seconds"] = data["interval_minutes"] * 60

        if "google_sheets" in data:
            app_state.setdefault("google_sheets", {}).update(data["google_sheets"])

    task_queue.put(("update_settings", data))
    return jsonify({"status": "success"})


@app.route("/api/sync_google_sheets", methods=["POST"])
def api_sync_google_sheets():
    """Manual or triggered sync to Google Sheet."""
    data = request.json or {}
    is_eod = data.get("is_eod", False)
    time_slot = data.get("time_slot")
    date_str = data.get("date_str")

    with state_lock:
        target_stores = app_state.get("eod_stores", []) if is_eod else app_state.get("stores", [])

    try:
        from google_sheets_sync import sync_sales_to_google_sheet
        result = sync_sales_to_google_sheet(
            target_stores,
            is_eod=is_eod,
            time_slot=time_slot,
            date_str=date_str,
            log_func=log_listener
        )
        return jsonify(result)
    except Exception as e:
        log_listener(f"[Google Sheets] Sync error: {e}", "ERROR")
        return jsonify({"success": False, "error": str(e)}), 500



@app.route("/api/open_file/<ftype>", methods=["POST"])
def api_open_file(ftype):
    filename = "sales_records.csv" if ftype == "csv" else "sales_records.txt"
    filepath = os.path.join(BASE_DIR, filename)
    if not os.path.exists(filepath):
        with open(filepath, "w", encoding="utf-8") as f:
            if ftype == "csv":
                f.write("Timestamp,Store ID,Store Name,Platform,Raw Text,Parsed Amount,Status\n")
            else:
                f.write("=== SALES RECORDS LOG (4 CITIES) ===\n\n")
    try:
        os.startfile(filepath)
        return jsonify({"status": "opened", "file": filename})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


def main():
    # Start persistent Playwright background worker
    worker = PersistentScraperWorker()
    worker.start()

    # Start timer loop
    timer_thread = threading.Thread(target=auto_scrape_timer_loop, daemon=True)
    timer_thread.start()

    port = 5000
    dashboard_url = f"http://localhost:{port}"
    print(f"\n=======================================================")
    print(f"  Multi-Store Sales Scraper Web Dashboard Active")
    print(f"  URL: {dashboard_url}")
    print(f"=======================================================\n")

    # Automatically open browser tab
    def open_browser():
        time.sleep(1.2)
        webbrowser.open(dashboard_url)

    threading.Thread(target=open_browser, daemon=True).start()

    # Run Flask server
    app.run(host="127.0.0.1", port=port, debug=False)


if __name__ == "__main__":
    main()
