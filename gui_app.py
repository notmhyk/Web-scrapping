import sys
import os
import queue
import time
from datetime import datetime
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGridLayout, QLabel, QPushButton, QSpinBox, QCheckBox, QTextEdit, QFrame,
    QDialog, QLineEdit, QFormLayout, QMessageBox, QScrollArea
)
from PyQt5.QtCore import Qt, QTimer, QThread, pyqtSignal
from PyQt5.QtGui import QFont, QColor

import json
from scraper_engine import ScraperEngine, CONFIG_FILE

EOD_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "eod_yesterday.json")

def is_eod_saved_for_today() -> bool:
    """Returns True if valid EOD data has already been recorded and saved for the current date."""
    if not os.path.exists(EOD_FILE):
        return False
    try:
        with open(EOD_FILE, "r", encoding="utf-8") as f:
            saved_eod = json.load(f)
        today_str = datetime.now().strftime("%Y-%m-%d")
        ts = str(saved_eod.get("timestamp", ""))
        eod_date = str(saved_eod.get("eod_date", ""))
        if today_str in ts or today_str in eod_date:
            stores = saved_eod.get("eod_stores", [])
            total = float(saved_eod.get("eod_total_sales", 0.0))
            if total > 0 or any(s.get("last_success") for s in stores):
                return True
    except Exception:
        pass
    return False

# Modern Dark Theme Stylesheet
DARK_THEME = """
QWidget {
    background-color: #0b0f19;
    color: #f1f5f9;
    font-family: 'Segoe UI', 'SF Pro Display', -apple-system, Roboto, sans-serif;
}

QScrollArea {
    background-color: transparent;
    border: none;
}

QFrame#HeaderFrame {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #1e293b, stop:1 #0f172a);
    border-bottom: 2px solid #334155;
    border-radius: 12px;
    padding: 10px 16px;
}

QFrame#PrimaryControlBar {
    background-color: #131b2e;
    border: 1px solid #1e293b;
    border-radius: 12px;
    padding: 8px 14px;
}

QFrame#ClockCard {
    background: rgba(15, 23, 42, 0.95);
    border: 1px solid rgba(56, 189, 248, 0.4);
    border-radius: 10px;
    padding: 4px 14px;
}

QFrame#TimerCard {
    background: rgba(15, 23, 42, 0.95);
    border: 1px solid rgba(16, 185, 129, 0.4);
    border-radius: 10px;
    padding: 4px 12px;
}

QFrame#SettingsFrame {
    background-color: #0f172a;
    border: 1px dashed #334155;
    border-radius: 10px;
    padding: 8px 14px;
}

QFrame#BranchCard {
    background-color: #131b2e;
    border: 1px solid #334155;
    border-radius: 14px;
    padding: 12px;
}
QFrame#BranchCard:hover {
    border: 1px solid #38bdf8;
    background-color: #17223b;
}

QFrame#BranchHeader {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #1e293b, stop:1 #0f172a);
    border: 1px solid #334155;
    border-radius: 8px;
    padding: 6px 12px;
}

QFrame#StoreSection {
    background-color: #0f172a;
    border: 1px solid #1e293b;
    border-radius: 10px;
    padding: 10px;
}
QFrame#StoreSection:hover {
    border: 1px solid #475569;
}

QFrame#SummaryCard {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #064e3b, stop:1 #0f172a);
    border: 2px solid #10b981;
    border-radius: 14px;
    padding: 12px 20px;
}

QPushButton {
    background-color: #334155;
    color: #f8fafc;
    border: 1px solid #475569;
    border-radius: 8px;
    padding: 7px 14px;
    font-weight: 600;
    font-size: 12px;
}
QPushButton:hover {
    background-color: #475569;
    border-color: #64748b;
}
QPushButton:pressed {
    background-color: #1e293b;
}

QPushButton#PrimaryBtn {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #2563eb, stop:1 #38bdf8);
    border: none;
    color: white;
    font-weight: bold;
    padding: 8px 16px;
}
QPushButton#PrimaryBtn:hover {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #1d4ed8, stop:1 #0284c7);
}

QPushButton#SuccessBtn {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #059669, stop:1 #10b981);
    border: none;
    color: white;
    font-weight: bold;
    padding: 8px 16px;
}
QPushButton#SuccessBtn:hover {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #047857, stop:1 #059669);
}

QPushButton#EodPrimaryBtn {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #7c3aed, stop:1 #a855f7);
    border: none;
    color: white;
    font-weight: bold;
    font-size: 12px;
    padding: 8px 16px;
    border-radius: 8px;
}
QPushButton#EodPrimaryBtn:hover {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #6d28d9, stop:1 #9333ea);
}
QPushButton#EodPrimaryBtn:pressed {
    background-color: #5b21b6;
}

QPushButton#EodTrainBtn {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #581c87, stop:1 #7e22ce);
    border: 1px solid #a855f7;
    color: #f3e8ff;
    padding: 5px 8px;
    font-size: 11px;
    font-weight: bold;
    border-radius: 6px;
}
QPushButton#EodTrainBtn:hover {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #6b21a8, stop:1 #9333ea);
    border-color: #c084fc;
}

QPushButton#DangerBtn {
    background-color: #dc2626;
    border: none;
    color: white;
    font-weight: bold;
    padding: 8px 16px;
}
QPushButton#DangerBtn:hover {
    background-color: #b91c1c;
}

QPushButton#SettingsToggleBtn {
    background-color: #1e293b;
    border: 1px solid #475569;
    color: #cbd5e1;
    border-radius: 8px;
    padding: 7px 12px;
    font-size: 12px;
    font-weight: bold;
}
QPushButton#SettingsToggleBtn:hover {
    background-color: #334155;
    border-color: #38bdf8;
    color: #38bdf8;
}

QPushButton#ActionCardBtn {
    background-color: #1e293b;
    border: 1px solid #475569;
    padding: 5px 8px;
    font-size: 11px;
    border-radius: 6px;
}
QPushButton#ActionCardBtn:hover {
    background-color: #334155;
    border-color: #38bdf8;
    color: #38bdf8;
}

QPushButton#TrainBtn {
    background-color: rgba(56, 189, 248, 0.15);
    border: 1px solid rgba(56, 189, 248, 0.4);
    color: #38bdf8;
    padding: 5px 8px;
    font-size: 11px;
    border-radius: 6px;
    font-weight: bold;
}
QPushButton#TrainBtn:hover {
    background-color: rgba(56, 189, 248, 0.3);
    color: white;
}

QPushButton#MiniScrapeBtn {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #059669, stop:1 #10b981);
    border: none;
    color: white;
    padding: 4px 10px;
    font-size: 11px;
    font-weight: bold;
    border-radius: 6px;
}
QPushButton#MiniScrapeBtn:hover {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #047857, stop:1 #059669);
}

QPushButton#EodMiniScrapeBtn {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #7c3aed, stop:1 #9333ea);
    border: none;
    color: white;
    padding: 4px 10px;
    font-size: 11px;
    font-weight: bold;
    border-radius: 6px;
}
QPushButton#EodMiniScrapeBtn:hover {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #6d28d9, stop:1 #7c3aed);
}

QSpinBox {
    background-color: #1e293b;
    border: 1px solid #475569;
    border-radius: 6px;
    padding: 3px 6px;
    color: #38bdf8;
    font-size: 12px;
    font-weight: bold;
}

QCheckBox {
    color: #cbd5e1;
    font-size: 12px;
    font-weight: 600;
}
QCheckBox::indicator {
    width: 15px;
    height: 15px;
    border-radius: 4px;
    border: 1px solid #475569;
    background-color: #1e293b;
}
QCheckBox::indicator:checked {
    background-color: #10b981;
    border-color: #10b981;
}

QTextEdit#ConsoleBox {
    background-color: #090d16;
    border: 1px solid #1e293b;
    border-radius: 8px;
    color: #94a3b8;
    font-family: 'Consolas', 'Courier New', monospace;
    font-size: 11px;
    padding: 6px 10px;
}

QScrollBar:vertical {
    border: none;
    background: #0f172a;
    width: 7px;
    border-radius: 4px;
}
QScrollBar::handle:vertical {
    background: #334155;
    min-height: 20px;
    border-radius: 4px;
}
QScrollBar::handle:vertical:hover {
    background: #475569;
}
"""

