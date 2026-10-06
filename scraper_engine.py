import os
import json
import re
import csv
import time
import logging
import ctypes
import ctypes.wintypes
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Callable, Any
from playwright.sync_api import sync_playwright, Playwright, BrowserContext, Page

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("ScraperEngine")

CONFIG_FILE = "config.json"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROFILES_DIR = os.path.join(BASE_DIR, "browser_profiles")
os.makedirs(PROFILES_DIR, exist_ok=True)


def get_screen_work_area() -> dict:
    """Returns usable screen area excluding the Windows taskbar."""
    try:
        rect = ctypes.wintypes.RECT()
        if ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(rect), 0):
            w = rect.right - rect.left
            h = rect.bottom - rect.top
            if w > 400 and h > 300:
                return {"x": rect.left, "y": rect.top, "width": w, "height": h}
    except Exception:
        pass
    return {"x": 0, "y": 0, "width": 1280, "height": 680}


def get_dynamic_quadrants(work_area: Optional[dict] = None) -> Dict[str, dict]:
    """Calculates non-overlapping 2-row x 4-column (4 Grab on top, 4 Panda on bottom) screen coordinates."""
    wa = work_area or get_screen_work_area()
    w = wa.get("width", 1280)
    h = wa.get("height", 680)
    left = wa.get("x", 0)
    top = wa.get("y", 0)

    top_h = h // 2
    bot_h = h - top_h

    col_w = w // 4
    w1 = col_w
    w2 = col_w
    w3 = col_w
    w4 = w - (col_w * 3)

    return {
        # Top Row: Grab Browsers
        "grab_1": {"x": left, "y": top, "width": w1, "height": top_h},
        "grab_2": {"x": left + w1, "y": top, "width": w2, "height": top_h},
        "grab_3": {"x": left + w1 + w2, "y": top, "width": w3, "height": top_h},
        "grab_4": {"x": left + w1 + w2 + w3, "y": top, "width": w4, "height": top_h},
        # Bottom Row: Foodpanda Browsers
        "panda_1": {"x": left, "y": top + top_h, "width": w1, "height": bot_h},
        "panda_2": {"x": left + w1, "y": top + top_h, "width": w2, "height": bot_h},
        "panda_3": {"x": left + w1 + w2, "y": top + top_h, "width": w3, "height": bot_h},
        "panda_4": {"x": left + w1 + w2 + w3, "y": top + top_h, "width": w4, "height": bot_h}
    }