class PersistentWorkerThread(QThread):
    log_signal = pyqtSignal(str, str)
    scrape_all_signal = pyqtSignal(list)
    scrape_single_signal = pyqtSignal(dict)
    training_finished_signal = pyqtSignal(str, str, str)
    multi_train_finished_signal = pyqtSignal(str, int, float)
    browser_ready_signal = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.task_queue = queue.Queue()
        self._running = True
        self.engine = None

    def enqueue_task(self, task_type: str, **kwargs):
        self.task_queue.put((task_type, kwargs))

    def stop(self):
        self._running = False
        self.task_queue.put(("STOP", {}))

    def cancel_current_task(self):
        """Signals ScraperEngine to immediately abort ongoing scrape and clears queued tasks."""
        if self.engine:
            self.engine.request_stop()
        while not self.task_queue.empty():
            try:
                self.task_queue.get_nowait()
                self.task_queue.task_done()
            except Exception:
                pass

    def run(self):
        self.engine = ScraperEngine(
            config_path=CONFIG_FILE,
            log_callback=lambda msg, level: self.log_signal.emit(msg, level)
        )

        while self._running:
            try:
                task_type, args = self.task_queue.get(timeout=0.5)
            except queue.Empty:
                continue

            if task_type == "STOP":
                break

            try:
                if task_type == "launch_all":
                    self.engine.launch_all_browsers()
                    self.browser_ready_signal.emit("all")
                elif task_type == "launch_single":
                    profile_id = args.get("profile_id", "grab_1")
                    self.engine.launch_profile_browser(profile_id, focus_url=True)
                    self.browser_ready_signal.emit(profile_id)
                elif task_type == "scrape_all":
                    self.engine.reset_stop()
                    results = self.engine.scrape_all(is_eod=False, on_store_scraped=lambda res: self.scrape_single_signal.emit(res))
                    self.scrape_all_signal.emit(results)
                elif task_type == "scrape_eod":
                    self.engine.reset_stop()
                    results = self.engine.scrape_all(is_eod=True, on_store_scraped=lambda res: self.scrape_single_signal.emit(res))
                    self.scrape_all_signal.emit(results)
                elif task_type == "scrape_single":
                    self.engine.reset_stop()
                    store_id = args.get("store_id")
                    is_eod = args.get("is_eod", False)
                    res = self.engine.scrape_store(store_id, is_eod=is_eod)
                    self.scrape_single_signal.emit(res)
                elif task_type == "scrape_branch":
                    self.engine.reset_stop()
                    branch_id = args.get("branch_id")
                    is_eod = args.get("is_eod", False)
                    if branch_id:
                        b_res = self.engine.scrape_branch(branch_id, is_eod=is_eod, on_store_scraped=lambda res: self.scrape_single_signal.emit(res))
                    else:
                        grab_id = args.get("grab_id")
                        panda_id = args.get("panda_id")
                        if grab_id and not self.engine.stop_requested:
                            res_grab = self.engine.scrape_store(grab_id, is_eod=is_eod)
                            self.scrape_single_signal.emit(res_grab)
                        if panda_id and not self.engine.stop_requested:
                            res_panda = self.engine.scrape_store(panda_id, is_eod=is_eod)
                            self.scrape_single_signal.emit(res_panda)
                elif task_type == "train_single":
                    store_id = args.get("store_id")

                    def on_single_found(sel, sample_text):
                        self.training_finished_signal.emit(store_id, sel, sample_text)

                    self.engine.train_single_picker(store_id, is_eod=False, on_selector_found=on_single_found)
                elif task_type == "train_eod":
                    store_id = args.get("store_id")

                    def on_eod_found(sel, sample_text):
                        self.training_finished_signal.emit(store_id, sel, sample_text)

                    self.engine.train_eod_wizard(store_id, on_complete=on_eod_found)
                elif task_type == "train_multi":
                    store_id = args.get("store_id")

                    def on_multi_done(selectors, total_sum, count):
                        self.multi_train_finished_signal.emit(store_id, count, total_sum)

                    self.engine.train_multi_picker(store_id, on_complete=on_multi_done)
                elif task_type == "update_settings":
                    general_cfg = args.get("general", {})
                    self.engine.config.setdefault("general", {}).update(general_cfg)
                    self.engine.save_config()
                elif task_type == "save_config":
                    self.engine.save_config()
                elif task_type == "reload_config":
                    self.engine.config = self.engine.load_config()
            except Exception as e:
                self.log_signal.emit(f"Task '{task_type}' error: {e}", "ERROR")
            finally:
                self.task_queue.task_done()

        if self.engine:
            try:
                self.engine.close_all()
            except Exception:
                pass


class StoreConfigDialog(QDialog):
    def __init__(self, store: dict, parent=None):
        super().__init__(parent)
        self.store = store
        self.setWindowTitle(f"Configure: {store.get('name', 'Store')}")
        self.setMinimumWidth(520)
        self.setStyleSheet(DARK_THEME)

        layout = QVBoxLayout(self)
        layout.setSpacing(14)

        title = QLabel(f"Settings for {store.get('name', 'Store')}")
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #38bdf8;")
        layout.addWidget(title)

        form = QFormLayout()
        self.name_edit = QLineEdit(store.get("name", ""))
        self.name_edit.setStyleSheet("background-color: #1e293b; padding: 6px; border: 1px solid #475569; border-radius: 6px;")
        
        self.url_edit = QLineEdit(store.get("url", ""))
        self.url_edit.setStyleSheet("background-color: #1e293b; padding: 6px; border: 1px solid #475569; border-radius: 6px;")
        
        form.addRow("Store Name:", self.name_edit)
        form.addRow("Live Portal URL:", self.url_edit)

        is_grab = store.get("platform") == "grab"
        multi_sels = store.get("multi_selectors", [])

        if is_grab:
            self.eod_url_edit = QLineEdit(store.get("eod_url", ""))
            self.eod_url_edit.setPlaceholderText("https://merchant.grab.com/finances?page=tx&startDate={YESTERDAY_DATE}&endDate={YESTERDAY_DATE}")
            self.eod_url_edit.setStyleSheet("background-color: #1e293b; padding: 6px; border: 1px solid #475569; border-radius: 6px;")
            form.addRow("EOD URL (Yesterday):", self.eod_url_edit)

        if multi_sels or "expected_count" in store:
            self.count_info = QLabel(f"{len(multi_sels)} selectors currently configured")
            self.count_info.setStyleSheet("color: #10b981; font-weight: bold;")
            form.addRow("Trained Stores:", self.count_info)
        else:
            self.selector_edit = QLineEdit(store.get("selector", ""))
            self.selector_edit.setPlaceholderText("e.g. #sales-total (Live Operation selector)")
            self.selector_edit.setStyleSheet("background-color: #1e293b; padding: 6px; border: 1px solid #475569; border-radius: 6px;")
            form.addRow("Live CSS Selector:", self.selector_edit)

            if is_grab:
                self.eod_selector_edit = QLineEdit(store.get("eod_selector", ""))
                self.eod_selector_edit.setPlaceholderText("e.g. EOD selector (or click Train EOD on dashboard)")
                self.eod_selector_edit.setStyleSheet("background-color: #1e293b; padding: 6px; border: 1px solid #475569; border-radius: 6px;")
                form.addRow("EOD CSS Selector:", self.eod_selector_edit)

        layout.addLayout(form)

        tip = QLabel("Tip: Use the 'Train' or 'Train EOD' buttons on the dashboard to click and train elements directly on the webpage.")
        tip.setStyleSheet("color: #94a3b8; font-size: 11px;")
        tip.setWordWrap(True)
        layout.addWidget(tip)

        btn_box = QHBoxLayout()
        save_btn = QPushButton("Save Settings", self)
        save_btn.setObjectName("SuccessBtn")
        save_btn.clicked.connect(self.save_and_close)
        
        cancel_btn = QPushButton("Cancel", self)
        cancel_btn.clicked.connect(self.reject)
        
        btn_box.addStretch()
        btn_box.addWidget(cancel_btn)
        btn_box.addWidget(save_btn)
        layout.addLayout(btn_box)

    def save_and_close(self):
        self.store["name"] = self.name_edit.text().strip()
        self.store["url"] = self.url_edit.text().strip()
        if hasattr(self, 'eod_url_edit'):
            self.store["eod_url"] = self.eod_url_edit.text().strip()
        if hasattr(self, 'selector_edit'):
            self.store["selector"] = self.selector_edit.text().strip()
        if hasattr(self, 'eod_selector_edit'):
            self.store["eod_selector"] = self.eod_selector_edit.text().strip()
        self.accept()


class StoreSubWidget(QFrame):
    train_single_requested = pyqtSignal(str)
    train_eod_requested = pyqtSignal(str)
    train_multi_requested = pyqtSignal(str)
    open_browser_requested = pyqtSignal(str)
    scrape_store_requested = pyqtSignal(str)
    scrape_store_eod_requested = pyqtSignal(str)
    config_store_requested = pyqtSignal(str)

    def __init__(self, store: dict, parent=None):
        super().__init__(parent)
        self.store = store
        self.setObjectName("StoreSection")
        self.last_amount = float(store.get("last_amount", 0.0))
        self.init_ui()

    def is_multi_mode(self) -> bool:
        return bool(self.store.get("platform") == "grab" and (self.store.get("expected_count") or self.store.get("multi_selectors")))

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(5)

        is_grab = self.store.get("platform") == "grab"
        is_multi = self.is_multi_mode()
        badge_color = "#059669" if is_grab else "#e11d48"
        badge_text = "GRAB" if is_grab else "FOODPANDA"

        # Top line: Badge + Name + Status Pill
        header_h = QHBoxLayout()
        header_h.setSpacing(6)

        self.badge_lbl = QLabel(badge_text)
        self.badge_lbl.setStyleSheet(f"background-color: {badge_color}; color: white; padding: 2px 6px; border-radius: 4px; font-size: 10px; font-weight: bold;")
        
        self.title_lbl = QLabel(self.store.get("name", "Store"))
        self.title_lbl.setStyleSheet("font-size: 13px; font-weight: 700; color: #f8fafc;")
        
        self.status_pill = QLabel("Idle")
        self.status_pill.setStyleSheet("font-size: 11px; color: #94a3b8;")

        header_h.addWidget(self.badge_lbl)
        header_h.addWidget(self.title_lbl)
        header_h.addStretch()
        header_h.addWidget(self.status_pill)
        layout.addLayout(header_h)

        # Sales Value
        self.sales_val_lbl = QLabel(f"₱ {self.last_amount:,.2f}")
        self.sales_val_lbl.setStyleSheet("font-size: 20px; font-weight: 800; color: #10b981; margin: 1px 0;")
        layout.addWidget(self.sales_val_lbl)

        # Subtext / Info
        trained_count = len(self.store.get("multi_selectors", []))
        if is_multi:
            init_info = f"Trained: {trained_count} stores" if trained_count > 0 else f"Target: {self.store.get('expected_count', 30)} stores"
        else:
            init_info = "Status: Not scraped yet"
        
        self.info_lbl = QLabel(init_info)
        self.info_lbl.setStyleSheet("font-size: 11px; color: #94a3b8;")
        self.info_lbl.setWordWrap(True)
        self.info_lbl.setFixedHeight(22)
        layout.addWidget(self.info_lbl)

        # Action Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(4)

        if is_multi:
            exp_count = self.store.get("expected_count", "")
            btn_label = f"Train ({exp_count})" if exp_count else "Multi-Train"
            self.train_btn = QPushButton(btn_label)
            self.train_btn.setObjectName("TrainBtn")
            self.train_btn.setToolTip(f"Train multi-store selectors ({exp_count} stores)")
            self.train_btn.clicked.connect(lambda: self.train_multi_requested.emit(self.store["id"]))
            btn_layout.addWidget(self.train_btn)

            if is_grab:
                self.train_eod_btn = QPushButton("Train EOD")
                self.train_eod_btn.setObjectName("EodTrainBtn")
                self.train_eod_btn.setToolTip("Train Yesterday's EOD 3-Step workflow (30 Stores + San Fernando Balance)")
                self.train_eod_btn.clicked.connect(lambda: self.train_eod_requested.emit(self.store["id"]))
                btn_layout.addWidget(self.train_eod_btn)
        elif is_grab:
            self.train_btn = QPushButton("Train")
            self.train_btn.setObjectName("TrainBtn")
            self.train_btn.setToolTip("Train Live Operation sales selector")
            self.train_btn.clicked.connect(lambda: self.train_single_requested.emit(self.store["id"]))
            btn_layout.addWidget(self.train_btn)

            self.train_eod_btn = QPushButton("Train EOD")
            self.train_eod_btn.setObjectName("EodTrainBtn")
            self.train_eod_btn.setToolTip("Train Yesterday's EOD Finances selector")
            self.train_eod_btn.clicked.connect(lambda: self.train_eod_requested.emit(self.store["id"]))
            btn_layout.addWidget(self.train_eod_btn)
        else:
            self.train_btn = QPushButton("Train")
            self.train_btn.setObjectName("TrainBtn")
            self.train_btn.setToolTip("Click directly on sales element inside browser")
            self.train_btn.clicked.connect(lambda: self.train_single_requested.emit(self.store["id"]))
            btn_layout.addWidget(self.train_btn)

            self.train_eod_btn = QPushButton("Train EOD")
            self.train_eod_btn.setObjectName("EodTrainBtn")
            self.train_eod_btn.setToolTip("Train Foodpanda Yesterday's EOD 3-Step workflow")
            self.train_eod_btn.clicked.connect(lambda: self.train_eod_requested.emit(self.store["id"]))
            btn_layout.addWidget(self.train_eod_btn)

        profile_id = self.store.get("profile_id", self.store["id"])
        self.browser_btn = QPushButton("View")
        self.browser_btn.setObjectName("ActionCardBtn")
        self.browser_btn.setToolTip("Focus this browser window")
        self.browser_btn.clicked.connect(lambda: self.open_browser_requested.emit(profile_id))

        self.scrape_btn = QPushButton("Scrape")
        self.scrape_btn.setObjectName("ActionCardBtn")
        self.scrape_btn.setToolTip("Scrape this portal (Live)")
        self.scrape_btn.clicked.connect(lambda: self.scrape_store_requested.emit(self.store["id"]))

        self.scrape_eod_btn = QPushButton("Scrape EOD")
        self.scrape_eod_btn.setObjectName("EodMiniScrapeBtn")
        self.scrape_eod_btn.setToolTip("Scrape yesterday's EOD sales for this portal")
        self.scrape_eod_btn.clicked.connect(lambda: self.scrape_store_eod_requested.emit(self.store["id"]))

        self.edit_btn = QPushButton("Edit")
        self.edit_btn.setObjectName("ActionCardBtn")
        self.edit_btn.setToolTip("Configure settings")
        self.edit_btn.clicked.connect(lambda: self.config_store_requested.emit(self.store["id"]))

        btn_layout.addWidget(self.browser_btn)
        btn_layout.addWidget(self.scrape_btn)
        btn_layout.addWidget(self.scrape_eod_btn)
        btn_layout.addWidget(self.edit_btn)
        layout.addLayout(btn_layout)

    def update_data(self, result: dict):
        amt = result.get("amount", 0.0)
        self.last_amount = amt
        raw_text = str(result.get("raw_text", ""))
        display_raw = (raw_text[:34] + "...") if len(raw_text) > 36 else raw_text
        is_eod = result.get("is_eod", False)

        if result.get("success") and amt > 0:
            self.sales_val_lbl.setText(f"₱ {amt:,.2f}")
            self.sales_val_lbl.setStyleSheet("font-size: 20px; font-weight: 800; color: #10b981; margin: 1px 0;")
            self.status_pill.setText("EOD Active" if is_eod else "Active")
            self.status_pill.setStyleSheet(f"font-size: 11px; color: {'#c084fc' if is_eod else '#10b981'}; font-weight: bold;")
            self.info_lbl.setText(f"{'[EOD] ' if is_eod else ''}Extracted: '{display_raw}'")
        else:
            self.sales_val_lbl.setText(f"₱ {amt:,.2f}")
            self.sales_val_lbl.setStyleSheet("font-size: 20px; font-weight: 800; color: #ef4444; margin: 1px 0;")
            self.status_pill.setText("0 / Check")
            self.status_pill.setStyleSheet("font-size: 11px; color: #ef4444; font-weight: bold;")
            self.info_lbl.setText(f"Status: {display_raw or '0.00'}")