class ScraperEngine:
    def __init__(self, config_path: str = CONFIG_FILE, log_callback: Optional[Callable[[str, str], None]] = None):
        self.config_path = os.path.join(BASE_DIR, config_path)
        self.log_callback = log_callback or self._default_log
        self.config = self.load_config()
        self.playwright: Optional[Playwright] = None
        self.contexts: Dict[str, BrowserContext] = {}
        self.pages: Dict[str, Page] = {}
        self.hwnds: Dict[str, int] = {}
        self.cached_shared_sales: Dict[str, Any] = {}
        self.is_running = False
        self.stop_requested = False

    def request_stop(self):
        """Requests immediate cancellation and stopping of ongoing scrape operations."""
        self.stop_requested = True
        self.log("[Stop] Scraping stop requested. Terminating current scrape operations...", "WARNING")

    def reset_stop(self):
        """Resets the cancellation flag before starting a new scrape operation."""
        self.stop_requested = False

    def _default_log(self, message: str, level: str = "INFO"):
        logger.log(getattr(logging, level.upper(), logging.INFO), message)

    def log(self, message: str, level: str = "INFO"):
        self.log_callback(message, level)

    def resolve_url(self, raw_url: str, is_eod: bool = False) -> str:
        """Resolves dynamic dates (DD/MM/YY) for Grab finances pages and URLs (Today for Ops, Yesterday for EOD)."""
        if not raw_url:
            return ""
        today_str = datetime.now().strftime("%d/%m/%y")
        yesterday_str = (datetime.now() - timedelta(days=1)).strftime("%d/%m/%y")
        target_date = yesterday_str if is_eod else today_str

        url = raw_url.replace("{CURRENT_DATE}", target_date).replace("{DATE}", target_date).replace("{YESTERDAY_DATE}", yesterday_str)
        url = re.sub(r'startDate=\d{2}/\d{2}/\d{2}', f'startDate={target_date}', url)
        url = re.sub(r'endDate=\d{2}/\d{2}/\d{2}', f'endDate={target_date}', url)
        return url

    def load_config(self) -> dict:
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                self.log(f"Error reading config: {e}", "ERROR")
        return {
            "general": {
                "interval_minutes": 1,
                "auto_refresh": True,
                "refresh_wait_seconds": 5,
                "force_retry_on_zero": True,
                "max_retries": 10,
                "txt_output_path": "sales_records.txt",
                "csv_output_path": "sales_records.csv",
                "headless": False
            },
            "stores": []
        }

    def save_config(self):
        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=2)
            self.log("Configuration updated successfully.", "SUCCESS")
        except Exception as e:
            self.log(f"Error saving config: {e}", "ERROR")

    def ensure_playwright(self):
        if self.playwright is None:
            self.playwright = sync_playwright().start()

    def get_profile_dir(self, profile_id: str) -> str:
        profile_path = os.path.join(PROFILES_DIR, profile_id)
        os.makedirs(profile_path, exist_ok=True)
        return profile_path

    def snap_window(self, profile_id: str, quad: dict, page: Optional[Page] = None):
        """Locks the specific Chromium window into its designated non-overlapping screen quadrant."""
        try:
            hwnd = self.hwnds.get(profile_id)
            if not hwnd or not ctypes.windll.user32.IsWindow(hwnd):
                if page and not page.is_closed():
                    marker = f"__MHYK_WIN_{profile_id}__"
                    try:
                        page.evaluate(f"() => {{ document.title = '{marker}'; }}")
                        time.sleep(0.12)
                    except Exception:
                        pass
                    
                    found = None
                    def enum_cb(h, lparam):
                        nonlocal found
                        length = ctypes.windll.user32.GetWindowTextLengthW(h)
                        if length > 0:
                            buff = ctypes.create_unicode_buffer(length + 1)
                            ctypes.windll.user32.GetWindowTextW(h, buff, length + 1)
                            if marker in buff.value:
                                found = h
                                return False
                        return True

                    EnumProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
                    ctypes.windll.user32.EnumWindows(EnumProc(enum_cb), 0)
                    if found:
                        hwnd = found
                        self.hwnds[profile_id] = hwnd

            if hwnd and ctypes.windll.user32.IsWindow(hwnd):
                # Flags: SWP_NOZORDER (0x0004) | SWP_SHOWWINDOW (0x0040) | SWP_NOACTIVATE (0x0010)
                ctypes.windll.user32.SetWindowPos(
                    hwnd,
                    0,
                    int(quad.get("x", 0)),
                    int(quad.get("y", 0)),
                    int(quad.get("width", 426)),
                    int(quad.get("height", 340)),
                    0x0004 | 0x0040 | 0x0010
                )
        except Exception as e:
            self.log(f"Window snap error for [{profile_id}]: {e}", "DEBUG")

    def snap_all_windows(self):
        """Snaps all open browser windows to their exact non-overlapping screen coordinates."""
        dynamic_quads = get_dynamic_quadrants()
        for pid, page in list(self.pages.items()):
            if page and not page.is_closed():
                quad = dynamic_quads.get(pid, {"x": 0, "y": 0, "width": 426, "height": 340})
                self.snap_window(pid, quad, page)

    def launch_profile_browser(self, profile_id: str, focus_url: bool = True) -> Optional[Page]:
        """Launches or connects to a persistent browser window with locked screen position."""
        self.ensure_playwright()

        instance = next((b for b in self.config.get("browser_instances", []) if b["profile_id"] == profile_id), None)
        if not instance:
            store = next((s for s in self.config.get("stores", []) if s.get("profile_id", s["id"]) == profile_id), None)
            if store:
                instance = {
                    "profile_id": profile_id,
                    "name": store["name"],
                    "url": store.get("url", "https://merchant.grab.com/portal"),
                    "quadrant": store.get("quadrant", {"x": 0, "y": 0, "width": 426, "height": 340})
                }
            else:
                instance = {
                    "profile_id": profile_id,
                    "name": profile_id,
                    "url": "https://merchant.grab.com/portal",
                    "quadrant": {"x": 0, "y": 0, "width": 426, "height": 340}
                }

        target_url = self.resolve_url(instance.get("url", ""))
        dynamic_quads = get_dynamic_quadrants()
        quad = dynamic_quads.get(profile_id) or instance.get("quadrant", {"x": 0, "y": 0, "width": 426, "height": 340})

        # If already open and active, return existing page without moving window
        if profile_id in self.contexts:
            try:
                ctx = self.contexts[profile_id]
                page = self.pages.get(profile_id)
                if page and not page.is_closed():
                    if focus_url and target_url:
                        current_url = page.url
                        if current_url in ("about:blank", "", "chrome://newtab/") or (
                            "finances" in target_url and target_url not in current_url
                        ):
                            self.log(f"Navigating [{instance['name']}] to {target_url}...", "INFO")
                            page.goto(target_url, timeout=45000, wait_until="domcontentloaded")
                    return page
                else:
                    pages = ctx.pages
                    if pages and not pages[0].is_closed():
                        self.pages[profile_id] = pages[0]
                        if focus_url and target_url:
                            current_url = pages[0].url
                            if current_url in ("about:blank", "", "chrome://newtab/") or (
                                "finances" in target_url and target_url not in current_url
                            ):
                                pages[0].goto(target_url, timeout=45000, wait_until="domcontentloaded")
                        return pages[0]
                    else:
                        page = ctx.new_page()
                        self.pages[profile_id] = page
                        if focus_url and target_url:
                            page.goto(target_url, timeout=45000, wait_until="domcontentloaded")
                        return page
            except Exception:
                self.contexts.pop(profile_id, None)
                self.pages.pop(profile_id, None)
                self.hwnds.pop(profile_id, None)

        profile_dir = self.get_profile_dir(profile_id)
        is_headless = self.config.get("general", {}).get("headless", False)

        # Clean any stale lock files before launch
        for lock_name in ["SingletonLock", "SingletonCookie", "SingletonSocket"]:
            lock_file = os.path.join(profile_dir, lock_name)
            if os.path.exists(lock_file):
                try:
                    os.remove(lock_file)
                except Exception:
                    pass

        args = [
            f"--window-position={quad.get('x', 0)},{quad.get('y', 0)}",
            f"--window-size={quad.get('width', 426)},{quad.get('height', 340)}",
            "--disable-blink-features=AutomationControlled",
            "--no-default-browser-check",
            "--no-first-run"
        ]

        launch_kwargs = {
            "user_data_dir": profile_dir,
            "headless": is_headless,
            "args": args,
            "viewport": None,
            "no_viewport": True,
            "ignore_default_args": ["--enable-automation"]
        }

        self.log(f"Launching [{instance['name']}] at fixed position ({quad.get('x')}, {quad.get('y')}) [Size: {quad.get('width')}x{quad.get('height')}]...", "INFO")
        try:
            context = self.playwright.chromium.launch_persistent_context(**launch_kwargs)
            self.contexts[profile_id] = context
            
            pages = context.pages
            page = pages[0] if pages else context.new_page()
            self.pages[profile_id] = page

            # Lock window frame to screen coordinates
            self.snap_window(profile_id, quad, page)

            if target_url:
                current_url = page.url
                if current_url in ("about:blank", "", "chrome://newtab/") or "finances" in target_url:
                    self.log(f"Navigating [{instance['name']}] to {target_url}...", "INFO")
                    page.goto(target_url, timeout=45000, wait_until="domcontentloaded")

            return page
        except Exception as e:
            self.log(f"Failed to launch browser for [{instance['name']}]: {e}", "ERROR")
            return None

    def launch_all_browsers(self):
        """Launches and tiles all 8 persistent browser windows (4 Grab + 4 Foodpanda across 4 Branches)."""
        self.log("Launching all 8 tiled browser windows (4 Grab + 4 Foodpanda) onto the screen...", "INFO")
        instances = self.config.get("browser_instances", [])
        if not instances:
            profiles = ["grab_1", "grab_2", "grab_3", "grab_4", "panda_1", "panda_2", "panda_3", "panda_4"]
        else:
            profiles = [b["profile_id"] for b in instances]

        for pid in profiles:
            try:
                self.launch_profile_browser(pid, focus_url=True)
                time.sleep(0.35)
            except Exception as e:
                self.log(f"Error launching browser profile {pid}: {e}", "ERROR")
        
        # Snap all to confirm locked positions
        self.snap_all_windows()
        self.log("All 8 browser windows are active and locked in screen grid (4 Top Grab, 4 Bottom Panda).", "SUCCESS")

    def train_single_picker(self, store_id: str, is_eod: bool = False, on_selector_found: Optional[Callable[[str, str], None]] = None) -> bool:
        """Visual single element selector training for single store (Live Operations or EOD finances)."""
        store = next((s for s in self.config.get("stores", []) if s["id"] == store_id), None)
        profile_id = store.get("profile_id", store_id) if store else store_id
        store_name = store["name"] if store else store_id

        page = self.launch_profile_browser(profile_id, focus_url=False)
        if not page or page.is_closed():
            self.log(f"Cannot train selector: Browser for [{profile_id}] is not open.", "ERROR")
            return False

        # If training in EOD mode, navigate the browser to the resolved EOD Finances URL first
        if is_eod and store:
            raw_url = store.get("eod_url") or store.get("url", "")
            target_url = self.resolve_url(raw_url, is_eod=True)
            if target_url:
                self.log(f"Navigating [{store_name}] to EOD finances page: {target_url}...", "INFO")
                try:
                    page.goto(target_url, timeout=45000, wait_until="domcontentloaded")
                    time.sleep(2.0)
                except Exception as e:
                    self.log(f"Navigation warning: {e}", "WARNING")

        mode_name = "EOD (Yesterday's Sales)" if is_eod else "Live Operation"
        self.log(f"Training Mode [{mode_name}] activated for [{store_name}]. Click the sales number on the webpage.", "WARNING")

        js_picker = """
        () => {
            if (window.__singlePickerActive) return;
            window.__singlePickerActive = true;
            
            const banner = document.createElement('div');
            banner.id = '__scraper_training_banner';
            banner.innerHTML = `
                <div style="position:fixed;top:10px;left:50%;transform:translateX(-50%);z-index:999999;
                            background:linear-gradient(135deg, #1e293b, #0f172a);color:#38bdf8;padding:12px 24px;
                            border-radius:12px;box-shadow:0 10px 25px rgba(0,0,0,0.5);border:2px solid #38bdf8;
                            font-family:sans-serif;font-size:14px;font-weight:bold;display:flex;align-items:center;gap:10px;">
                    <span>TRAINING MODE: Click directly on the SALES AMOUNT on this page.</span>
                    <button id="__scraper_cancel_btn" style="background:#ef4444;color:white;border:none;padding:4px 10px;border-radius:6px;cursor:pointer;font-size:12px;">Cancel</button>
                </div>
            `;
            document.body.appendChild(banner);

            let lastTarget = null;
            const originalOutline = new Map();

            function getCssPath(el) {
                if (!(el instanceof Element)) return;
                var path = [];
                while (el.nodeType === Node.ELEMENT_NODE) {
                    var selector = el.nodeName.toLowerCase();
                    if (el.id) {
                        selector += '#' + el.id;
                        path.unshift(selector);
                        break;
                    } else {
                        var sib = el, nth = 1;
                        while (sib = sib.previousElementSibling) {
                            if (sib.nodeName.toLowerCase() == selector)
                                nth++;
                        }
                        if (nth != 1)
                            selector += ":nth-of-type("+nth+")";
                    }
                    path.unshift(selector);
                    el = el.parentNode;
                }
                return path.join(" > ");
            }

            function onMouseMove(e) {
                if (e.target.closest('#__scraper_training_banner')) return;
                if (lastTarget && lastTarget !== e.target) {
                    lastTarget.style.outline = originalOutline.get(lastTarget) || '';
                }
                lastTarget = e.target;
                if (!originalOutline.has(lastTarget)) {
                    originalOutline.set(lastTarget, lastTarget.style.outline);
                }
                lastTarget.style.outline = '3px solid #10b981';
                lastTarget.style.cursor = 'crosshair';
            }

            function onClick(e) {
                if (e.target.id === '__scraper_cancel_btn') {
                    cleanup();
                    window.__selectedSelectorResult = { cancelled: true };
                    return;
                }
                if (e.target.closest('#__scraper_training_banner')) return;

                e.preventDefault();
                e.stopPropagation();

                const selector = getCssPath(e.target);
                const text = e.target.innerText || e.target.textContent || '';
                
                cleanup();

                const toast = document.createElement('div');
                toast.innerHTML = `<div style="position:fixed;top:20px;left:50%;transform:translateX(-50%);z-index:999999;
                                    background:#10b981;color:white;padding:12px 24px;border-radius:10px;
                                    font-family:sans-serif;font-size:15px;font-weight:bold;box-shadow:0 8px 20px rgba(0,0,0,0.3);">
                                    Sales Element Captured: "${text.trim()}"
                                   </div>`;
                document.body.appendChild(toast);
                setTimeout(() => toast.remove(), 3500);

                window.__selectedSelectorResult = {
                    selector: selector,
                    text: text.trim()
                };
            }

            function cleanup() {
                window.__singlePickerActive = false;
                document.removeEventListener('mousemove', onMouseMove, true);
                document.removeEventListener('click', onClick, true);
                if (lastTarget) lastTarget.style.outline = originalOutline.get(lastTarget) || '';
                const b = document.getElementById('__scraper_training_banner');
                if (b) b.remove();
            }

            window.__selectedSelectorResult = null;
            document.addEventListener('mousemove', onMouseMove, true);
            document.addEventListener('click', onClick, true);
        }
        """

        try:
            page.evaluate(js_picker)
            for _ in range(60):
                time.sleep(1)
                res = page.evaluate("() => window.__selectedSelectorResult")
                if res:
                    if res.get("cancelled"):
                        self.log(f"Selector training cancelled for [{store_name}].", "WARNING")
                        return False
                    
                    found_selector = res.get("selector", "")
                    sample_text = res.get("text", "")
                    self.log(f"Successfully trained [{store_name}] ({mode_name})! Selector: {found_selector} (Text: '{sample_text}')", "SUCCESS")
                    
                    if store:
                        if is_eod:
                            store["eod_selector"] = found_selector
                        else:
                            store["selector"] = found_selector
                    self.save_config()
                    if on_selector_found:
                        on_selector_found(found_selector, sample_text)
                    return True
            self.log("Training timed out (no element clicked within 60s).", "WARNING")
            return False
        except Exception as e:
            self.log(f"Training error on [{store_name}]: {e}", "ERROR")
            return False

    def train_eod_wizard(self, store_id: str, on_complete: Optional[Callable[[str, str], None]] = None) -> bool:
        """
        Interactive 3-Step EOD Training Wizard:
        - For Single Grab Stores (Angeles grab_1 & Quezon City grab_2):
          Step 1: Locates the Date Filter / Dropdown button (or allows skipping if already open/visible).
          Step 2: Locates and CLICKS the 'Yesterday' filter option (dispatches live click to update page to yesterday).
          Step 3: Locates and captures the Net Sales / Total Amount element selector on that updated page.
        - For Caloocan Grab (grab_3_caloocan):
          Step 1: Locates the Date Filter / Dropdown button on the default operation page.
          Step 2: Locates and CLICKS the 'Yesterday' filter option (dispatches live click to load yesterday's 30+ stores).
          Step 3: Navigates and captures the 30 Caloocan stores + Top Total Net Sales, and computes San Fernando Net Sales (Overall - Caloocan).
        """
        store = next((s for s in self.config.get("stores", []) if s["id"] == store_id), None)
        profile_id = store.get("profile_id", store_id) if store else store_id
        store_name = store["name"] if store else store_id
        is_grab = (store.get("platform") == "grab") if store else ("grab" in store_id.lower())
        is_panda = (store.get("platform") == "foodpanda") if store else ("panda" in store_id.lower())
        is_caloocan_grab = is_grab and ("caloocan" in store_id.lower() or "grab_3" in store_id.lower() or "caloocan" in (store["name"].lower() if store else ""))
        is_multi = is_caloocan_grab and (bool(store.get("multi_selectors")) or bool(store.get("expected_count")))

        page = self.launch_profile_browser(profile_id, focus_url=False)
        if not page or page.is_closed():
            self.log(f"Cannot train EOD: Browser for [{profile_id}] is not open.", "ERROR")
            return False

        # If Foodpanda or Caloocan Grab, open default operation link with current date as requested; otherwise open EOD link
        if is_panda or is_caloocan_grab:
            raw_url = (store.get("url") if store else None) or ""
            target_url = self.resolve_url(raw_url, is_eod=False)
        else:
            raw_url = (store.get("eod_url") if store else None) or "https://merchant.grab.com/finances?page=tx&startDate={YESTERDAY_DATE}&endDate={YESTERDAY_DATE}"
            target_url = self.resolve_url(raw_url, is_eod=True)

        if target_url:
            self.log(f"Navigating [{store_name}] for EOD Training to: {target_url}...", "INFO")
            try:
                page.goto(target_url, timeout=45000, wait_until="domcontentloaded")
                time.sleep(2.0)
            except Exception as e:
                self.log(f"Navigation note: {e}", "WARNING")

        self.log(f"3-Step EOD Training Wizard activated for [{store_name}]. Follow the on-screen steps in the browser window.", "WARNING")

        is_multi_js = "true" if is_multi else "false"

        js_wizard = f"""
        () => {{
            if (window.__eodWizardActive) return;
            window.__eodWizardActive = true;

            const isMultiStore = {is_multi_js};
            let currentStep = 1;
            let dropdownSelector = "";
            let yesterdaySelector = "";
            let salesSelector = "";
            let sampleSalesText = "";
            let selectedMultiItems = [];
            let topOverallSalesVal = 0.0;

            let hoveredEl = null;
            const originalOutlines = new Map();

            // Simulate real mouse and pointer events for React, Vue, Angular SPAs (Foodpanda & Grab)
            function simulateRealClick(el) {{
                if (!el) return;
                const target = el.closest('button, [role="button"], [role="option"], [role="menuitem"], [role="tab"], [role="radio"], li, a, label, div[tabindex], div.ant-select-item, div.dropdown-item, input, select') || el;
                const opts = {{ bubbles: true, cancelable: true, view: window, composed: true }};
                try {{ target.dispatchEvent(new PointerEvent('pointerover', opts)); }} catch(e){{}}
                try {{ target.dispatchEvent(new MouseEvent('mouseover', opts)); }} catch(e){{}}
                try {{ target.dispatchEvent(new PointerEvent('pointerdown', opts)); }} catch(e){{}}
                try {{ target.dispatchEvent(new MouseEvent('mousedown', opts)); }} catch(e){{}}
                try {{ target.focus(); }} catch(e){{}}
                try {{ target.dispatchEvent(new PointerEvent('pointerup', opts)); }} catch(e){{}}
                try {{ target.dispatchEvent(new MouseEvent('mouseup', opts)); }} catch(e){{}}
                try {{ target.click(); }} catch(e){{}}
                try {{ target.dispatchEvent(new Event('change', {{ bubbles: true }})); }} catch(e){{}}
            }}

            // Auto-click any 'Apply' / 'Done' / 'OK' button in date pickers (Foodpanda & Grab popovers)
            function autoClickApplyIfPresent() {{
                const buttons = Array.from(document.querySelectorAll('button, [role="button"], .ant-btn-primary, .ant-picker-ok button'));
                for (const b of buttons) {{
                    if (b.closest('#__scraper_eod_wizard')) continue;
                    const t = (b.innerText || b.textContent || '').trim().toLowerCase();
                    if (['apply', 'apply filter', 'done', 'confirm', 'update', 'submit', 'ok'].includes(t)) {{
                        simulateRealClick(b);
                        break;
                    }}
                }}
            }}

            // Create floating wizard container
            const container = document.createElement('div');
            container.id = '__scraper_eod_wizard';
            container.style.cssText = 'position:fixed;top:10px;left:50%;transform:translateX(-50%);z-index:99999999;font-family:sans-serif;box-sizing:border-box;pointer-events:auto;';

            function parseAmount(txt) {{
                if (!txt) return 0.0;
                const cleaned = txt.replace(/[₱$PHP,]/gi, '').trim();
                const match = cleaned.match(/[-+]?\\d*\\.?\\d+/);
                return match ? parseFloat(match[0]) : 0.0;
            }}

            function detectTopOverallSales() {{
                const allText = document.body.innerText || '';
                const lines = allText.split('\\n').map(l => l.trim()).filter(l => l.length > 0);
                for (let i = 0; i < Math.min(60, lines.length); i++) {{
                    const lineLower = lines[i].toLowerCase();
                    if (lineLower === 'net sales' || lineLower === 'total net sales' || lineLower.includes('overall net sales')) {{
                        for (let k = i + 1; k < Math.min(i + 4, lines.length); k++) {{
                            const amt = parseAmount(lines[k]);
                            if (amt > 0) {{
                                return amt;
                            }}
                        }}
                    }}
                }}
                return 0.0;
            }}

            function updateMultiUI() {{
                const calTotal = selectedMultiItems.reduce((acc, item) => acc + item.amount, 0);
                if (topOverallSalesVal === 0.0) {{
                    topOverallSalesVal = detectTopOverallSales();
                }}
                const sfBalance = Math.max(0, topOverallSalesVal - calTotal);
                const statsEl = document.getElementById('__eod_multi_stats');
                const doneBtn = document.getElementById('__eod_done_multi_btn');

                if (statsEl) {{
                    statsEl.innerHTML = `
                        Clicked: <b style="color:#38bdf8;">${{selectedMultiItems.length}} / 30 stores</b> |
                        Caloocan: <b style="color:#10b981;">₱ ${{calTotal.toLocaleString(undefined, {{minimumFractionDigits: 2, maximumFractionDigits: 2}})}}</b> |
                        Top Overall: <b style="color:#f59e0b;">₱ ${{topOverallSalesVal.toLocaleString(undefined, {{minimumFractionDigits: 2, maximumFractionDigits: 2}})}}</b> |
                        San Fernando Balance: <b style="color:#a855f7;">₱ ${{sfBalance.toLocaleString(undefined, {{minimumFractionDigits: 2, maximumFractionDigits: 2}})}}</b>
                    `;
                }}
                if (doneBtn) {{
                    doneBtn.innerText = `Done (Save ${{selectedMultiItems.length}} Stores)`;
                }}
            }}

            function autoDetect30Stores() {{
                clearAllMultiSelections();
                topOverallSalesVal = detectTopOverallSales();

                // Find store rows or elements containing sales figures
                const panel = document.querySelector('div#rc-tabs-0-panel-overview, [role="tabpanel"], main, body');
                if (!panel) return;

                const strongElements = Array.from(panel.querySelectorAll('span > strong, h4, h5, div > strong'));
                const candidates = [];

                strongElements.forEach(el => {{
                    const t = (el.innerText || el.textContent || '').trim();
                    if (/[₱$PHP]/.test(t) || /\\d+\\.\\d{{2}}/.test(t)) {{
                        const amt = parseAmount(t);
                        if (amt >= 0 && !el.closest('#__scraper_eod_wizard')) {{
                            candidates.push({{ el: el, text: t, amount: amt }});
                        }}
                    }}
                }});

                // Filter or take first 30 store sales elements
                const targetList = candidates.slice(0, 30);
                targetList.forEach((c, idx) => {{
                    const el = c.el;
                    const path = getCssPath(el);
                    el.setAttribute('data-eod-selected', 'true');
                    el.style.outline = '2px solid #10b981';
                    el.style.position = 'relative';

                    const badge = document.createElement('span');
                    badge.className = '__scraper_eod_badge';
                    badge.innerText = `#${{idx + 1}}`;
                    badge.style.position = 'absolute';
                    badge.style.top = '-10px';
                    badge.style.left = '-10px';
                    badge.style.background = '#10b981';
                    badge.style.color = 'white';
                    badge.style.fontSize = '10px';
                    badge.style.fontWeight = 'bold';
                    badge.style.padding = '2px 5px';
                    badge.style.borderRadius = '6px';
                    badge.style.zIndex = '99999';
                    badge.style.pointerEvents = 'none';
                    el.appendChild(badge);

                    selectedMultiItems.push({{
                        el: el,
                        selector: path,
                        text: c.text,
                        amount: c.amount
                    }});
                }});

                updateMultiUI();
            }}

            function clearAllMultiSelections() {{
                selectedMultiItems.forEach(item => {{
                    const badge = item.el.querySelector('.__scraper_eod_badge');
                    if (badge) badge.remove();
                    item.el.removeAttribute('data-eod-selected');
                    item.el.style.outline = '';
                }});
                selectedMultiItems.length = 0;
            }}

            function renderWizard() {{
                if (currentStep === 1) {{
                    container.innerHTML = `
                        <div style="background:linear-gradient(135deg, #0f172a, #1e293b);color:#f8fafc;padding:14px 22px;border-radius:14px;box-shadow:0 12px 35px rgba(0,0,0,0.65);border:2px solid #38bdf8;display:flex;align-items:center;gap:14px;max-width:880px;">
                            <div style="display:flex;align-items:center;justify-content:center;background:#0284c7;color:white;width:32px;height:32px;border-radius:50%;font-weight:bold;font-size:15px;flex-shrink:0;">1</div>
                            <div style="display:flex;flex-direction:column;">
                                <span style="color:#38bdf8;font-size:14px;font-weight:bold;letter-spacing:0.5px;">EOD STEP 1/3: LOCATE DATE FILTER / DROPDOWN</span>
                                <span style="color:#cbd5e1;font-size:12px;margin-top:2px;">Click the <b>Date Filter button / Dropdown</b> on portal. If 'Yesterday' is <i>already visible</i> on screen, click 'Skip Step 1'.</span>
                            </div>
                            <button id="__eod_skip_step1_btn" style="background:#475569;color:white;border:none;padding:7px 12px;border-radius:8px;cursor:pointer;font-size:12px;font-weight:bold;white-space:nowrap;">Skip Step 1</button>
                            <button id="__eod_cancel_btn" style="background:#ef4444;color:white;border:none;padding:7px 12px;border-radius:8px;cursor:pointer;font-size:12px;font-weight:bold;white-space:nowrap;">Cancel</button>
                        </div>
                    `;
                }} else if (currentStep === 2) {{
                    container.innerHTML = `
                        <div style="background:linear-gradient(135deg, #0f172a, #1e293b);color:#f8fafc;padding:14px 22px;border-radius:14px;box-shadow:0 12px 35px rgba(0,0,0,0.65);border:2px solid #f59e0b;display:flex;align-items:center;gap:14px;max-width:920px;">
                            <div style="display:flex;align-items:center;justify-content:center;background:#d97706;color:white;width:32px;height:32px;border-radius:50%;font-weight:bold;font-size:15px;flex-shrink:0;">2</div>
                            <div style="display:flex;flex-direction:column;">
                                <span style="color:#fbbf24;font-size:14px;font-weight:bold;letter-spacing:0.5px;">EOD STEP 2/3: CLICK 'YESTERDAY' OPTION</span>
                                <span style="color:#cbd5e1;font-size:12px;margin-top:2px;">Click directly on the <b>'Yesterday'</b> option, or click <b>Auto-Find 'Yesterday'</b> below.</span>
                            </div>
                            <button id="__eod_autofind_btn" style="background:#0284c7;color:white;border:none;padding:7px 12px;border-radius:8px;cursor:pointer;font-size:12px;font-weight:bold;white-space:nowrap;">Auto-Find 'Yesterday'</button>
                            <button id="__eod_cancel_btn" style="background:#ef4444;color:white;border:none;padding:7px 12px;border-radius:8px;cursor:pointer;font-size:12px;font-weight:bold;white-space:nowrap;">Cancel</button>
                        </div>
                    `;
                }} else if (currentStep === 2.5) {{
                    container.innerHTML = `
                        <div style="background:linear-gradient(135deg, #0f172a, #1e293b);color:#f8fafc;padding:14px 22px;border-radius:14px;box-shadow:0 12px 35px rgba(0,0,0,0.65);border:2px solid #10b981;display:flex;align-items:center;gap:14px;max-width:880px;">
                            <div style="display:flex;align-items:center;justify-content:center;background:#10b981;color:white;width:32px;height:32px;border-radius:50%;font-weight:bold;font-size:14px;flex-shrink:0;">OK</div>
                            <div style="display:flex;flex-direction:column;">
                                <span style="color:#34d399;font-size:14px;font-weight:bold;">'Yesterday' Selected! Loading yesterday's data...</span>
                                <span style="color:#cbd5e1;font-size:12px;margin-top:2px;">Please wait while the portal updates yesterday's sales figures...</span>
                            </div>
                        </div>
                    `;
                }} else if (currentStep === 3) {{
                    if (isMultiStore) {{
                        container.innerHTML = `
                            <div style="background:linear-gradient(135deg, #0f172a, #1e293b);color:#f8fafc;padding:14px 22px;border-radius:14px;box-shadow:0 12px 35px rgba(0,0,0,0.65);border:2px solid #38bdf8;display:flex;flex-direction:column;gap:10px;max-width:960px;">
                                <div style="display:flex;align-items:center;justify-content:space-between;gap:14px;">
                                    <div style="display:flex;align-items:center;gap:10px;">
                                        <div style="display:flex;align-items:center;justify-content:center;background:#059669;color:white;width:30px;height:30px;border-radius:50%;font-weight:bold;font-size:14px;flex-shrink:0;">3</div>
                                        <div>
                                            <div style="color:#34d399;font-size:14px;font-weight:bold;letter-spacing:0.5px;">CALOOCAN EOD STEP 3/3: 30 STORES & SAN FERNANDO DEDUCTION</div>
                                            <div id="__eod_multi_stats" style="color:#cbd5e1;font-size:12px;margin-top:2px;">Clicked: 0 / 30 stores | Caloocan: ₱ 0.00 | Overall: ₱ 0.00 | San Fernando Balance: ₱ 0.00</div>
                                        </div>
                                    </div>
                                    <div style="display:flex;align-items:center;gap:8px;">
                                        <button id="__eod_autodetect_btn" style="background:#0284c7;color:white;border:none;padding:7px 12px;border-radius:8px;cursor:pointer;font-weight:bold;font-size:12px;white-space:nowrap;">Auto-Detect 30</button>
                                        <button id="__eod_done_multi_btn" style="background:#10b981;color:white;border:none;padding:7px 14px;border-radius:8px;cursor:pointer;font-weight:bold;font-size:12px;white-space:nowrap;">Done (Save 0)</button>
                                        <button id="__eod_clear_btn" style="background:#475569;color:white;border:none;padding:7px 10px;border-radius:8px;cursor:pointer;font-size:12px;">Clear</button>
                                        <button id="__eod_cancel_btn" style="background:#ef4444;color:white;border:none;padding:7px 10px;border-radius:8px;cursor:pointer;font-size:12px;">Cancel</button>
                                    </div>
                                </div>
                            </div>
                        `;
                        setTimeout(() => {{
                            updateMultiUI();
                            const autoBtn = document.getElementById('__eod_autodetect_btn');
                            if (autoBtn) autoBtn.onclick = autoDetect30Stores;
                            const doneMultiBtn = document.getElementById('__eod_done_multi_btn');
                            if (doneMultiBtn) doneMultiBtn.onclick = () => {{
                                const calTotal = selectedMultiItems.reduce((acc, item) => acc + item.amount, 0);
                                if (topOverallSalesVal === 0.0) topOverallSalesVal = detectTopOverallSales();
                                const sfBalance = Math.max(0, topOverallSalesVal - calTotal);
                                const sels = selectedMultiItems.map(i => i.selector);

                                cleanup();

                                const toast = document.createElement('div');
                                toast.innerHTML = `
                                    <div style="position:fixed;top:20px;left:50%;transform:translateX(-50%);z-index:99999999;
                                                background:#059669;color:white;padding:16px 28px;border-radius:12px;
                                                font-family:sans-serif;font-size:14px;font-weight:bold;box-shadow:0 10px 30px rgba(0,0,0,0.4);border:2px solid #34d399;">
                                        [Success] Caloocan EOD Trained! (${{sels.length}} Stores: ₱${{calTotal.toLocaleString()}} | San Fernando Balance: ₱${{sfBalance.toLocaleString()}})
                                    </div>`;
                                document.body.appendChild(toast);
                                setTimeout(() => toast.remove(), 4000);

                                window.__eodWizardResult = {{
                                    cancelled: false,
                                    is_multi: true,
                                    dropdown_selector: dropdownSelector,
                                    yesterday_selector: yesterdaySelector,
                                    multi_selectors: sels,
                                    count: sels.length,
                                    caloocan_sales: calTotal,
                                    overall_sales: topOverallSalesVal,
                                    san_fernando_sales: sfBalance,
                                    text: `₱${{calTotal.toFixed(2)}} (${{sels.length}} stores)`
                                }};
                            }};
                            const clearBtn = document.getElementById('__eod_clear_btn');
                            if (clearBtn) clearBtn.onclick = () => {{
                                clearAllMultiSelections();
                                updateMultiUI();
                            }};
                        }}, 50);
                    }} else {{
                        container.innerHTML = `
                            <div style="background:linear-gradient(135deg, #0f172a, #1e293b);color:#f8fafc;padding:14px 22px;border-radius:14px;box-shadow:0 12px 35px rgba(0,0,0,0.65);border:2px solid #10b981;display:flex;align-items:center;gap:14px;max-width:880px;">
                                <div style="display:flex;align-items:center;justify-content:center;background:#059669;color:white;width:32px;height:32px;border-radius:50%;font-weight:bold;font-size:15px;flex-shrink:0;">3</div>
                                <div style="display:flex;flex-direction:column;">
                                    <span style="color:#34d399;font-size:14px;font-weight:bold;letter-spacing:0.5px;">EOD STEP 3/3: SELECT TOTAL SALES AMOUNT</span>
                                    <span style="color:#cbd5e1;font-size:12px;margin-top:2px;">Click directly on the <b>Net Sales / Total Sales Amount</b> on the updated page to finish training.</span>
                                </div>
                                <button id="__eod_cancel_btn" style="background:#ef4444;color:white;border:none;padding:7px 12px;border-radius:8px;cursor:pointer;font-size:12px;font-weight:bold;white-space:nowrap;">Cancel</button>
                            </div>
                        `;
                    }}
                }}
            }}

            function getCssPath(el) {{
                if (!(el instanceof Element)) return '';
                var path = [];
                while (el.nodeType === Node.ELEMENT_NODE) {{
                    var selector = el.nodeName.toLowerCase();
                    if (el.id && !el.id.startsWith('__')) {{
                        selector += '#' + el.id;
                        path.unshift(selector);
                        break;
                    }} else {{
                        var sib = el, nth = 1;
                        while (sib = sib.previousElementSibling) {{
                            if (sib.nodeName.toLowerCase() == selector)
                                nth++;
                        }}
                        if (nth != 1)
                            selector += ":nth-of-type("+nth+")";
                    }}
                    path.unshift(selector);
                    el = el.parentNode;
                }}
                return path.join(" > ");
            }}

            function onMouseMove(e) {{
                if (e.target.closest('#__scraper_eod_wizard')) return;
                if (currentStep === 2.5) return;

                if (hoveredEl && hoveredEl !== e.target) {{
                    if (!hoveredEl.getAttribute('data-eod-selected')) {{
                        hoveredEl.style.outline = originalOutlines.get(hoveredEl) || '';
                    }}
                }}
                hoveredEl = e.target;
                if (!originalOutlines.has(hoveredEl)) {{
                    originalOutlines.set(hoveredEl, hoveredEl.style.outline);
                }}

                if (!hoveredEl.getAttribute('data-eod-selected')) {{
                    if (currentStep === 1) {{
                        hoveredEl.style.outline = '3px solid #38bdf8';
                    }} else if (currentStep === 2) {{
                        hoveredEl.style.outline = '3px solid #fbbf24';
                    }} else if (currentStep === 3) {{
                        hoveredEl.style.outline = isMultiStore ? '2px dashed #38bdf8' : '3px solid #10b981';
                    }}
                    hoveredEl.style.cursor = 'pointer';
                }}
            }}

            function onClick(e) {{
                if (e.target.id === '__eod_cancel_btn') {{
                    cleanup();
                    window.__eodWizardResult = {{ cancelled: true }};
                    return;
                }}

                if (e.target.id === '__eod_skip_step1_btn') {{
                    dropdownSelector = "";
                    currentStep = 2;
                    renderWizard();
                    return;
                }}

                if (e.target.id === '__eod_autofind_btn') {{
                    const allElements = Array.from(document.querySelectorAll('button, [role="button"], [role="option"], [role="tab"], [role="menuitem"], li, span, div, a, label'));
                    const yestEl = allElements.find(el => {{
                        if (el.closest('#__scraper_eod_wizard')) return false;
                        const t = (el.innerText || el.textContent || '').trim().toLowerCase();
                        return t === 'yesterday' || t === 'kahapon';
                    }});
                    if (yestEl) {{
                        yesterdaySelector = getCssPath(yestEl);
                        simulateRealClick(yestEl);
                        setTimeout(autoClickApplyIfPresent, 350);
                        currentStep = 2.5;
                        renderWizard();
                        setTimeout(() => {{
                            currentStep = 3;
                            renderWizard();
                            if (isMultiStore) updateMultiUI();
                        }}, 3000);
                    }} else {{
                        alert("Could not find a 'Yesterday' button automatically. Please open the Date Filter dropdown first, or click directly on the Yesterday button.");
                    }}
                    return;
                }}

                if (e.target.closest('#__scraper_eod_wizard')) return;
                if (currentStep === 2.5) return;

                const target = e.target;
                const selector = getCssPath(target);
                const text = (target.innerText || target.textContent || '').trim();

                if (currentStep === 1) {{
                    dropdownSelector = selector;
                    simulateRealClick(target);
                    currentStep = 2;
                    renderWizard();
                }} else if (currentStep === 2) {{
                    let finalYesterdayTarget = target;
                    let finalSelector = selector;

                    // If clicked element does not contain 'yesterday', try to find exact 'Yesterday' element on page
                    const clickedText = text.toLowerCase();
                    const isYesterdayText = clickedText.includes('yesterday') || clickedText.includes('kahapon');
                    
                    if (!isYesterdayText) {{
                        const allElements = Array.from(document.querySelectorAll('button, [role="button"], [role="option"], [role="tab"], [role="menuitem"], li, span, div, a, label'));
                        const exactYest = allElements.find(el => {{
                            if (el.closest('#__scraper_eod_wizard')) return false;
                            const t = (el.innerText || el.textContent || '').trim().toLowerCase();
                            return t === 'yesterday' || t === 'kahapon';
                        }});
                        if (exactYest) {{
                            finalYesterdayTarget = exactYest;
                            finalSelector = getCssPath(exactYest);
                        }} else if (clickedText.includes('7 day') || clickedText.includes('today') || clickedText.includes('30 day') || clickedText.includes('week') || clickedText.includes('month')) {{
                            alert("Warning: You clicked '" + text + "'. This is not 'Yesterday'. If 'Yesterday' is inside a Date Dropdown or calendar menu, please click the dropdown button first to open it, or click 'Auto-Find Yesterday'.");
                            return;
                        }}
                    }}

                    yesterdaySelector = finalSelector;
                    simulateRealClick(finalYesterdayTarget);

                    // Check if popover has an Apply or Done button and trigger it
                    setTimeout(() => {{
                        autoClickApplyIfPresent();
                    }}, 350);

                    currentStep = 2.5;
                    renderWizard();

                    // Wait 3.0 seconds for network and DOM to refresh yesterday's data
                    setTimeout(() => {{
                        currentStep = 3;
                        renderWizard();
                        if (isMultiStore) {{
                            updateMultiUI();
                        }}
                    }}, 3000);

                }} else if (currentStep === 3) {{
                    if (isMultiStore) {{
                        e.preventDefault();
                        e.stopPropagation();
                        
                        const alreadySelected = selectedMultiItems.some(i => i.el === target || i.selector === selector);
                        if (!alreadySelected) {{
                            const amt = parseAmount(text);
                            target.setAttribute('data-eod-selected', 'true');
                            target.style.outline = '2px solid #10b981';
                            target.style.position = 'relative';

                            const badge = document.createElement('span');
                            badge.className = '__scraper_eod_badge';
                            badge.innerText = `#${{selectedMultiItems.length + 1}}`;
                            badge.style.position = 'absolute';
                            badge.style.top = '-10px';
                            badge.style.left = '-10px';
                            badge.style.background = '#10b981';
                            badge.style.color = 'white';
                            badge.style.fontSize = '10px';
                            badge.style.fontWeight = 'bold';
                            badge.style.padding = '2px 5px';
                            badge.style.borderRadius = '6px';
                            badge.style.zIndex = '99999';
                            badge.style.pointerEvents = 'none';
                            target.appendChild(badge);

                            selectedMultiItems.push({{
                                el: target,
                                selector: selector,
                                text: text,
                                amount: amt
                            }});
                            updateMultiUI();
                        }}
                    }} else {{
                        e.preventDefault();
                        e.stopPropagation();
                        salesSelector = selector;
                        sampleSalesText = text;

                        cleanup();

                        const toast = document.createElement('div');
                        toast.innerHTML = `
                            <div style="position:fixed;top:20px;left:50%;transform:translateX(-50%);z-index:99999999;
                                        background:#059669;color:white;padding:16px 28px;border-radius:12px;
                                        font-family:sans-serif;font-size:15px;font-weight:bold;box-shadow:0 10px 30px rgba(0,0,0,0.4);border:2px solid #34d399;">
                                [Success] EOD Training Complete! Captured: "${{sampleSalesText}}"
                            </div>`;
                        document.body.appendChild(toast);
                        setTimeout(() => toast.remove(), 4000);

                        window.__eodWizardResult = {{
                            cancelled: false,
                            is_multi: false,
                            dropdown_selector: dropdownSelector,
                            yesterday_selector: yesterdaySelector,
                            sales_selector: salesSelector,
                            text: sampleSalesText
                        }};
                    }}
                }}
            }}

            function cleanup() {{
                window.__eodWizardActive = false;
                document.removeEventListener('mousemove', onMouseMove, true);
                document.removeEventListener('click', onClick, true);
                if (hoveredEl) hoveredEl.style.outline = originalOutlines.get(hoveredEl) || '';
                clearAllMultiSelections();
                const el = document.getElementById('__scraper_eod_wizard');
                if (el) el.remove();
            }}

            window.__eodWizardResult = null;
            document.body.appendChild(container);
            renderWizard();
            document.addEventListener('mousemove', onMouseMove, true);
            document.addEventListener('click', onClick, true);
        }}
        """

        try:
            page.evaluate(js_wizard)
            for _ in range(300):
                time.sleep(1)
                res = page.evaluate("() => window.__eodWizardResult")
                if res:
                    if res.get("cancelled"):
                        self.log(f"3-Step EOD training cancelled for [{store_name}].", "WARNING")
                        return False

                    dropdown_sel = res.get("dropdown_selector", "")
                    yesterday_sel = res.get("yesterday_selector", "")
                    is_res_multi = res.get("is_multi", False)

                    if is_res_multi:
                        multi_selectors = res.get("multi_selectors", [])
                        count = res.get("count", len(multi_selectors))
                        caloocan_sales = res.get("caloocan_sales", 0.0)
                        overall_sales = res.get("overall_sales", 0.0)
                        san_fernando_sales = res.get("san_fernando_sales", 0.0)
                        sample_text = res.get("text", f"₱{caloocan_sales:,.2f} ({count} stores)")

                        self.log(
                            f"Successfully completed 3-Step EOD Training for [{store_name}]!\n"
                            f"• Dropdown Selector: {dropdown_sel or '(Skipped)'}\n"
                            f"• Yesterday Button Selector: {yesterday_sel}\n"
                            f"• Trained Stores: {count} Caloocan stores (Total: ₱{caloocan_sales:,.2f})\n"
                            f"• Top Overall Sales: ₱{overall_sales:,.2f}\n"
                            f"• San Fernando Shared Balance: ₱{san_fernando_sales:,.2f} (Overall ₱{overall_sales:,.2f} - Caloocan ₱{caloocan_sales:,.2f})",
                            "SUCCESS"
                        )

                        if store:
                            if dropdown_sel:
                                store["eod_dropdown_selector"] = dropdown_sel
                            if yesterday_sel:
                                store["eod_yesterday_selector"] = yesterday_sel
                            if multi_selectors:
                                store["multi_selectors"] = multi_selectors
                                store["expected_count"] = count

                        self.cached_shared_sales = {
                            "timestamp": time.time(),
                            "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            "is_eod": True,
                            "overall_sales": overall_sales,
                            "caloocan_sales": caloocan_sales,
                            "san_fernando_sales": san_fernando_sales,
                            "caloocan_count": count,
                            "san_fernando_count": 35,
                            "total_stores_count": 65
                        }
                        self.save_config()

                        if on_complete:
                            on_complete(sample_text, f"₱{caloocan_sales:,.2f}")
                        return True
                    else:
                        sales_sel = res.get("sales_selector", "")
                        sample_text = res.get("text", "")

                        self.log(
                            f"Successfully completed 3-Step EOD Training for [{store_name}]!\n"
                            f"• Dropdown Selector: {dropdown_sel or '(Skipped)'}\n"
                            f"• Yesterday Button Selector: {yesterday_sel}\n"
                            f"• EOD Sales Selector: {sales_sel} (Sample: '{sample_text}')",
                            "SUCCESS"
                        )

                        if store:
                            store["eod_url"] = raw_url
                            if dropdown_sel:
                                store["eod_dropdown_selector"] = dropdown_sel
                            if yesterday_sel:
                                store["eod_yesterday_selector"] = yesterday_sel
                            if sales_sel:
                                store["eod_selector"] = sales_sel
                        self.save_config()

                        if on_complete:
                            on_complete(sales_sel, sample_text)
                        return True

            self.log(f"3-Step EOD Training timed out for [{store_name}] (no completion within 5 minutes).", "WARNING")
            return False
        except Exception as e:
            self.log(f"3-Step EOD Training error on [{store_name}]: {e}", "ERROR")
            return False

    def train_multi_picker(self, store_id: str, on_complete: Optional[Callable[[List[str], float, int], None]] = None) -> bool:
        """
        Interactive Multi-Item Selector Training for stores with multiple branch lists (e.g. Caloocan 1-30, San Fernando 1-34).
        Allows clicking each store's sales number in order, showing badges (#1, #2, #3...) and live preview sum.
        """
        store = next((s for s in self.config.get("stores", []) if s["id"] == store_id), None)
        profile_id = store.get("profile_id", "grab_3") if store else "grab_3"
        store_name = store["name"] if store else store_id

        page = self.launch_profile_browser(profile_id, focus_url=False)
        if not page or page.is_closed():
            self.log(f"Cannot train multi-select: Browser for [{profile_id}] is closed.", "ERROR")
            return False

        self.log(f"[Multi-Select Training] Started for [{store_name}]. Click each store's sales number on the webpage, then click 'Done'.", "WARNING")

        js_multi_picker = f"""
        () => {{
            if (window.__multiPickerActive) return;
            window.__multiPickerActive = true;
            
            const selectedItems = [];

            // Floating Header Bar
            const bar = document.createElement('div');
            bar.id = '__scraper_multi_bar';
            bar.innerHTML = `
                <div style="position:fixed;top:10px;left:50%;transform:translateX(-50%);z-index:9999999;
                            background:linear-gradient(135deg, #0f172a, #1e293b);color:#f1f5f9;padding:12px 20px;
                            border-radius:14px;box-shadow:0 12px 30px rgba(0,0,0,0.6);border:2px solid #38bdf8;
                            font-family:sans-serif;font-size:13px;font-weight:600;display:flex;align-items:center;gap:14px;">
                    <div style="display:flex;flex-direction:column;">
                        <span style="color:#38bdf8;font-size:14px;font-weight:bold;">MULTI-SELECT: {store_name}</span>
                        <span id="__multi_stats" style="color:#94a3b8;font-size:12px;">Clicked: 0 stores | Total Preview: ₱ 0.00</span>
                    </div>
                    <button id="__multi_done_btn" style="background:#10b981;color:white;border:none;padding:8px 16px;border-radius:8px;cursor:pointer;font-weight:bold;font-size:13px;">Done (Save 0)</button>
                    <button id="__multi_clear_btn" style="background:#475569;color:white;border:none;padding:8px 12px;border-radius:8px;cursor:pointer;font-size:12px;">Clear</button>
                    <button id="__multi_cancel_btn" style="background:#ef4444;color:white;border:none;padding:8px 12px;border-radius:8px;cursor:pointer;font-size:12px;">Cancel</button>
                </div>
            `;
            document.body.appendChild(bar);

            function getCssPath(el) {{
                if (!(el instanceof Element)) return;
                var path = [];
                while (el.nodeType === Node.ELEMENT_NODE) {{
                    var selector = el.nodeName.toLowerCase();
                    if (el.id) {{
                        selector += '#' + el.id;
                        path.unshift(selector);
                        break;
                    }} else {{
                        var sib = el, nth = 1;
                        while (sib = sib.previousElementSibling) {{
                            if (sib.nodeName.toLowerCase() == selector)
                                nth++;
                        }}
                        if (nth != 1)
                            selector += ":nth-of-type("+nth+")";
                    }}
                    path.unshift(selector);
                    el = el.parentNode;
                }}
                return path.join(" > ");
            }}

            function parseAmount(txt) {{
                if (!txt) return 0.0;
                const cleaned = txt.replace(/[₱$PHP,]/gi, '').trim();
                const match = cleaned.match(/[-+]?\\d*\\.?\\d+/);
                return match ? parseFloat(match[0]) : 0.0;
            }}

            function updateUI() {{
                const total = selectedItems.reduce((sum, item) => sum + item.amount, 0);
                const statsEl = document.getElementById('__multi_stats');
                const doneBtn = document.getElementById('__multi_done_btn');
                if (statsEl) {{
                    statsEl.innerHTML = `Clicked: <b style="color:#10b981;">${{selectedItems.length}} stores</b> | Total Preview: <b style="color:#10b981;">₱ ${{total.toLocaleString(undefined, {{minimumFractionDigits: 2, maximumFractionDigits: 2}})}}</b>`;
                }}
                if (doneBtn) {{
                    doneBtn.innerText = `Done (Save ${{selectedItems.length}} Stores)`;
                }}
            }}

            let hoverTarget = null;
            let originalOutline = '';

            function onMouseMove(e) {{
                if (e.target.closest('#__scraper_multi_bar')) return;
                if (hoverTarget && hoverTarget !== e.target) {{
                    if (!hoverTarget.getAttribute('data-scraper-selected')) {{
                        hoverTarget.style.outline = originalOutline;
                    }}
                }}
                hoverTarget = e.target;
                if (!hoverTarget.getAttribute('data-scraper-selected')) {{
                    originalOutline = hoverTarget.style.outline;
                    hoverTarget.style.outline = '2px dashed #38bdf8';
                    hoverTarget.style.cursor = 'pointer';
                }}
            }}

            function onClick(e) {{
                if (e.target.id === '__multi_cancel_btn') {{
                    cleanup();
                    window.__multiPickerResult = {{ cancelled: true }};
                    return;
                }}
                if (e.target.id === '__multi_clear_btn') {{
                    clearAllSelections();
                    updateUI();
                    return;
                }}
                if (e.target.id === '__multi_done_btn') {{
                    const selectors = selectedItems.map(item => item.selector);
                    const totalSum = selectedItems.reduce((sum, item) => sum + item.amount, 0);
                    const count = selectedItems.length;
                    cleanup();
                    window.__multiPickerResult = {{
                        selectors: selectors,
                        totalSum: totalSum,
                        count: count
                    }};
                    return;
                }}
                if (e.target.closest('#__scraper_multi_bar')) return;

                e.preventDefault();
                e.stopPropagation();

                const el = e.target;
                const path = getCssPath(el);
                const txt = el.innerText || el.textContent || '';
                const amt = parseAmount(txt);

                // Check if already selected -> unselect
                const existingIdx = selectedItems.findIndex(item => item.el === el || item.selector === path);
                if (existingIdx !== -1) {{
                    // Remove selection
                    const badge = el.querySelector('.__scraper_badge');
                    if (badge) badge.remove();
                    el.removeAttribute('data-scraper-selected');
                    el.style.outline = '';
                    selectedItems.splice(existingIdx, 1);
                    // Renumber badges
                    selectedItems.forEach((item, idx) => {{
                        const b = item.el.querySelector('.__scraper_badge');
                        if (b) b.innerText = `#${{idx + 1}}`;
                    }});
                }} else {{
                    // Add selection
                    el.setAttribute('data-scraper-selected', 'true');
                    el.style.outline = '3px solid #10b981';
                    el.style.position = (window.getComputedStyle(el).position === 'static') ? 'relative' : el.style.position;

                    const badge = document.createElement('span');
                    badge.className = '__scraper_badge';
                    badge.innerText = `#${{selectedItems.length + 1}}`;
                    badge.style.position = 'absolute';
                    badge.style.top = '-8px';
                    badge.style.right = '-8px';
                    badge.style.background = '#10b981';
                    badge.style.color = 'white';
                    badge.style.fontSize = '10px';
                    badge.style.fontWeight = 'bold';
                    badge.style.padding = '2px 5px';
                    badge.style.borderRadius = '6px';
                    badge.style.boxShadow = '0 2px 6px rgba(0,0,0,0.4)';
                    badge.style.zIndex = '99999';
                    badge.style.pointerEvents = 'none';
                    el.appendChild(badge);

                    selectedItems.push({{
                        el: el,
                        selector: path,
                        text: txt.trim(),
                        amount: amt
                    }});
                }}

                updateUI();
            }}

            function clearAllSelections() {{
                selectedItems.forEach(item => {{
                    const badge = item.el.querySelector('.__scraper_badge');
                    if (badge) badge.remove();
                    item.el.removeAttribute('data-scraper-selected');
                    item.el.style.outline = '';
                }});
                selectedItems.length = 0;
            }}

            function cleanup() {{
                window.__multiPickerActive = false;
                document.removeEventListener('mousemove', onMouseMove, true);
                document.removeEventListener('click', onClick, true);
                clearAllSelections();
                const b = document.getElementById('__scraper_multi_bar');
                if (b) b.remove();
            }}

            window.__multiPickerResult = null;
            document.addEventListener('mousemove', onMouseMove, true);
            document.addEventListener('click', onClick, true);
        }}
        """

        try:
            page.evaluate(js_multi_picker)
            # Wait up to 5 minutes for user to click all stores
            for _ in range(300):
                time.sleep(1)
                res = page.evaluate("() => window.__multiPickerResult")
                if res:
                    if res.get("cancelled"):
                        self.log(f"Multi-select training cancelled for [{store_name}].", "WARNING")
                        return False
                    
                    selectors = res.get("selectors", [])
                    total_sum = res.get("totalSum", 0.0)
                    count = res.get("count", 0)

                    self.log(f"Successfully trained [{store_name}]! Saved {count} store elements (Sample Total: ₱{total_sum:,.2f})", "SUCCESS")
                    
                    if store:
                        store["multi_selectors"] = selectors
                        store["expected_count"] = count
                    self.save_config()

                    if on_complete:
                        on_complete(selectors, total_sum, count)
                    return True

            self.log(f"Multi-select training timed out for [{store_name}].", "WARNING")
            return False

        except Exception as e:
            self.log(f"Multi-select training error on [{store_name}]: {e}", "ERROR")
            return False

    def parse_grab_csv_sales(self, csv_path: str) -> Dict[str, Any]:
        """
        Parses a Grab Finance CSV and extracts sales per store and totals.
        Detects store names, amounts, and splits between Caloocan & San Fernando.
        """
        if not os.path.exists(csv_path):
            return {"success": False, "error": "CSV file not found", "total_sales": 0.0}

        encodings = ["utf-8-sig", "utf-8", "latin-1", "cp1252"]
        rows = []
        header_idx = -1
        headers = []

        for enc in encodings:
            try:
                with open(csv_path, "r", encoding=enc, errors="replace") as f:
                    reader = list(csv.reader(f))
                    if len(reader) >= 2:
                        rows = reader
                        break
            except Exception:
                continue

        if not rows:
            return {"success": False, "error": "Empty or unreadable CSV", "total_sales": 0.0}

        # Find the header row
        for idx, row in enumerate(rows[:20]):
            row_str = " ".join([c.lower() for c in row])
            if any(k in row_str for k in ["store", "merchant", "outlet", "branch", "restaurant"]) and any(
                k in row_str for k in ["amount", "gross", "net", "sales", "total", "earning", "payout", "price"]
            ):
                header_idx = idx
                headers = [c.strip() for c in row]
                break

        if header_idx == -1:
            header_idx = 0
            headers = [c.strip() for c in rows[0]]

        # Identify store column and amount column
        store_col_idx = -1
        amount_col_idx = -1

        for idx, h in enumerate(headers):
            h_lower = h.lower()
            if store_col_idx == -1 and any(k in h_lower for k in ["store name", "merchant name", "outlet", "branch", "store", "restaurant"]):
                store_col_idx = idx
            if amount_col_idx == -1 and any(k in h_lower for k in ["merchant earning", "gross amount", "net amount", "total", "gross sales", "amount", "sales", "net sales", "payout"]):
                amount_col_idx = idx

        if amount_col_idx == -1:
            amount_col_idx = len(headers) - 1

        caloocan_sum = 0.0
        san_fernando_sum = 0.0
        grand_total = 0.0
        caloocan_stores = set()
        san_fernando_stores = set()
        all_stores = {}

        data_rows = rows[header_idx + 1 :]
        for row_idx, r in enumerate(data_rows):
            if not r or len(r) <= max(store_col_idx, amount_col_idx):
                continue
            
            store_name = r[store_col_idx].strip() if store_col_idx >= 0 and store_col_idx < len(r) else f"Store {row_idx + 1}"
            amt_str = r[amount_col_idx].strip() if amount_col_idx >= 0 and amount_col_idx < len(r) else "0"
            
            # Clean amount string
            amt_cleaned = amt_str.replace("₱", "").replace("PHP", "").replace("$", "").replace(",", "").strip()
            m = re.search(r"[-+]?\d*\.?\d+", amt_cleaned)
            amt = float(m.group(0)) if m else 0.0

            if not store_name or amt_str == "":
                continue

            all_stores[store_name] = all_stores.get(store_name, 0.0) + amt
            grand_total += amt

            # Classify store
            s_lower = store_name.lower()
            if "caloocan" in s_lower or "cal" in s_lower:
                caloocan_sum += amt
                caloocan_stores.add(store_name)
            elif "san fernando" in s_lower or "pampanga" in s_lower or "sf" in s_lower or "fernando" in s_lower:
                san_fernando_sum += amt
                san_fernando_stores.add(store_name)
            else:
                # If name doesn't specify, split by store order index (1..30 vs 31..65)
                if row_idx < 30:
                    caloocan_sum += amt
                    caloocan_stores.add(store_name)
                else:
                    san_fernando_sum += amt
                    san_fernando_stores.add(store_name)

        return {
            "success": True,
            "csv_path": csv_path,
            "csv_file": os.path.basename(csv_path),
            "total_sales": grand_total,
            "caloocan_sales": caloocan_sum,
            "san_fernando_sales": san_fernando_sum,
            "caloocan_count": len(caloocan_stores),
            "san_fernando_count": len(san_fernando_stores),
            "total_stores_found": len(all_stores),
            "stores_breakdown": all_stores
        }

    def train_csv_export_steps(self, store_id: str, on_complete: Optional[Callable[[List[str], Optional[dict]], None]] = None) -> bool:
        """Interactive recorder that captures the sequence of clicks to export and download Grab CSV."""
        store = next((s for s in self.config.get("stores", []) if s["id"] == store_id), None)
        profile_id = store.get("profile_id", store_id) if store else store_id
        store_name = store["name"] if store else store_id

        page = self.launch_profile_browser(profile_id, focus_url=True)
        if not page or page.is_closed():
            self.log(f"Cannot train CSV export: Browser for [{profile_id}] is not open.", "ERROR")
            return False

        self.log(f"[CSV Export Recorder] Active for [{store_name}]. Click the export button(s) on the Grab page to download CSV.", "WARNING")

        js_recorder = """
        () => {
            if (window.__csvRecorderActive) return;
            window.__csvRecorderActive = true;
            window.__recordedExportSteps = [];
            window.__exportRecorderResult = null;

            const bar = document.createElement('div');
            bar.id = '__scraper_csv_recorder_bar';
            bar.innerHTML = `
                <div style="position:fixed;top:10px;left:50%;transform:translateX(-50%);z-index:999999;
                            background:linear-gradient(135deg, #064e3b, #0f172a);color:#34d399;padding:12px 24px;
                            border-radius:14px;box-shadow:0 10px 30px rgba(0,0,0,0.6);border:2px solid #10b981;
                            font-family:sans-serif;display:flex;align-items:center;gap:15px;">
                    <div style="font-weight:bold;font-size:14px;">
                        <span>CSV EXPORT RECORDER: Click the Export/Download button(s) on this page</span>
                        <div id="__scraper_step_counter" style="color:#94a3b8;font-size:12px;font-weight:normal;margin-top:2px;">Recorded 0 steps</div>
                    </div>
                    <button id="__scraper_csv_save_btn" style="background:#10b981;color:white;border:none;padding:7px 15px;border-radius:8px;cursor:pointer;font-weight:bold;font-size:13px;box-shadow:0 2px 8px rgba(16,185,129,0.4);">
                        Save & Test Download
                    </button>
                    <button id="__scraper_csv_cancel_btn" style="background:#ef4444;color:white;border:none;padding:7px 12px;border-radius:8px;cursor:pointer;font-weight:bold;font-size:12px;">
                        Cancel
                    </button>
                </div>
            `;
            document.body.appendChild(bar);

            function getCssPath(el) {
                if (!(el instanceof Element)) return;
                var path = [];
                while (el.nodeType === Node.ELEMENT_NODE) {
                    var selector = el.nodeName.toLowerCase();
                    if (el.id) {
                        selector += '#' + el.id;
                        path.unshift(selector);
                        break;
                    } else {
                        var sib = el, nth = 1;
                        while (sib = sib.previousElementSibling) {
                            if (sib.nodeName.toLowerCase() == selector)
                                nth++;
                        }
                        if (nth != 1)
                            selector += ":nth-of-type("+nth+")";
                    }
                    path.unshift(selector);
                    el = el.parentNode;
                }
                return path.join(" > ");
            }

            function onClick(e) {
                if (e.target.closest('#__scraper_csv_recorder_bar')) {
                    if (e.target.id === '__scraper_csv_cancel_btn') {
                        cleanup();
                        window.__exportRecorderResult = { cancelled: true };
                    } else if (e.target.id === '__scraper_csv_save_btn') {
                        const steps = [...window.__recordedExportSteps];
                        cleanup();
                        window.__exportRecorderResult = { cancelled: false, steps: steps };
                    }
                    return;
                }

                const path = getCssPath(e.target);
                if (path && !window.__recordedExportSteps.includes(path)) {
                    window.__recordedExportSteps.push(path);
                    
                    e.target.style.outline = '3px solid #10b981';
                    const counter = document.getElementById('__scraper_step_counter');
                    if (counter) counter.innerText = `Recorded ${window.__recordedExportSteps.length} step(s): [${e.target.innerText.trim().slice(0, 20) || path.slice(-25)}]`;
                }
            }

            function cleanup() {
                window.__csvRecorderActive = false;
                document.removeEventListener('click', onClick, true);
                const b = document.getElementById('__scraper_csv_recorder_bar');
                if (b) b.remove();
            }

            document.addEventListener('click', onClick, true);
        }
        """

        try:
            page.evaluate(js_recorder)
            start_time = time.time()

            while time.time() - start_time < 180:
                time.sleep(0.5)
                res = page.evaluate("() => window.__exportRecorderResult")
                if res:
                    if res.get("cancelled"):
                        self.log(f"CSV Export training cancelled for [{store_name}].", "WARNING")
                        return False
                    
                    steps = res.get("steps", [])
                    if not steps:
                        self.log(f"No click steps were recorded for [{store_name}].", "WARNING")
                        return False

                    self.log(f"Recorded {len(steps)} export action step(s). Executing test download...", "INFO")
                    
                    # Test replay the steps with expect_download
                    csv_path = None
                    try:
                        downloads_dir = os.path.join(BASE_DIR, "downloads")
                        os.makedirs(downloads_dir, exist_ok=True)
                        
                        with page.expect_download(timeout=25000) as download_info:
                            for sel in steps:
                                loc = page.locator(sel).first
                                if loc.is_visible(timeout=4000):
                                    loc.click()
                                    time.sleep(1.2)
                        
                        download = download_info.value
                        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                        csv_path = os.path.join(downloads_dir, f"grab_tx_{ts}.csv")
                        download.save_as(csv_path)
                        self.log(f"Download intercepted successfully! Saved to: {os.path.basename(csv_path)}", "SUCCESS")
                    except Exception as de:
                        self.log(f"Download note: {de}. Action steps saved to config.", "INFO")

                    # Save steps to config
                    if store:
                        store["csv_export_steps"] = steps
                    self.save_config()

                    parsed_res = None
                    if csv_path and os.path.exists(csv_path):
                        parsed_res = self.parse_grab_csv_sales(csv_path)
                        if parsed_res.get("success"):
                            self.log(f"[CSV Parsed] Total Sales: ₱{parsed_res['total_sales']:,.2f} | Caloocan: ₱{parsed_res['caloocan_sales']:,.2f} ({parsed_res['caloocan_count']} stores) | San Fernando: ₱{parsed_res['san_fernando_sales']:,.2f} ({parsed_res['san_fernando_count']} stores)", "SUCCESS")

                    if on_complete:
                        on_complete(steps, parsed_res)

                    return True

            self.log(f"CSV Export recorder timed out for [{store_name}].", "WARNING")
            return False

        except Exception as e:
            self.log(f"CSV Export training error on [{store_name}]: {e}", "ERROR")
            return False

    def extract_sales_from_page(self, page: Page, store: dict, is_eod: bool = False) -> Dict[str, Any]:
        """Extracts sales text using multi_selectors sum, single selector (or eod_selector), or smart DOM fallback."""
        multi_sels = store.get("multi_selectors", [])
        raw_text = ""
        extracted_value = 0.0
        success = False
        method = "None"

        # 0. Auto-Scroll and Intelligent Net Sales Extractor for Multi-Store Grab Overview Pages
        is_grab = store.get("platform", "grab") == "grab"
        is_caloocan_store = is_grab and ("caloocan" in store["id"].lower() or "caloocan" in store["name"].lower())
        is_san_fernando_store = is_grab and ("san_fernando" in store["id"].lower() or "fernando" in store["name"].lower())

        if (is_caloocan_store or is_san_fernando_store) and "finances" in getattr(page, "url", ""):
            try:
                # Scroll down in increments to render all virtualized/lazy-loaded store cards (1 to 30 or 1 to 65)
                for _ in range(10):
                    page.evaluate("() => { window.scrollBy(0, 600); const p = document.querySelector('#rc-tabs-0-panel-overview, .ant-tabs-content'); if (p) p.scrollTop += 600; }")
                    time.sleep(0.12)
                page.evaluate("() => { window.scrollTo(0, 0); const p = document.querySelector('#rc-tabs-0-panel-overview, .ant-tabs-content'); if (p) p.scrollTop = 0; }")
                time.sleep(0.2)

                js_overview_parser = """
                () => {
                    const text = document.body.innerText || '';
                    const lines = text.split('\\n').map(l => l.trim()).filter(Boolean);
                    let topOverallNetSales = 0.0;
                    let foundFirstStoreCard = false;

                    const stores = [];
                    const seen = new Set();

                    for (let i = 0; i < lines.length; i++) {
                        const line = lines[i];
                        const lineLower = line.toLowerCase();

                        // Detect store card header line
                        const isStoreName = (lineLower.includes('- caloocan') || lineLower.includes('- san fernando') ||
                                             (lineLower.includes('caloocan') && !lineLower.includes('merchant')) ||
                                             (lineLower.includes('san fernando') && !lineLower.includes('merchant'))) &&
                                            lineLower !== 'net sales' && lineLower !== 'gross sales' &&
                                            lineLower !== 'overview' && lineLower !== 'outlet performance' &&
                                            lineLower !== 'total net sales';

                        if (isStoreName && !foundFirstStoreCard) {
                            foundFirstStoreCard = true;
                        }

                        // Check for top overview Net sales before the first store card
                        if (!foundFirstStoreCard && topOverallNetSales === 0.0 && (lineLower === 'net sales' || lineLower === 'total net sales')) {
                            for (let k = i + 1; k < Math.min(i + 4, lines.length); k++) {
                                const amtStr = lines[k].replace(/[₱$PHP,]/g, '').trim();
                                const m = amtStr.match(/[-+]?\\d*\\.?\\d+/);
                                if (m) {
                                    topOverallNetSales = parseFloat(m[0]);
                                    break;
                                }
                            }
                        }

                        if (isStoreName) {
                            const storeName = line;
                            let netSales = 0.0;
                            let found = false;

                            for (let j = i + 1; j < Math.min(i + 12, lines.length); j++) {
                                const subLine = lines[j].toLowerCase();
                                if (subLine === 'net sales' && j + 1 < lines.length) {
                                    const amtStr = lines[j + 1].replace(/[₱$PHP,]/g, '').trim();
                                    const m = amtStr.match(/[-+]?\\d*\\.?\\d+/);
                                    if (m) {
                                        netSales = parseFloat(m[0]);
                                        found = true;
                                        break;
                                    }
                                }
                                if (lines[j].toLowerCase().includes('- caloocan') || lines[j].toLowerCase().includes('- san fernando')) {
                                    break;
                                }
                            }

                            if (found && !seen.has(storeName)) {
                                seen.add(storeName);
                                stores.push({
                                    name: storeName,
                                    net_sales: netSales,
                                    is_caloocan: storeName.toLowerCase().includes('caloocan'),
                                    is_san_fernando: storeName.toLowerCase().includes('san fernando') || storeName.toLowerCase().includes('fernando')
                                });
                            }
                        }
                    }

                    const caloocanStores = stores.filter(s => s.is_caloocan);
                    const sanFernandoStores = stores.filter(s => s.is_san_fernando);
                    const caloocanSum = caloocanStores.reduce((acc, s) => acc + s.net_sales, 0.0);
                    const sanFernandoSum = sanFernandoStores.reduce((acc, s) => acc + s.net_sales, 0.0);
                    const allStoresSum = stores.reduce((acc, s) => acc + s.net_sales, 0.0);

                    return {
                        top_overall_net_sales: topOverallNetSales,
                        all_stores_sum: allStoresSum,
                        caloocan_sum: caloocanSum,
                        san_fernando_sum: sanFernandoSum,
                        caloocan_count: caloocanStores.length,
                        san_fernando_count: sanFernandoStores.length,
                        total_stores_count: stores.length,
                        stores: stores
                    };
                }
                """
                overview_data = page.evaluate(js_overview_parser)
                if overview_data:
                    top_overall = overview_data.get("top_overall_net_sales", 0.0)
                    all_stores_sum = round(overview_data.get("all_stores_sum", 0.0), 2)
                    caloocan_sum = round(overview_data.get("caloocan_sum", 0.0), 2)
                    san_fernando_sum_cards = round(overview_data.get("san_fernando_sum", 0.0), 2)
                    caloocan_count = overview_data.get("caloocan_count", 0)
                    san_fernando_count = overview_data.get("san_fernando_count", 0)

                    # Determine overall total net sales
                    overall_sales = top_overall if top_overall > 0 else (all_stores_sum if all_stores_sum > 0 else caloocan_sum)
                    
                    # Compute San Fernando = Overall Sales - Caloocan Sales
                    if overall_sales > caloocan_sum:
                        san_fernando_sales = round(overall_sales - caloocan_sum, 2)
                    elif san_fernando_sum_cards > 0:
                        san_fernando_sales = san_fernando_sum_cards
                    else:
                        san_fernando_sales = 0.0

                    # Cache calculated shared values
                    self.cached_shared_sales = {
                        "timestamp": time.time(),
                        "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "is_eod": is_eod,
                        "overall_sales": overall_sales,
                        "caloocan_sales": caloocan_sum,
                        "san_fernando_sales": san_fernando_sales,
                        "caloocan_count": caloocan_count,
                        "san_fernando_count": san_fernando_count,
                        "total_stores_count": overview_data.get("total_stores_count", 0)
                    }

                    mode_tag = "[EOD] " if is_eod else ""
                    if is_caloocan_store and (caloocan_count > 0 or caloocan_sum > 0):
                        raw_text = f"₱{caloocan_sum:,.2f} ({caloocan_count} stores)"
                        self.log(f"{mode_tag}[{store['name']}] Scraped: {raw_text} (₱{caloocan_sum:,.2f}) | Overall Portal Sales: ₱{overall_sales:,.2f}", "SUCCESS")
                        self.log(f"{mode_tag}[Shared Deduction] San Fernando City calculated: ₱{san_fernando_sales:,.2f} (Overall ₱{overall_sales:,.2f} - Caloocan ₱{caloocan_sum:,.2f})", "SUCCESS")
                        return {
                            "store_id": store["id"],
                            "store_name": store["name"],
                            "platform": store.get("platform", "grab"),
                            "raw_text": raw_text,
                            "amount": caloocan_sum,
                            "is_eod": is_eod,
                            "success": True,
                            "method": f"Grab Net Sales Extractor ({caloocan_count} stores)",
                            "shared_sales": self.cached_shared_sales,
                            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        }

                    elif is_san_fernando_store:
                        raw_text = f"₱{san_fernando_sales:,.2f} (Overall ₱{overall_sales:,.2f} - Caloocan ₱{caloocan_sum:,.2f})"
                        self.log(f"{mode_tag}[{store['name']}] Scraped via Shared Deduction: {raw_text}", "SUCCESS")
                        return {
                            "store_id": store["id"],
                            "store_name": store["name"],
                            "platform": store.get("platform", "grab"),
                            "raw_text": raw_text,
                            "amount": san_fernando_sales,
                            "is_eod": is_eod,
                            "success": True,
                            "method": "Shared Balance (Overall - Caloocan)",
                            "shared_sales": self.cached_shared_sales,
                            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        }
            except Exception as e:
                self.log(f"Auto-overview parse note for [{store['name']}]: {e}", "DEBUG")

        # 1. Multi-Item Extraction (e.g. 30 Caloocan stores or 34 San Fernando stores)
        if not success and multi_sels and len(multi_sels) > 0:
            found_count = 0
            items_sum = 0.0
            
            for sel in multi_sels:
                try:
                    elem = page.locator(sel).first
                    if elem.is_visible(timeout=1500):
                        t = elem.inner_text().strip()
                        cleaned = t.replace("₱", "").replace("PHP", "").replace("$", "").replace(",", "").strip()
                        m = re.search(r"[-+]?\d*\.?\d+", cleaned)
                        if m:
                            items_sum += float(m.group(0))
                            found_count += 1
                except Exception:
                    pass

            if found_count > 0:
                extracted_value = items_sum
                raw_text = f"₱{extracted_value:,.2f} ({found_count}/{len(multi_sels)} stores)"
                method = f"Multi-Store Sum ({found_count}/{len(multi_sels)})"
                success = True
            else:
                self.log(f"Multi-selectors not visible for [{store['name']}].", "WARNING")

        # 2. Single Selector (Live selector vs EOD Selector for Angeles & Quezon City)
        if not success:
            single_sel = ""
            if is_eod and store.get("eod_selector", "").strip():
                single_sel = store.get("eod_selector", "").strip()
            elif store.get("selector", "").strip():
                single_sel = store.get("selector", "").strip()

            if single_sel:
                try:
                    locator = page.locator(single_sel).first
                    # Wait up to 10 seconds for Foodpanda to hydrate DOM, 4 seconds for Grab
                    loc_timeout = 10000 if not is_grab else 4000
                    try:
                        locator.wait_for(state="visible", timeout=loc_timeout)
                    except Exception:
                        pass

                    if locator.is_visible(timeout=1500):
                        raw_text = locator.inner_text().strip()
                        if raw_text:
                            # Verify that raw_text is not just a date tab / button (e.g. "7 Days", "30 Days", "Today")
                            lower_txt = raw_text.lower()
                            if any(k in lower_txt for k in ("days", "today", "yesterday", "week", "month", "orders", "items", "reviews")):
                                raw_text = ""
                            else:
                                method = f"{'EOD ' if is_eod else ''}Selector ({single_sel[:30]}...)"
                                success = True
                except Exception as e:
                    self.log(f"Selector lookup note for [{store['name']}]: {e}", "DEBUG")

        # 2b. Specialized Foodpanda Article / Card Parser Fallback
        if not is_grab and (not success or not raw_text or raw_text in ("₱0.00", "0", "Not Found")):
            try:
                js_panda_cards = """
                () => {
                    const articles = Array.from(document.querySelectorAll('article, div[data-testid*="card"], div.dashboard-card, div.overview-card'));
                    const cards = [];
                    articles.forEach((art, idx) => {
                        const fullText = (art.innerText || art.textContent || '').trim();
                        let foundVal = null;
                        
                        // Look for h5, h4, h3, h2, strong, or metric spans/paragraphs
                        const allCandidates = Array.from(art.querySelectorAll('h5, h4, h3, h2, strong, [data-testid*="metric"], [data-testid*="sales"], [data-testid*="amount"], p > span, div > span'));
                        
                        // Strict exclusion: Reject any element inside navigation, tabs, button groups, date pickers
                        const validCandidates = allCandidates.filter(el => {
                            if (el.closest('nav, button, [role="tab"], [role="tablist"], [role="navigation"], header, .ant-picker, .ant-select, select, input')) {
                                return false;
                            }
                            return true;
                        });

                        // Priority 1: Elements with explicit currency symbol (₱, PHP, $)
                        for (let el of validCandidates) {
                            const t = (el.innerText || el.textContent || '').trim();
                            if (/\\b(days?|hours?|mins?|minutes?|orders?|items?|reviews?|rating|growth|comparison|vs|today|yesterday|week|month|all|past)\\b/i.test(t)) {
                                continue;
                            }
                            if (/[₱$PHP]/.test(t)) {
                                const cleaned = t.replace(/[₱$PHP,]/gi, '').trim();
                                const m = cleaned.match(/[-+]?\\d*\\.?\\d+/);
                                if (m && parseFloat(m[0]) > 0) {
                                    foundVal = t;
                                    break;
                                }
                            }
                        }

                        // Priority 2: Monetary formatted numbers in headings (e.g. 1,450.00 or 1450.00 or 1450)
                        if (!foundVal) {
                            for (let el of validCandidates) {
                                const t = (el.innerText || el.textContent || '').trim();
                                if (/\\b(days?|hours?|mins?|minutes?|orders?|items?|reviews?|rating|growth|comparison|vs|today|yesterday|week|month|all|past)\\b/i.test(t)) {
                                    continue;
                                }
                                if (/^[0-9]{1,3}(?:,[0-9]{3})+(?:\\.[0-9]{2})?$/.test(t) || /^[0-9]+(?:\\.[0-9]{2})$/.test(t) || /^[0-9]{3,}$/.test(t)) {
                                    const cleaned = t.replace(/,/g, '').trim();
                                    const m = cleaned.match(/[-+]?\\d*\\.?\\d+/);
                                    if (m && parseFloat(m[0]) > 0) {
                                        foundVal = `₱${t}`;
                                        break;
                                    }
                                }
                            }
                        }

                        cards.push({
                            index: idx + 1,
                            salesText: foundVal || '',
                            fullText: fullText
                        });
                    });
                    return cards;
                }
                """
                cards_data = page.evaluate(js_panda_cards)
                if cards_data and len(cards_data) > 0:
                    target_card = None
                    store_id_lower = store["id"].lower()
                    
                    if "panda_4" in store_id_lower or "fernando" in store["name"].lower():
                        # San Fernando Panda is typically the 3rd article, or matching "fernando"
                        for c in cards_data:
                            if "fernando" in c["fullText"].lower() and c["salesText"]:
                                target_card = c
                                break
                        if not target_card and len(cards_data) >= 3 and cards_data[2]["salesText"]:
                            target_card = cards_data[2]
                        elif not target_card and len(cards_data) >= 2 and cards_data[1]["salesText"]:
                            target_card = cards_data[1]

                    elif "panda_3" in store_id_lower or "caloocan" in store["name"].lower():
                        for c in cards_data:
                            if "caloocan" in c["fullText"].lower() and c["salesText"]:
                                target_card = c
                                break
                        if not target_card and len(cards_data) >= 2 and cards_data[1]["salesText"]:
                            target_card = cards_data[1]

                    elif "panda_2" in store_id_lower:
                        if len(cards_data) >= 2 and cards_data[1]["salesText"]:
                            target_card = cards_data[1]
                        elif len(cards_data) >= 1 and cards_data[0]["salesText"]:
                            target_card = cards_data[0]

                    elif "panda_1" in store_id_lower:
                        if len(cards_data) >= 2 and cards_data[1]["salesText"]:
                            target_card = cards_data[1]
                        elif len(cards_data) >= 1 and cards_data[0]["salesText"]:
                            target_card = cards_data[0]

                    if target_card and target_card.get("salesText"):
                        raw_text = target_card["salesText"]
                        method = f"Foodpanda Card Parser (Card #{target_card['index']})"
                        success = True
                        self.log(f"[{store['name']}] Found via Foodpanda Card #{target_card['index']}: {raw_text}", "SUCCESS")
            except Exception as e:
                self.log(f"Foodpanda card parse fallback error for [{store['name']}]: {e}", "DEBUG")

        # 3. Smart DOM Fallback
        if not success or not raw_text:
            try:
                smart_js = """
                () => {
                    const candidates = [];
                    const allElems = document.querySelectorAll('h1, h2, h3, h4, h5, span, div, p, strong, b');
                    for (let el of allElems) {
                        if (el.children.length > 2) continue;
                        const t = el.innerText || '';
                        if (!t) continue;
                        
                        if (/[₱$]|PHP|RM|SGD|\\b(Today|Yesterday|Gross|Sales|Revenue|Total)\\b/i.test(t)) {
                            const numMatch = t.match(/[0-9]{1,3}(?:,[0-9]{3})*(?:\\.[0-9]{2})|[0-9]+(?:\\.[0-9]{2})/);
                            if (numMatch && parseFloat(numMatch[0].replace(/,/g, '')) > 0) {
                                candidates.push({
                                    text: t.trim(),
                                    number: numMatch[0],
                                    tag: el.tagName
                                });
                            }
                        }
                    }
                    return candidates;
                }
                """
                candidates = page.evaluate(smart_js)
                if candidates:
                    best = candidates[0]
                    raw_text = best.get("text", "")
                    method = "Smart Pattern Match"
                    success = True
            except Exception as e:
                self.log(f"Smart search error for [{store['name']}]: {e}", "WARNING")

        # Parse numeric float if not already computed from multi_selectors
        if success and not multi_sels and raw_text:
            cleaned = raw_text.replace(",", "")
            num_match = re.search(r"(\d+(?:\.\d{2})?)", cleaned)
            if num_match:
                try:
                    extracted_value = float(num_match.group(1))
                except ValueError:
                    pass

        return {
            "store_id": store["id"],
            "store_name": store["name"],
            "platform": store.get("platform", "grab"),
            "raw_text": raw_text if raw_text else "Not Found",
            "amount": extracted_value,
            "is_eod": is_eod,
            "success": success,
            "method": method,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

    def scrape_store(self, store_id: str, max_retries: Optional[int] = None, is_eod: bool = False) -> Dict[str, Any]:
        """Scrapes sales data for a single store (in Live Ops mode or EOD yesterday mode)."""
        if self.stop_requested:
            return {"store_id": store_id, "store_name": store_id, "success": False, "raw_text": "Scrape Cancelled", "amount": 0.0, "is_eod": is_eod, "cancelled": True}

        store = next((s for s in self.config.get("stores", []) if s["id"] == store_id), None)
        if not store:
            return {"store_id": store_id, "store_name": store_id, "success": False, "raw_text": "Store not configured", "amount": 0.0, "is_eod": is_eod}

        is_grab = store.get("platform", "grab") == "grab"
        is_san_fernando_grab = is_grab and ("san_fernando" in store_id.lower() or "fernando" in store["name"].lower())
        
        # Check cached shared deduction if valid and matching mode
        if is_san_fernando_grab and self.cached_shared_sales:
            cache_eod = self.cached_shared_sales.get("is_eod", False)
            if cache_eod == is_eod and time.time() - self.cached_shared_sales.get("timestamp", 0) < 300:
                sf_amt = self.cached_shared_sales.get("san_fernando_sales", 0.0)
                overall_amt = self.cached_shared_sales.get("overall_sales", 0.0)
                cal_amt = self.cached_shared_sales.get("caloocan_sales", 0.0)
                mode_tag = "[EOD] " if is_eod else ""
                raw_text = f"₱{sf_amt:,.2f} (Overall ₱{overall_amt:,.2f} - Caloocan ₱{cal_amt:,.2f})"
                self.log(f"{mode_tag}[{store['name']}] Instant Scraped via Shared Deduction: {raw_text}", "SUCCESS")
                return {
                    "store_id": store["id"],
                    "store_name": store["name"],
                    "platform": "grab",
                    "raw_text": raw_text,
                    "amount": sf_amt,
                    "is_eod": is_eod,
                    "success": True,
                    "method": "Shared Balance (Overall - Caloocan)",
                    "shared_sales": self.cached_shared_sales,
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }

        profile_id = store.get("profile_id", store_id)
        if is_san_fernando_grab and profile_id not in self.pages and "grab_3" in self.pages:
            profile_id = "grab_3"

        page = self.launch_profile_browser(profile_id, focus_url=False)
        if not page or page.is_closed():
            return {"store_id": store_id, "store_name": store["name"], "success": False, "raw_text": "Browser Closed / Offline", "amount": 0.0, "is_eod": is_eod}

        # Resolve target URL based on Live vs EOD mode
        if is_eod and is_grab and store.get("eod_url"):
            raw_target_url = store.get("eod_url")
        else:
            raw_target_url = store.get("url", "")

        target_url = self.resolve_url(raw_target_url, is_eod=is_eod)
        if target_url:
            current_url = page.url
            if current_url in ("about:blank", "", "chrome://newtab/") or (
                target_url not in current_url and current_url not in target_url
            ) or ("finances" in target_url and target_url not in current_url):
                mode_tag = "[EOD] " if is_eod else ""
                self.log(f"Navigating [{store['name']}] to {mode_tag}{target_url}...", "INFO")
                page.goto(target_url, timeout=45000, wait_until="domcontentloaded")
                time.sleep(1.0)

        if self.stop_requested:
            return {"store_id": store_id, "store_name": store["name"], "success": False, "raw_text": "Scrape Cancelled", "amount": 0.0, "is_eod": is_eod, "cancelled": True}

        # Check if store is configured for automated CSV export
        csv_steps = store.get("csv_export_steps", [])
        if csv_steps:
            self.log(f"[CSV Auto-Export] Running {len(csv_steps)} export step(s) for [{store['name']}]...", "INFO")
            csv_path = None
            try:
                downloads_dir = os.path.join(BASE_DIR, "downloads")
                os.makedirs(downloads_dir, exist_ok=True)
                
                with page.expect_download(timeout=30000) as download_info:
                    for sel in csv_steps:
                        if self.stop_requested:
                            break
                        loc = page.locator(sel).first
                        if loc.is_visible(timeout=4000):
                            loc.click()
                            time.sleep(1.0)
                if not self.stop_requested:
                    download = download_info.value
                    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                    csv_path = os.path.join(downloads_dir, f"{store_id}_{ts}.csv")
                    download.save_as(csv_path)
            except Exception as e:
                self.log(f"CSV auto-download note: {e}", "WARNING")

            if self.stop_requested:
                return {"store_id": store_id, "store_name": store["name"], "success": False, "raw_text": "Scrape Cancelled", "amount": 0.0, "is_eod": is_eod, "cancelled": True}

            if csv_path and os.path.exists(csv_path):
                parsed = self.parse_grab_csv_sales(csv_path)
                if parsed.get("success"):
                    is_caloocan = "caloocan" in store_id.lower() or "caloocan" in store["name"].lower()
                    is_san_fernando = "san_fernando" in store_id.lower() or "fernando" in store["name"].lower()
                    
                    if is_caloocan:
                        amt = parsed["caloocan_sales"]
                        raw_text = f"₱{amt:,.2f} ({parsed['caloocan_count']} Caloocan stores)"
                        method = f"CSV Export ({parsed['caloocan_count']} stores)"
                    elif is_san_fernando:
                        amt = parsed["san_fernando_sales"]
                        raw_text = f"₱{amt:,.2f} ({parsed['san_fernando_count']} San Fernando stores)"
                        method = f"CSV Export ({parsed['san_fernando_count']} stores)"
                    else:
                        amt = parsed["total_sales"]
                        raw_text = f"₱{amt:,.2f} ({parsed['total_stores_found']} stores)"
                        method = "CSV Export Total"

                    self.log(f"[{store['name']}] Scraped via CSV: {raw_text} (₱{amt:,.2f})", "SUCCESS")
                    return {
                        "store_id": store["id"],
                        "store_name": store["name"],
                        "platform": store.get("platform", "grab"),
                        "raw_text": raw_text,
                        "amount": amt,
                        "is_eod": is_eod,
                        "success": True,
                        "method": method,
                        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    }

        retries_limit = max_retries or self.config.get("general", {}).get("max_retries", 3)
        force_retry_on_zero = self.config.get("general", {}).get("force_retry_on_zero", True)
        last_result = None

        is_panda = store.get("platform") == "foodpanda" or "panda" in store_id.lower()
        if is_panda:
            refresh_delay_ms = max(10000, int(self.config.get("general", {}).get("panda_refresh_wait_seconds", 10) * 1000))
        else:
            refresh_delay_ms = int(self.config.get("general", {}).get("refresh_wait_seconds", 5) * 1000)

        for attempt in range(1, retries_limit + 1):
            if self.stop_requested:
                return {"store_id": store_id, "store_name": store["name"], "success": False, "raw_text": "Scrape Cancelled", "amount": 0.0, "is_eod": is_eod, "cancelled": True}

            try:
                # Auto-dismiss Foodpanda modal popups or marketing overlays if present
                if is_panda:
                    try:
                        page.evaluate("""() => {
                            const btns = Array.from(document.querySelectorAll('button, [role="button"], a'));
                            for (let b of btns) {
                                const t = (b.innerText || b.textContent || '').trim().toLowerCase();
                                if (['got it', 'close', 'dismiss', 'remind me later', 'skip', 'accept', 'ok', 'i understand'].includes(t)) {
                                    try { b.click(); } catch(e) {}
                                }
                            }
                        }""")
                    except Exception:
                        pass

                if attempt == 1:
                    if self.config.get("general", {}).get("auto_refresh", True):
                        self.log(f"Refreshing [{store['name']}] (waiting {refresh_delay_ms//1000}s for portal to adjust)...", "INFO")
                        page.reload(wait_until="domcontentloaded", timeout=45000)
                        if is_panda:
                            page.evaluate("() => { window.scrollBy(0, 100); setTimeout(() => window.scrollBy(0, -100), 200); }")
                        # Sleep in short chunks for responsive stop
                        wait_steps = max(1, refresh_delay_ms // 400)
                        for _ in range(wait_steps):
                            if self.stop_requested:
                                return {"store_id": store_id, "store_name": store["name"], "success": False, "raw_text": "Scrape Cancelled", "amount": 0.0, "is_eod": is_eod, "cancelled": True}
                            page.wait_for_timeout(400)
                else:
                    self.log(f"[Force Retry {attempt}/{retries_limit}] for [{store['name']}]: Value was 0 or unread. Reloading & waiting {refresh_delay_ms//1000}s...", "WARNING")
                    page.reload(wait_until="domcontentloaded", timeout=45000)
                    page.evaluate("() => { window.scrollBy(0, 150); setTimeout(() => window.scrollBy(0, -150), 200); }")
                    wait_steps = max(1, refresh_delay_ms // 400)
                    for _ in range(wait_steps):
                        if self.stop_requested:
                            return {"store_id": store_id, "store_name": store["name"], "success": False, "raw_text": "Scrape Cancelled", "amount": 0.0, "is_eod": is_eod, "cancelled": True}
                        page.wait_for_timeout(400)

                if self.stop_requested:
                    return {"store_id": store_id, "store_name": store["name"], "success": False, "raw_text": "Scrape Cancelled", "amount": 0.0, "is_eod": is_eod, "cancelled": True}

                # Automated EOD Yesterday selection for Grab and Foodpanda portals
                if is_eod:
                    dropdown_sel = store.get("eod_dropdown_selector", "").strip()
                    yesterday_sel = store.get("eod_yesterday_selector", "").strip()

                    # Step 1: Open date dropdown if selector exists or fallback
                    if dropdown_sel:
                        try:
                            d_loc = page.locator(dropdown_sel).first
                            if d_loc.is_visible(timeout=2500):
                                self.log(f"[EOD Automation] Clicking date dropdown for [{store['name']}]...", "INFO")
                                d_loc.click()
                                time.sleep(0.8)
                            else:
                                page.evaluate(f"""(sel) => {{
                                    const el = document.querySelector(sel);
                                    if (el) {{
                                        const target = el.closest('button, [role="button"], div[tabindex], input, select') || el;
                                        target.click();
                                    }}
                                }}""", dropdown_sel)
                                time.sleep(0.8)
                        except Exception as e:
                            self.log(f"Dropdown click note: {e}", "DEBUG")

                    # Step 2: Click 'Yesterday' option with strict matching & text fallback
                    js_click_yesterday = f"""
                    (yestSel) => {{
                        function simulateClick(el) {{
                            if (!el) return false;
                            const target = el.closest('button, [role="button"], [role="option"], [role="menuitem"], [role="tab"], [role="radio"], li, a, label, div[tabindex], div.ant-select-item, div.dropdown-item, input, select') || el;
                            const opts = {{ bubbles: true, cancelable: true, view: window, composed: true }};
                            try {{ target.dispatchEvent(new PointerEvent('pointerover', opts)); }} catch(e){{}}
                            try {{ target.dispatchEvent(new MouseEvent('mouseover', opts)); }} catch(e){{}}
                            try {{ target.dispatchEvent(new PointerEvent('pointerdown', opts)); }} catch(e){{}}
                            try {{ target.dispatchEvent(new MouseEvent('mousedown', opts)); }} catch(e){{}}
                            try {{ target.focus(); }} catch(e){{}}
                            try {{ target.dispatchEvent(new PointerEvent('pointerup', opts)); }} catch(e){{}}
                            try {{ target.dispatchEvent(new MouseEvent('mouseup', opts)); }} catch(e){{}}
                            try {{ target.click(); }} catch(e){{}}
                            try {{ target.dispatchEvent(new Event('change', {{ bubbles: true }})); }} catch(e){{}}
                            return true;
                        }}

                        let clicked = false;
                        const allNodes = Array.from(document.querySelectorAll('button, [role="button"], [role="option"], [role="menuitem"], [role="tab"], li, span, div, a, label'));
                        
                        // Strategy 1: Exact text match for "Yesterday" / "Kahapon"
                        const exactYest = allNodes.find(n => {{
                            if (n.closest('#__scraper_eod_wizard')) return false;
                            const txt = (n.innerText || n.textContent || '').trim().toLowerCase();
                            return txt === 'yesterday' || txt === 'kahapon';
                        }});

                        if (exactYest) {{
                            clicked = simulateClick(exactYest);
                        }} else {{
                            // Strategy 2: If no exact text, check selector if valid and not a wrong tab
                            if (yestSel) {{
                                try {{
                                    const yEl = document.querySelector(yestSel);
                                    if (yEl) {{
                                        const txt = (yEl.innerText || yEl.textContent || '').trim().toLowerCase();
                                        if (!txt.includes('7 day') && !txt.includes('today') && !txt.includes('30 day')) {{
                                            clicked = simulateClick(yEl);
                                        }}
                                    }}
                                }} catch(err) {{}}
                            }}

                            // Strategy 3: Partial text match
                            if (!clicked) {{
                                const partialYest = allNodes.find(n => {{
                                    if (n.closest('#__scraper_eod_wizard')) return false;
                                    const txt = (n.innerText || n.textContent || '').trim().toLowerCase();
                                    return txt.includes('yesterday') && n.children.length <= 2;
                                }});
                                if (partialYest) {{
                                    clicked = simulateClick(partialYest);
                                }}
                            }}
                        }}

                        // Check for Apply / Done button in popover
                        setTimeout(() => {{
                            const buttons = Array.from(document.querySelectorAll('button, [role="button"], .ant-btn-primary, .ant-picker-ok button'));
                            for (const b of buttons) {{
                                const t = (b.innerText || b.textContent || '').trim().toLowerCase();
                                if (['apply', 'apply filter', 'done', 'confirm', 'update', 'submit', 'ok'].includes(t)) {{
                                    simulateClick(b);
                                    break;
                                }}
                            }}
                        }}, 300);

                        return {{ yesterdayClicked: clicked }};
                    }}
                    """

                    try:
                        y_res = page.evaluate(js_click_yesterday, yesterday_sel)
                        if y_res and y_res.get("yesterdayClicked"):
                            self.log(f"[EOD Automation] Selected 'Yesterday' filter for [{store['name']}].", "INFO")
                        time.sleep(2.0)
                    except Exception as e:
                        self.log(f"Yesterday automation execution note for [{store['name']}]: {e}", "DEBUG")

                if self.stop_requested:
                    return {"store_id": store_id, "store_name": store["name"], "success": False, "raw_text": "Scrape Cancelled", "amount": 0.0, "is_eod": is_eod, "cancelled": True}

                result = self.extract_sales_from_page(page, store, is_eod=is_eod)
                last_result = result

                if result["success"] and result["amount"] > 0:
                    if attempt > 1:
                        self.log(f"[Force Scrape Recovered] [{store['name']}] recovered on attempt {attempt}: {result['raw_text']} (₱{result['amount']:,.2f})", "SUCCESS")
                    else:
                        self.log(f"[{store['name']}] Scraped: {result['raw_text']} ({result['method']})", "SUCCESS")
                    return result

                if not force_retry_on_zero:
                    return result

                if attempt < retries_limit:
                    time.sleep(1.0)
            except Exception as e:
                self.log(f"Error during attempt {attempt} for [{store['name']}]: {e}", "ERROR")
                time.sleep(1.0)

        if last_result:
            return last_result

        return {
            "store_id": store_id,
            "store_name": store["name"],
            "platform": store.get("platform", "grab"),
            "success": False,
            "raw_text": "Failed after forceful retries",
            "amount": 0.0,
            "is_eod": is_eod,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

    def scrape_branch(self, branch_id: str, is_eod: bool = False, on_store_scraped: Optional[Callable[[Dict[str, Any]], None]] = None) -> Dict[str, Any]:
        """Scrapes both Grab and Foodpanda for a specific branch with real-time per-store updates."""
        self.reset_stop()
        branch = next((b for b in self.config.get("branches", []) if b["id"] == branch_id), None)
        branch_name = branch["name"] if branch else branch_id
        mode_str = " (EOD Yesterday)" if is_eod else ""
        self.log(f"Scraping city: [{branch_name}]{mode_str} (Grab + Foodpanda)...", "INFO")

        grab_store_id = branch.get("grab_store_id") if branch else f"grab_{branch_id}"
        panda_store_id = branch.get("panda_store_id") if branch else f"panda_{branch_id}"

        grab_res = {}
        if grab_store_id and not self.stop_requested:
            grab_res = self.scrape_store(grab_store_id, is_eod=is_eod)
            if on_store_scraped and grab_res:
                try:
                    on_store_scraped(grab_res)
                except Exception as e:
                    self.log(f"Callback error: {e}", "WARNING")

        if not self.stop_requested:
            time.sleep(0.3)

        panda_res = {}
        if panda_store_id and not self.stop_requested:
            panda_res = self.scrape_store(panda_store_id, is_eod=is_eod)
            if on_store_scraped and panda_res:
                try:
                    on_store_scraped(panda_res)
                except Exception as e:
                    self.log(f"Callback error: {e}", "WARNING")

        grab_amt = grab_res.get("amount", 0.0) if grab_res else 0.0
        panda_amt = panda_res.get("amount", 0.0) if panda_res else 0.0
        branch_total = grab_amt + panda_amt

        if not self.stop_requested:
            self.log(f"[{branch_name}] Total: ₱{branch_total:,.2f} (Grab: ₱{grab_amt:,.2f} + Panda: ₱{panda_amt:,.2f})", "SUCCESS")

        return {
            "branch_id": branch_id,
            "branch_name": branch_name,
            "is_eod": is_eod,
            "grab_result": grab_res,
            "panda_result": panda_res,
            "grab_amount": grab_amt,
            "panda_amount": panda_amt,
            "branch_total": branch_total,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

    def scrape_all(self, is_eod: bool = False, on_store_scraped: Optional[Callable[[Dict[str, Any]], None]] = None) -> List[Dict[str, Any]]:
        """Scrapes all 4 merchant branches (8 stores total) with real-time per-store updates and writes to logs."""
        self.reset_stop()
        mode_label = "EOD (Yesterday's Sales)" if is_eod else "Live Operations (Today's Sales)"
        self.log(f"Starting full scrape across all 4 merchant hubs [{mode_label}]...", "INFO")
        results = []
        for store in self.config.get("stores", []):
            if self.stop_requested:
                self.log("[Scrape Aborted] Full scrape cancelled by user.", "WARNING")
                break
            res = self.scrape_store(store["id"], is_eod=is_eod)
            results.append(res)
            if on_store_scraped and res:
                try:
                    on_store_scraped(res)
                except Exception as e:
                    self.log(f"Callback error: {e}", "WARNING")
            if self.stop_requested:
                self.log("[Scrape Aborted] Full scrape cancelled by user.", "WARNING")
                break
            time.sleep(0.25)

        if not self.stop_requested and len(results) > 0:
            self.save_results_to_files(results, is_eod=is_eod)
        return results

    def save_results_to_files(self, results: List[Dict[str, Any]], is_eod: bool = False):
        """Appends formatted output grouped by the 4 Branches to TXT and CSV logs."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        txt_path = os.path.join(BASE_DIR, self.config.get("general", {}).get("txt_output_path", "sales_records.txt"))
        csv_path = os.path.join(BASE_DIR, self.config.get("general", {}).get("csv_output_path", "sales_records.csv"))

        total_sales = sum(r.get("amount", 0.0) for r in results)
        branches = self.config.get("branches", [])
        store_map = {r.get("store_id"): r for r in results}

        mode_header = "END OF DAY (EOD) SALES SUMMARY - YESTERDAY'S SALES" if is_eod else "LIVE SALES SUMMARY REPORT (4 CITIES / 8 STORES)"
        txt_lines = [
            "=" * 84,
            f"{mode_header}  |  Date: {timestamp}",
            "=" * 84,
        ]

        for branch in branches:
            bid = branch["id"]
            bname = branch["name"]
            grab_r = store_map.get(branch.get("grab_store_id"), {})
            panda_r = store_map.get(branch.get("panda_store_id"), {})
            
            g_amt = grab_r.get("amount", 0.0)
            p_amt = panda_r.get("amount", 0.0)
            b_total = g_amt + p_amt
            
            txt_lines.append(f"CITY: {bname.upper()}:")
            txt_lines.append(f"   ├─ [GRAB]      : ₱{g_amt:>10,.2f}  ({grab_r.get('raw_text', 'N/A')})")
            txt_lines.append(f"   ├─ [FOODPANDA] : ₱{p_amt:>10,.2f}  ({panda_r.get('raw_text', 'N/A')})")
            txt_lines.append(f"   └─ CITY TOTAL  : ₱{b_total:>10,.2f}")
            txt_lines.append("-" * 84)

        total_label = "GRAND COMBINED TOTAL (EOD YESTERDAY)" if is_eod else "GRAND COMBINED TOTAL (4 CITIES)"
        txt_lines.append(f"{total_label}: ₱ {total_sales:,.2f}")
        txt_lines.append("=" * 84 + "\n")

        try:
            with open(txt_path, "a", encoding="utf-8") as f:
                f.write("\n".join(txt_lines) + "\n")
            self.log(f"Sales appended to TXT log: {os.path.basename(txt_path)}", "INFO")
        except Exception as e:
            self.log(f"Error saving to TXT file: {e}", "ERROR")

        file_exists = os.path.exists(csv_path)
        status_tag = "EOD" if is_eod else "Live"
        try:
            with open(csv_path, "a", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                if not file_exists:
                    writer.writerow(["Timestamp", "Branch", "Store ID", "Store Name", "Platform", "Raw Text", "Parsed Amount", "Status", "Mode"])
                for r in results:
                    sid = r.get("store_id")
                    store_cfg = next((s for s in self.config.get("stores", []) if s["id"] == sid), {})
                    bid = store_cfg.get("branch_id", "")
                    writer.writerow([
                        timestamp,
                        bid,
                        sid,
                        r.get("store_name"),
                        r.get("platform"),
                        r.get("raw_text"),
                        r.get("amount", 0.0),
                        "Success" if r.get("success") else "Failed",
                        status_tag
                    ])
                writer.writerow([timestamp, "ALL_4_BRANCHES", "TOTAL_SUMMARY", f"GRAND COMBINED TOTAL ({status_tag})", "ALL", f"₱{total_sales:,.2f}", total_sales, "SUMMARY", status_tag])
        except Exception as e:
            self.log(f"Error saving to CSV file: {e}", "ERROR")

    def close_all(self):
        """Closes all browsers and shuts down Playwright engine."""
        self.log("Closing all browsers...", "INFO")
        for profile_id, ctx in list(self.contexts.items()):
            try:
                ctx.close()
            except Exception:
                pass
        self.contexts.clear()
        self.pages.clear()

        if self.playwright:
            try:
                self.playwright.stop()
            except Exception:
                pass
            self.playwright = None
        self.log("All browser sessions closed cleanly.", "INFO")