class BranchCardWidget(QFrame):
    scrape_branch_requested = pyqtSignal(str, str)
    scrape_branch_eod_requested = pyqtSignal(str, str)
    train_single_requested = pyqtSignal(str)
    train_eod_requested = pyqtSignal(str)
    train_multi_requested = pyqtSignal(str)
    open_browser_requested = pyqtSignal(str)
    scrape_store_requested = pyqtSignal(str)
    scrape_store_eod_requested = pyqtSignal(str)
    config_store_requested = pyqtSignal(str)

    def __init__(self, branch: dict, grab_store: dict, panda_store: dict, parent=None):
        super().__init__(parent)
        self.branch = branch
        self.grab_store = grab_store
        self.panda_store = panda_store
        self.setObjectName("BranchCard")
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(10)

        # 1. Branch Header Bar
        header_frame = QFrame()
        header_frame.setObjectName("BranchHeader")
        h_layout = QHBoxLayout(header_frame)
        h_layout.setContentsMargins(8, 6, 8, 6)
        h_layout.setSpacing(8)

        branch_name_clean = self.branch.get("name", "Branch").replace("Branch", "").strip()
        self.title_lbl = QLabel(branch_name_clean)
        self.title_lbl.setStyleSheet("font-size: 15px; font-weight: 800; color: #f8fafc;")

        self.branch_total_lbl = QLabel("₱ 0.00")
        self.branch_total_lbl.setStyleSheet("font-size: 16px; font-weight: 900; color: #34d399;")

        self.scrape_city_btn = QPushButton("Scrape")
        self.scrape_city_btn.setObjectName("MiniScrapeBtn")
        self.scrape_city_btn.setToolTip(f"Scrape live sales for {branch_name_clean} (Grab + Foodpanda)")
        self.scrape_city_btn.clicked.connect(self.on_scrape_city_clicked)

        self.scrape_city_eod_btn = QPushButton("Scrape EOD")
        self.scrape_city_eod_btn.setObjectName("EodMiniScrapeBtn")
        self.scrape_city_eod_btn.setToolTip(f"Scrape yesterday's EOD sales for {branch_name_clean} (Grab + Foodpanda)")
        self.scrape_city_eod_btn.clicked.connect(self.on_scrape_city_eod_clicked)

        h_layout.addWidget(self.title_lbl)
        h_layout.addStretch()
        h_layout.addWidget(self.branch_total_lbl)
        h_layout.addWidget(self.scrape_city_btn)
        h_layout.addWidget(self.scrape_city_eod_btn)
        layout.addWidget(header_frame)

        # 2. Stores Layout (Grab on top, Panda below inside the branch card)
        stores_layout = QVBoxLayout()
        stores_layout.setSpacing(8)

        self.grab_sub = StoreSubWidget(self.grab_store, self)
        self.grab_sub.train_single_requested.connect(self.train_single_requested.emit)
        self.grab_sub.train_eod_requested.connect(self.train_eod_requested.emit)
        self.grab_sub.train_multi_requested.connect(self.train_multi_requested.emit)
        self.grab_sub.open_browser_requested.connect(self.open_browser_requested.emit)
        self.grab_sub.scrape_store_requested.connect(self.scrape_store_requested.emit)
        self.grab_sub.scrape_store_eod_requested.connect(self.scrape_store_eod_requested.emit)
        self.grab_sub.config_store_requested.connect(self.config_store_requested.emit)
        stores_layout.addWidget(self.grab_sub)

        self.panda_sub = StoreSubWidget(self.panda_store, self)
        self.panda_sub.train_single_requested.connect(self.train_single_requested.emit)
        self.panda_sub.train_eod_requested.connect(self.train_eod_requested.emit)
        self.panda_sub.train_multi_requested.connect(self.train_multi_requested.emit)
        self.panda_sub.open_browser_requested.connect(self.open_browser_requested.emit)
        self.panda_sub.scrape_store_requested.connect(self.scrape_store_requested.emit)
        self.panda_sub.scrape_store_eod_requested.connect(self.scrape_store_eod_requested.emit)
        self.panda_sub.config_store_requested.connect(self.config_store_requested.emit)
        stores_layout.addWidget(self.panda_sub)

        layout.addLayout(stores_layout)
        self.recalc_branch_total()

    def on_scrape_city_clicked(self):
        grab_id = self.grab_store.get("id", "")
        panda_id = self.panda_store.get("id", "")
        self.scrape_branch_requested.emit(grab_id, panda_id)

    def on_scrape_city_eod_clicked(self):
        grab_id = self.grab_store.get("id", "")
        panda_id = self.panda_store.get("id", "")
        self.scrape_branch_eod_requested.emit(grab_id, panda_id)

    def recalc_branch_total(self):
        total = self.grab_sub.last_amount + self.panda_sub.last_amount
        self.branch_total_lbl.setText(f"₱ {total:,.2f}")
        return total


class SalesScraperApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Multi-Store Sales Dashboard (4 Consolidated City Branches)")
        self.setMinimumSize(1240, 900)
        self.setStyleSheet(DARK_THEME)

        self.init_config = ScraperEngine().load_config()

        self.worker = PersistentWorkerThread()
        self.worker.log_signal.connect(self.on_log_received)
        self.worker.scrape_all_signal.connect(self.on_scrape_all_finished)
        self.worker.scrape_single_signal.connect(self.on_single_scrape_finished)
        self.worker.training_finished_signal.connect(self.on_training_finished)
        self.worker.multi_train_finished_signal.connect(self.on_multi_train_finished)
        self.worker.start()

        self.auto_timer = QTimer(self)
        self.auto_timer.timeout.connect(self.on_timer_tick)
        self.countdown_seconds = 0
        self.is_auto_running = False
        self.executed_eod_slots = set()

        # Live Clock Timer (updates Date and Time every 1s & triggers 12 AM / 1 AM EOD)
        self.clock_timer = QTimer(self)
        self.clock_timer.timeout.connect(self.update_live_clock)
        self.clock_timer.start(1000)

        self.branch_cards: dict = {}
        self.store_to_branch: dict = {}

        self.init_ui()
        self.update_live_clock()
        self.log_message("System ready. 4 City Branches configured (Angeles, Quezon City, Caloocan, San Fernando).", "INFO")

    def init_ui(self):
        central = QWidget(self)
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(16, 12, 16, 12)
        main_layout.setSpacing(10)

        # 1. TOP HEADER FRAME (With Title, Subtitle, and Launch Browsers button)
        header_frame = QFrame()
        header_frame.setObjectName("HeaderFrame")
        h_layout = QHBoxLayout(header_frame)
        h_layout.setContentsMargins(12, 6, 12, 6)
        h_layout.setSpacing(16)

        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        title = QLabel("Multi-Store Sales Dashboard")
        title.setStyleSheet("font-size: 20px; font-weight: 800; color: #38bdf8;")
        subtitle = QLabel("Angeles City • Quezon City • Caloocan City • San Fernando City (4 Grab + 4 Foodpanda Portals)")
        subtitle.setStyleSheet("font-size: 11px; color: #94a3b8;")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        h_layout.addLayout(title_box)

        h_layout.addStretch()

        self.launch_browsers_btn = QPushButton("Launch 8 Browsers")
        self.launch_browsers_btn.setObjectName("PrimaryBtn")
        self.launch_browsers_btn.setToolTip("Open all 8 persistent browser windows in a 2x4 screen grid (4 Grab Top, 4 Panda Bottom)")
        self.launch_browsers_btn.clicked.connect(self.launch_all_browsers)
        h_layout.addWidget(self.launch_browsers_btn)

        main_layout.addWidget(header_frame)

        # 2. DEFAULT VISIBLE CONTROL BAR (Directly above the 4 branches)
        # On default: ONLY Scrape all 4 cities, Auto Scraping, Next Scrape Timer, Date and Time, and Settings toggle
        primary_control_bar = QFrame()
        primary_control_bar.setObjectName("PrimaryControlBar")
        pc_layout = QHBoxLayout(primary_control_bar)
        pc_layout.setContentsMargins(10, 6, 10, 6)
        pc_layout.setSpacing(12)

        # Action 1: Scrape All 4 Cities
        self.scrape_now_btn = QPushButton("Scrape All 4 Cities")
        self.scrape_now_btn.setObjectName("PrimaryBtn")
        self.scrape_now_btn.clicked.connect(self.trigger_scrape_now)
        pc_layout.addWidget(self.scrape_now_btn)

        # Stop Scraping Button
        self.stop_scrape_btn = QPushButton("Stop Scraping")
        self.stop_scrape_btn.setObjectName("DangerBtn")
        self.stop_scrape_btn.setToolTip("Immediately cancel any ongoing live or EOD scrape")
        self.stop_scrape_btn.clicked.connect(self.trigger_stop_scraping)
        pc_layout.addWidget(self.stop_scrape_btn)

        # Action 2: Auto Scraping
        self.toggle_auto_btn = QPushButton("Start Auto-Scraping")
        self.toggle_auto_btn.setObjectName("SuccessBtn")
        self.toggle_auto_btn.clicked.connect(self.toggle_auto_scraping)
        pc_layout.addWidget(self.toggle_auto_btn)

        # Action 2b: EOD Button (Placed alongside Auto Scraping)
        self.eod_btn = QPushButton("EOD")
        self.eod_btn.setObjectName("EodPrimaryBtn")
        self.eod_btn.setToolTip("Scrape yesterday's End of Day (EOD) sales across all 4 cities")
        self.eod_btn.clicked.connect(self.trigger_scrape_eod)
        pc_layout.addWidget(self.eod_btn)

        pc_layout.addStretch(1)

        # Action 3: Prominent Date and Time Card (Centered on Screen: Date on top, Time below)
        clock_frame = QFrame()
        clock_frame.setObjectName("ClockCard")
        clock_layout = QVBoxLayout(clock_frame)
        clock_layout.setContentsMargins(16, 3, 16, 3)
        clock_layout.setSpacing(1)

        self.live_date_lbl = QLabel("Date Loading...")
        self.live_date_lbl.setAlignment(Qt.AlignCenter)
        self.live_date_lbl.setStyleSheet("font-size: 11.5px; font-weight: 600; color: #94a3b8;")

        self.live_time_lbl = QLabel("00:00:00 AM")
        self.live_time_lbl.setAlignment(Qt.AlignCenter)
        self.live_time_lbl.setStyleSheet("font-size: 16px; font-weight: 900; color: #38bdf8; font-family: 'Consolas', monospace;")

        clock_layout.addWidget(self.live_date_lbl)
        clock_layout.addWidget(self.live_time_lbl)
        pc_layout.addWidget(clock_frame)

        pc_layout.addStretch(1)

        # Action 4: Next Scrape Timer Badge (Positioned beside Settings button)
        timer_card = QFrame()
        timer_card.setObjectName("TimerCard")
        t_card_layout = QHBoxLayout(timer_card)
        t_card_layout.setContentsMargins(8, 4, 8, 4)
        t_card_layout.setSpacing(6)
        
        self.countdown_lbl = QLabel("Next Scrape: Stopped")
        self.countdown_lbl.setStyleSheet("color: #10b981; font-size: 13px; font-weight: 800; min-width: 140px;")
        t_card_layout.addWidget(self.countdown_lbl)
        pc_layout.addWidget(timer_card)

        # Action 5: Collapsible Settings Toggle Button
        self.toggle_settings_btn = QPushButton("Settings")
        self.toggle_settings_btn.setObjectName("SettingsToggleBtn")
        self.toggle_settings_btn.setToolTip("Show/hide interval, grab delay, panda delay, retries, and log file controls")
        self.toggle_settings_btn.clicked.connect(self.toggle_settings_panel)
        pc_layout.addWidget(self.toggle_settings_btn)

        main_layout.addWidget(primary_control_bar)

        # 3. COLLAPSIBLE SETTINGS FRAME (Hidden/Collapsed by default)
        self.settings_frame = QFrame()
        self.settings_frame.setObjectName("SettingsFrame")
        self.settings_frame.setVisible(False)  # Collapsed by default!
        s_layout = QHBoxLayout(self.settings_frame)
        s_layout.setContentsMargins(10, 6, 10, 6)
        s_layout.setSpacing(12)

        s_layout.addWidget(QLabel("Interval (min):"))
        self.interval_spin = QSpinBox()
        self.interval_spin.setRange(1, 120)
        self.interval_spin.setValue(self.init_config.get("general", {}).get("interval_minutes", 1))
        self.interval_spin.valueChanged.connect(self.on_settings_changed)
        s_layout.addWidget(self.interval_spin)

        s_layout.addWidget(QLabel("Grab Wait (s):"))
        self.grab_wait_spin = QSpinBox()
        self.grab_wait_spin.setRange(1, 30)
        self.grab_wait_spin.setValue(self.init_config.get("general", {}).get("refresh_wait_seconds", 5))
        self.grab_wait_spin.valueChanged.connect(self.on_settings_changed)
        s_layout.addWidget(self.grab_wait_spin)

        s_layout.addWidget(QLabel("Panda Wait (s):"))
        self.panda_wait_spin = QSpinBox()
        self.panda_wait_spin.setRange(5, 60)
        self.panda_wait_spin.setValue(self.init_config.get("general", {}).get("panda_refresh_wait_seconds", 10))
        self.panda_wait_spin.valueChanged.connect(self.on_settings_changed)
        s_layout.addWidget(self.panda_wait_spin)

        self.force_retry_chk = QCheckBox("Force Retry on 0")
        self.force_retry_chk.setChecked(self.init_config.get("general", {}).get("force_retry_on_zero", True))
        self.force_retry_chk.setToolTip("Forcefully reload and retry if a branch sales returns 0 or fails")
        self.force_retry_chk.stateChanged.connect(self.on_settings_changed)
        s_layout.addWidget(self.force_retry_chk)

        s_layout.addWidget(QLabel("Retries:"))
        self.retries_spin = QSpinBox()
        self.retries_spin.setRange(1, 10)
        self.retries_spin.setValue(self.init_config.get("general", {}).get("max_retries", 3))
        self.retries_spin.valueChanged.connect(self.on_settings_changed)
        s_layout.addWidget(self.retries_spin)

        s_layout.addStretch()

        self.open_txt_btn = QPushButton("TXT Log")
        self.open_txt_btn.clicked.connect(self.open_txt_log)
        s_layout.addWidget(self.open_txt_btn)

        self.open_csv_btn = QPushButton("CSV Log")
        self.open_csv_btn.clicked.connect(self.open_csv_log)
        s_layout.addWidget(self.open_csv_btn)

        main_layout.addWidget(self.settings_frame)

        # 4. 4 BRANCHES GRID (2x2 Layout: Angeles Top-Left, Quezon City Top-Right, Caloocan Bottom-Left, San Fernando Bottom-Right)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(0, 0, 0, 0)
        scroll_layout.setSpacing(10)

        grid_layout = QGridLayout()
        grid_layout.setSpacing(12)

        stores_map = {s["id"]: s for s in self.init_config.get("stores", [])}
        branches = self.init_config.get("branches", [
            {"id": "angeles", "name": "Angeles City Branch", "grab_store_id": "grab_1", "panda_store_id": "panda_1"},
            {"id": "qc", "name": "Quezon City Branch", "grab_store_id": "grab_2", "panda_store_id": "panda_2"},
            {"id": "caloocan", "name": "Caloocan City Branch", "grab_store_id": "grab_3_caloocan", "panda_store_id": "panda_3"},
            {"id": "san_fernando", "name": "San Fernando City Branch", "grab_store_id": "grab_4_san_fernando", "panda_store_id": "panda_4"}
        ])

        # Strict 2x2 Grid Mapping:
        # Row 0: Left -> Angeles (0,0), Right -> Quezon City (0,1)
        # Row 1: Left -> Caloocan (1,0), Right -> San Fernando (1,1)
        grid_pos_map = {
            "angeles": (0, 0),
            "qc": (0, 1),
            "caloocan": (1, 0),
            "san_fernando": (1, 1)
        }

        for idx, branch in enumerate(branches):
            b_id = branch["id"]
            grab_id = branch.get("grab_store_id", f"grab_{idx+1}")
            panda_id = branch.get("panda_store_id", f"panda_{idx+1}")

            grab_store = stores_map.get(grab_id, {"id": grab_id, "name": f"{branch.get('name')} (Grab)", "platform": "grab", "last_amount": 0.0})
            panda_store = stores_map.get(panda_id, {"id": panda_id, "name": f"{branch.get('name')} (Foodpanda)", "platform": "foodpanda", "last_amount": 0.0})

            card = BranchCardWidget(branch, grab_store, panda_store, self)
            card.scrape_branch_requested.connect(self.on_scrape_branch_requested)
            card.scrape_branch_eod_requested.connect(self.on_scrape_branch_eod_requested)
            card.train_single_requested.connect(self.on_train_single_requested)
            card.train_eod_requested.connect(self.on_train_eod_requested)
            card.train_multi_requested.connect(self.on_train_multi_requested)
            card.open_browser_requested.connect(self.on_open_browser_requested)
            card.scrape_store_requested.connect(self.on_scrape_single_requested)
            card.scrape_store_eod_requested.connect(self.on_scrape_store_eod_requested)
            card.config_store_requested.connect(self.on_config_store_requested)

            self.branch_cards[b_id] = card
            self.store_to_branch[grab_id] = (b_id, "grab")
            self.store_to_branch[panda_id] = (b_id, "panda")

            row, col = grid_pos_map.get(b_id, (idx // 2, idx % 2))
            grid_layout.addWidget(card, row, col)

        scroll_layout.addLayout(grid_layout)
        scroll.setWidget(scroll_content)
        main_layout.addWidget(scroll, 1)

        # 5. TOTAL AREA (Combined Total Sales then Total then Last Updated)
        summary_frame = QFrame()
        summary_frame.setObjectName("SummaryCard")
        s_layout = QHBoxLayout(summary_frame)
        s_layout.setContentsMargins(18, 10, 18, 10)
        s_layout.setSpacing(14)

        sum_title = QLabel("Combined Total Sales:")
        sum_title.setStyleSheet("font-size: 16px; font-weight: 800; color: #a7f3d0; text-transform: uppercase;")
        s_layout.addWidget(sum_title)

        self.total_sales_lbl = QLabel("₱ 0.00")
        self.total_sales_lbl.setStyleSheet("font-size: 28px; font-weight: 900; color: #34d399;")
        s_layout.addWidget(self.total_sales_lbl)

        s_layout.addStretch()

        self.last_update_lbl = QLabel("Last Updated: Never")
        self.last_update_lbl.setStyleSheet("font-size: 12px; font-weight: 600; color: #cbd5e1;")
        s_layout.addWidget(self.last_update_lbl)

        main_layout.addWidget(summary_frame)

        # 6. ACTIVITY LOG & OUTPUT CONSOLE
        console_box_layout = QVBoxLayout()
        console_box_layout.setSpacing(4)
        console_header = QHBoxLayout()
        console_title = QLabel("Activity Log & Output Console")
        console_title.setStyleSheet("font-size: 12px; font-weight: bold; color: #94a3b8;")
        
        clear_btn = QPushButton("Clear")
        clear_btn.setObjectName("ActionCardBtn")
        clear_btn.clicked.connect(self.clear_console)
        
        console_header.addWidget(console_title)
        console_header.addStretch()
        console_header.addWidget(clear_btn)
        console_box_layout.addLayout(console_header)

        self.console = QTextEdit()
        self.console.setObjectName("ConsoleBox")
        self.console.setReadOnly(True)
        self.console.setMaximumHeight(110)
        console_box_layout.addWidget(self.console)

        main_layout.addLayout(console_box_layout)

    def toggle_settings_panel(self):
        """Toggles the collapsible settings panel visibility."""
        is_vis = self.settings_frame.isVisible()
        self.settings_frame.setVisible(not is_vis)
        if not is_vis:
            self.toggle_settings_btn.setText("Hide Settings")
            self.toggle_settings_btn.setStyleSheet("background-color: #334155; color: #38bdf8; border: 1px solid #38bdf8;")
        else:
            self.toggle_settings_btn.setText("Settings")
            self.toggle_settings_btn.setStyleSheet("")

    def update_live_clock(self):
        """Updates the visible date and time clock every second and checks for 12 AM / 1 AM scheduled EOD."""
        now = datetime.now()
        self.live_date_lbl.setText(now.strftime("%A, %B %d, %Y"))
        self.live_time_lbl.setText(now.strftime("%I:%M:%S %p"))

        # Automated Scheduled EOD at 12:00 AM (Midnight) and 1:00 AM daily
        if now.hour in (0, 1):
            slot_key = f"{now.strftime('%Y-%m-%d')}_{now.hour:02d}"
            if slot_key not in self.executed_eod_slots:
                self.executed_eod_slots.add(slot_key)
                if is_eod_saved_for_today():
                    self.log_message(f"[Scheduled EOD] EOD is already recorded for today ({now.strftime('%Y-%m-%d')}). Skipping scheduled EOD.", "INFO")
                else:
                    hour_label = "12:00 AM Midnight" if now.hour == 0 else "1:00 AM"
                    self.log_message(f"[Scheduled EOD] Clock reached {hour_label}. Automatically scraping & recording Yesterday's EOD for all 4 hubs...", "INFO")
                    self.trigger_scrape_eod()

    def log_message(self, message: str, level: str = "INFO"):
        color_map = {
            "INFO": "#38bdf8",
            "SUCCESS": "#10b981",
            "WARNING": "#f59e0b",
            "ERROR": "#ef4444"
        }
        color = color_map.get(level.upper(), "#94a3b8")
        timestamp = datetime.now().strftime("%H:%M:%S")
        html = f"<span style='color:#64748b;'>[{timestamp}]</span> <span style='color:{color}; font-weight:bold;'>[{level}]</span> <span style='color:#f1f5f9;'>{message}</span>"
        self.console.append(html)
        scrollbar = self.console.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def on_log_received(self, message: str, level: str):
        self.log_message(message, level)

    def clear_console(self):
        self.console.clear()

    def launch_all_browsers(self):
        self.log_message("Requesting launch of all 8 persistent browser windows...", "INFO")
        self.worker.enqueue_task("launch_all")

    def on_open_browser_requested(self, profile_id: str):
        self.worker.enqueue_task("launch_single", profile_id=profile_id)

    def trigger_scrape_now(self):
        if self.worker.engine:
            self.worker.engine.reset_stop()
        self.scrape_now_btn.setEnabled(False)
        self.scrape_now_btn.setText("Scraping...")
        self.worker.enqueue_task("scrape_all")

    def trigger_stop_scraping(self):
        self.log_message("Stop requested. Aborting ongoing scrape and clearing task queue...", "WARNING")
        self.worker.cancel_current_task()
        self.scrape_now_btn.setEnabled(True)
        self.scrape_now_btn.setText("Scrape All 4 Cities")
        self.eod_btn.setEnabled(True)
        self.eod_btn.setText("EOD")
        for card in self.branch_cards.values():
            if "scraping" in card.grab_sub.status_pill.text().lower():
                card.grab_sub.status_pill.setText("Stopped")
                card.grab_sub.status_pill.setStyleSheet("font-size: 11px; color: #94a3b8;")
            if "scraping" in card.panda_sub.status_pill.text().lower():
                card.panda_sub.status_pill.setText("Stopped")
                card.panda_sub.status_pill.setStyleSheet("font-size: 11px; color: #94a3b8;")

    def trigger_scrape_eod(self):
        if self.worker.engine:
            self.worker.engine.reset_stop()
        self.eod_btn.setEnabled(False)
        self.eod_btn.setText("Scraping EOD...")
        self.scrape_now_btn.setEnabled(False)
        self.log_message("[Forced EOD] Starting yesterday's sales scrape across all 4 cities...", "INFO")
        self.worker.enqueue_task("scrape_eod")

    def on_scrape_branch_requested(self, grab_id: str, panda_id: str):
        if self.worker.engine:
            self.worker.engine.reset_stop()
        self.log_message(f"Triggering live scrape for [{grab_id}] and [{panda_id}]...", "INFO")
        self.worker.enqueue_task("scrape_branch", grab_id=grab_id, panda_id=panda_id, is_eod=False)

    def on_scrape_branch_eod_requested(self, grab_id: str, panda_id: str):
        if self.worker.engine:
            self.worker.engine.reset_stop()
        self.log_message(f"[EOD] Triggering yesterday's sales scrape for [{grab_id}] and [{panda_id}]...", "INFO")
        self.worker.enqueue_task("scrape_branch", grab_id=grab_id, panda_id=panda_id, is_eod=True)

    def on_scrape_single_requested(self, store_id: str):
        if self.worker.engine:
            self.worker.engine.reset_stop()
        self.worker.enqueue_task("scrape_single", store_id=store_id, is_eod=False)

    def on_scrape_store_eod_requested(self, store_id: str):
        if self.worker.engine:
            self.worker.engine.reset_stop()
        self.log_message(f"[EOD] Scraping store [{store_id}] for yesterday's sales...", "INFO")
        self.worker.enqueue_task("scrape_single", store_id=store_id, is_eod=True)

    def update_store_in_ui(self, result: dict):
        store_id = result.get("store_id")
        if store_id in self.store_to_branch:
            b_id, platform_type = self.store_to_branch[store_id]
            card = self.branch_cards.get(b_id)
            if card:
                if platform_type == "grab":
                    card.grab_sub.update_data(result)
                else:
                    card.panda_sub.update_data(result)
                card.recalc_branch_total()

    def on_scrape_all_finished(self, results: list):
        self.scrape_now_btn.setEnabled(True)
        self.scrape_now_btn.setText("Scrape All 4 Cities")
        self.eod_btn.setEnabled(True)
        self.eod_btn.setText("EOD")
        
        is_eod = any(res.get("is_eod") for res in results)
        mode_str = " (EOD Yesterday)" if is_eod else ""

        for res in results:
            self.update_store_in_ui(res)

        grand_total = sum(card.recalc_branch_total() for card in self.branch_cards.values())
        self.total_sales_lbl.setText(f"₱ {grand_total:,.2f}")
        self.last_update_lbl.setText(f"Last Updated: {datetime.now().strftime('%Y-%m-%d %I:%M:%S %p')}{mode_str}")
        self.log_message(f"Scraping completed{mode_str}! Grand Combined Total: ₱ {grand_total:,.2f}", "SUCCESS")

        if is_eod:
            try:
                now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                today_str = datetime.now().strftime("%Y-%m-%d")
                eod_data = {
                    "eod_stores": results,
                    "eod_total_sales": grand_total,
                    "eod_last_updated": f"{now_str} (Yesterday EOD)",
                    "eod_date": today_str,
                    "timestamp": now_str
                }
                with open(EOD_FILE, "w", encoding="utf-8") as f:
                    json.dump(eod_data, f, indent=2)
            except Exception:
                pass

    def on_single_scrape_finished(self, result: dict):
        store_id = result.get("store_id")
        self.update_store_in_ui(result)
        
        shared = result.get("shared_sales")
        if shared:
            sf_amt = shared.get("san_fernando_sales", 0.0)
            overall_amt = shared.get("overall_sales", 0.0)
            cal_amt = shared.get("caloocan_sales", 0.0)
            is_eod = shared.get("is_eod", False)
            if "caloocan" in str(store_id).lower():
                self.update_store_in_ui({
                    "store_id": "grab_4_san_fernando",
                    "amount": sf_amt,
                    "raw_text": f"₱{sf_amt:,.2f} (Overall ₱{overall_amt:,.2f} - Caloocan ₱{cal_amt:,.2f})",
                    "is_eod": is_eod,
                    "success": True,
                    "status": "active" if sf_amt > 0 else "idle"
                })

        grand_total = sum(card.recalc_branch_total() for card in self.branch_cards.values())
        self.total_sales_lbl.setText(f"₱ {grand_total:,.2f}")
        self.last_update_lbl.setText(f"Last Updated: {datetime.now().strftime('%Y-%m-%d %I:%M:%S %p')}")
        self.log_message(f"Finished scraping [{result.get('store_name', store_id)}].", "INFO")

    def on_train_single_requested(self, store_id: str):
        QMessageBox.information(
            self,
            "Train Live Sales Selector",
            f"Training mode will now activate on [{store_id}].\n\n"
            "1. Switch to the browser window.\n"
            "2. Hover over the current sales number.\n"
            "3. Click directly on the sales number to capture it.\n\n"
            "The program will record this live selector permanently!"
        )
        self.worker.enqueue_task("train_single", store_id=store_id)

    def on_train_eod_requested(self, store_id: str):
        store = next((s for s in self.engine.config.get("stores", []) if s["id"] == store_id), None)
        store_name = store["name"] if store else store_id
        is_caloocan = "caloocan" in store_id.lower() or "grab_3" in store_id.lower()
        is_panda = "panda" in store_id.lower() or (store.get("platform") == "foodpanda" if store else False)

        if is_panda:
            msg_text = (
                f"Foodpanda 3-Step EOD Training Wizard for [{store_name}]:\n\n"
                "Step 1: Click the Date Filter / Dropdown button on Foodpanda (or click 'Skip' if 'Yesterday' is already visible).\n"
                "Step 2: Click the 'Yesterday' filter option (the program will click it to load yesterday's dashboard).\n"
                "Step 3: Click directly on the Sales Amount / Net Sales text on the updated page.\n\n"
                "Click OK to begin training in the Foodpanda browser window."
            )
        elif is_caloocan:
            msg_text = (
                f"3-Step EOD Training Wizard for [{store_name}]:\n\n"
                "Step 1: Click the Date Filter / Dropdown button on Grab (or click 'Skip' if 'Yesterday' is already visible).\n"
                "Step 2: Click the 'Yesterday' filter option (the program will click it to load yesterday's 30+ stores list).\n"
                "Step 3: Select the 30 Caloocan stores (or click 'Auto-Detect 30') and compute Top Overall Sales minus Caloocan to get the San Fernando Net Sales balance!\n\n"
                "Click OK to begin training in the browser window."
            )
        else:
            msg_text = (
                f"3-Step EOD Training Wizard for [{store_name}]:\n\n"
                "Step 1: Click the Date Filter / Dropdown button on the Grab page (or click 'Skip' if 'Yesterday' is already visible).\n"
                "Step 2: Click the 'Yesterday' filter option (the program will click it to load yesterday's sales figures).\n"
                "Step 3: Click directly on the Net Sales / Total Sales Amount on the updated page.\n\n"
                "The program will record all steps for 100% automated EOD scraping!"
            )

        QMessageBox.information(
            self,
            "3-Step EOD Training Wizard",
            msg_text
        )
        self.worker.enqueue_task("train_eod", store_id=store_id)

    def on_train_multi_requested(self, store_id: str):
        QMessageBox.information(
            self,
            f"Multi-Store Training: {store_id}",
            f"You will now train the multi-stores for [{store_id}]:\n\n"
            "1. Switch to the Grab browser window.\n"
            "2. Click each store's sales number in order.\n"
            "3. When finished, click 'Done' on the floating top bar.\n\n"
            "All clicked stores will be summed together automatically on every scrape!"
        )
        self.worker.enqueue_task("train_multi", store_id=store_id)

    def on_training_finished(self, store_id: str, selector: str, sample_text: str):
        QMessageBox.information(
            self,
            "Training Successful",
            f"Successfully captured selector for [{store_id}]!\n\n"
            f"Selector: {selector}\n"
            f"Sample Text: {sample_text}"
        )

    def on_multi_train_finished(self, store_id: str, count: int, total_sum: float):
        if store_id in self.store_to_branch:
            b_id, platform_type = self.store_to_branch[store_id]
            card = self.branch_cards.get(b_id)
            if card:
                target = card.grab_sub if platform_type == "grab" else card.panda_sub
                target.info_lbl.setText(f"Trained: {count} stores (₱{total_sum:,.2f})")
        
        QMessageBox.information(
            self,
            "Multi-Select Training Complete",
            f"Successfully recorded {count} store elements for [{store_id}]!\n\n"
            f"Preview Total: ₱{total_sum:,.2f}\n\n"
            "The program will now automatically sum all these stores on every interval scrape!"
        )

    def on_config_store_requested(self, store_id: str):
        if store_id not in self.store_to_branch:
            return
        b_id, platform_type = self.store_to_branch[store_id]
        card = self.branch_cards.get(b_id)
        if not card:
            return
        target_store = card.grab_store if platform_type == "grab" else card.panda_store
        dialog = StoreConfigDialog(target_store, self)
        if dialog.exec_() == QDialog.Accepted:
            self.worker.enqueue_task("save_config")
            if platform_type == "grab":
                card.grab_sub.title_lbl.setText(target_store.get("name", "Store"))
            else:
                card.panda_sub.title_lbl.setText(target_store.get("name", "Store"))
            self.log_message(f"Updated configuration for [{target_store.get('name')}].", "SUCCESS")

    def on_settings_changed(self):
        general_cfg = {
            "interval_minutes": self.interval_spin.value(),
            "refresh_wait_seconds": self.grab_wait_spin.value(),
            "panda_refresh_wait_seconds": self.panda_wait_spin.value(),
            "force_retry_on_zero": self.force_retry_chk.isChecked(),
            "max_retries": self.retries_spin.value()
        }
        self.worker.enqueue_task("update_settings", general=general_cfg)
        if self.is_auto_running:
            self.countdown_seconds = self.interval_spin.value() * 60

    def toggle_auto_scraping(self):
        if not self.is_auto_running:
            self.is_auto_running = True
            interval_mins = self.interval_spin.value()
            self.countdown_seconds = interval_mins * 60
            self.auto_timer.start(1000)
            self.toggle_auto_btn.setText("Stop Auto-Scraping")
            self.toggle_auto_btn.setObjectName("DangerBtn")
            self.toggle_auto_btn.setStyleSheet("background-color: #dc2626; color: white;")
            self.countdown_lbl.setText(f"Next in: {interval_mins:02d}:00")
            self.log_message(f"Auto-scraping started (Every {interval_mins} min, Force-Retry: {self.force_retry_chk.isChecked()}).", "SUCCESS")
            self.trigger_scrape_now()
        else:
            self.is_auto_running = False
            self.auto_timer.stop()
            self.worker.cancel_current_task()
            self.toggle_auto_btn.setText("Start Auto-Scraping")
            self.toggle_auto_btn.setObjectName("SuccessBtn")
            self.toggle_auto_btn.setStyleSheet("")
            self.countdown_lbl.setText("Next Scrape: Stopped")
            self.log_message("Auto-scraping stopped and running tasks cancelled.", "WARNING")

    def on_timer_tick(self):
        if self.countdown_seconds > 0:
            self.countdown_seconds -= 1
            mins = self.countdown_seconds // 60
            secs = self.countdown_seconds % 60
            self.countdown_lbl.setText(f"Next in: {mins:02d}:{secs:02d}")
        else:
            self.countdown_seconds = self.interval_spin.value() * 60
            self.log_message("Interval reached. Triggering automatic 4-city scrape...", "INFO")
            self.trigger_scrape_now()

    def open_txt_log(self):
        txt_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sales_records.txt")
        if not os.path.exists(txt_path):
            with open(txt_path, "w", encoding="utf-8") as f:
                f.write("=== SALES RECORDS LOG (4 CONSOLIDATED BRANCHES) ===\n\n")
        try:
            os.startfile(txt_path)
        except Exception as e:
            self.log_message(f"Cannot open TXT file: {e}", "ERROR")

    def open_csv_log(self):
        csv_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sales_records.csv")
        if not os.path.exists(csv_path):
            with open(csv_path, "w", encoding="utf-8") as f:
                f.write("Timestamp,Store ID,Store Name,Platform,Raw Text,Parsed Amount,Status\n")
        try:
            os.startfile(csv_path)
        except Exception as e:
            self.log_message(f"Cannot open CSV file: {e}", "ERROR")

    def closeEvent(self, event):
        self.worker.stop()
        self.worker.wait(2000)
        event.accept()


def main():
    app = QApplication(sys.argv)
    window = SalesScraperApp()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
