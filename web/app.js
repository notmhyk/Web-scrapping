// Multi-Branch Sales Dashboard Client Logic (4 Consolidated Branches / 8 Portals)

let currentAppTab = "live"; // 'live' or 'eod'

let appState = {
  branches: [],
  stores: [],
  total_sales: 0.0,
  last_updated: "Never",
  eod_stores: [],
  eod_total_sales: 0.0,
  eod_last_updated: "Not recorded yet",
  eod_recorded: false,
  auto_running: false,
  countdown_seconds: 0,
  interval_minutes: 1,
  refresh_wait_seconds: 5,
  panda_refresh_wait_seconds: 10,
  force_retry: true,
  max_retries: 3
};

let countdownTimer = null;

function setAppTab(mode) {
  currentAppTab = mode;
  
  const liveBtn = document.getElementById("btn-admin-view-live");
  const eodBtn = document.getElementById("btn-admin-view-eod");

  if (liveBtn && eodBtn) {
    if (mode === "live") {
      liveBtn.classList.add("active");
      eodBtn.classList.remove("active");
    } else {
      eodBtn.classList.add("active");
      liveBtn.classList.remove("active");
    }
  }

  // Immediately re-render active dataset
  updateDashboardUI(appState);
}

// Theme Handling (Default: Dark Mode for Web App)
function initTheme() {
  const savedTheme = localStorage.getItem("webapp_theme") || "dark";
  applyTheme(savedTheme);
}

function toggleTheme() {
  const current = document.documentElement.getAttribute("data-theme") || "dark";
  const next = current === "dark" ? "light" : "dark";
  applyTheme(next);
  localStorage.setItem("webapp_theme", next);
}

function applyTheme(theme) {
  document.documentElement.setAttribute("data-theme", theme);
  const themeBtn = document.getElementById("btn-toggle-theme");
  if (themeBtn) {
    themeBtn.innerHTML = theme === "dark" 
      ? '<span>Light Mode</span>' 
      : '<span>Dark Mode</span>';
    themeBtn.setAttribute("title", `Switch to ${theme === "dark" ? "Light" : "Dark"} mode`);
  }
}

// Initialize on DOM load
document.addEventListener("DOMContentLoaded", () => {
  initTheme();
  setupEventListeners();
  updateLiveClock();
  setInterval(updateLiveClock, 1000);
  startStatusPolling();
  setupSSE();
});

function updateLiveClock() {
  const now = new Date();
  const dateEl = document.getElementById("live-clock-date");
  const timeEl = document.getElementById("live-clock-time");
  if (dateEl) {
    const options = { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' };
    dateEl.innerText = now.toLocaleDateString(undefined, options);
  }
  if (timeEl) {
    timeEl.innerText = now.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: true });
  }
}

function setupEventListeners() {
  // Theme Toggle Button
  const themeBtn = document.getElementById("btn-toggle-theme");
  if (themeBtn) {
    themeBtn.addEventListener("click", toggleTheme);
  }

  // Toolbar Buttons
  document.getElementById("btn-launch-browsers").addEventListener("click", () => {
    postAPI("/api/launch_browsers");
    showToast("Launching all 8 browser windows (4 Grab + 4 Foodpanda)...", "info");
  });

  document.getElementById("btn-tile-browsers").addEventListener("click", () => {
    postAPI("/api/tile_browsers");
    showToast("Aligning all 8 browsers to 2x4 locked screen grid...", "info");
  });

  document.getElementById("btn-scrape-all").addEventListener("click", () => {
    const btn = document.getElementById("btn-scrape-all");
    btn.disabled = true;
    btn.innerHTML = 'Scraping All 4...';
    postAPI("/api/scrape_all").finally(() => {
      setTimeout(() => {
        btn.disabled = false;
        btn.innerHTML = 'Scrape All 4 Cities';
      }, 3500);
    });
    showToast("Scraping all 4 cities across Grab and Foodpanda...", "info");
  });

  const btnEod = document.getElementById("btn-eod");
  if (btnEod) {
    btnEod.addEventListener("click", () => {
      btnEod.disabled = true;
      btnEod.innerHTML = "Scraping EOD...";
      postAPI("/api/scrape_eod").finally(() => {
        setTimeout(() => {
          btnEod.disabled = false;
          btnEod.innerHTML = "EOD";
        }, 3500);
      });
      showToast("[EOD] Scraping yesterday's sales across all 4 cities...", "info");
    });
  }

  const btnStop = document.getElementById("btn-stop-scraping");
  if (btnStop) {
    btnStop.addEventListener("click", () => {
      postAPI("/api/stop_scraping");
      showToast("Stopping ongoing scrape and cancelling operations...", "warning");
      const btnScrapeAll = document.getElementById("btn-scrape-all");
      if (btnScrapeAll) {
        btnScrapeAll.disabled = false;
        btnScrapeAll.innerHTML = "Scrape All 4 Cities";
      }
      if (btnEod) {
        btnEod.disabled = false;
        btnEod.innerHTML = "EOD";
      }
    });
  }

  document.getElementById("btn-toggle-auto").addEventListener("click", toggleAutoScraping);

  // Inputs
  document.getElementById("interval-input").addEventListener("change", (e) => {
    const val = parseInt(e.target.value) || 1;
    appState.interval_minutes = val;
    postAPI("/api/update_settings", { interval_minutes: val });
  });

  document.getElementById("wait-input").addEventListener("change", (e) => {
    const val = parseInt(e.target.value) || 5;
    appState.refresh_wait_seconds = val;
    postAPI("/api/update_settings", { refresh_wait_seconds: val });
    showToast(`Grab refresh wait time set to ${val} seconds`, "info");
  });

  const pandaWaitEl = document.getElementById("panda-wait-input");
  if (pandaWaitEl) {
    pandaWaitEl.addEventListener("change", (e) => {
      const val = parseInt(e.target.value) || 10;
      appState.panda_refresh_wait_seconds = val;
      postAPI("/api/update_settings", { panda_refresh_wait_seconds: val });
      showToast(`Foodpanda refresh wait time set to ${val} seconds`, "info");
    });
  }

  document.getElementById("force-retry-chk").addEventListener("change", (e) => {
    const val = e.target.checked;
    appState.force_retry = val;
    postAPI("/api/update_settings", { force_retry_on_zero: val });
    showToast(`Force Retry on 0 is now ${val ? "Enabled" : "Disabled"}`, "info");
  });

  document.getElementById("retries-input").addEventListener("change", (e) => {
    const val = parseInt(e.target.value) || 3;
    appState.max_retries = val;
    postAPI("/api/update_settings", { max_retries: val });
  });

  const toggleSettingsBtn = document.getElementById("btn-toggle-settings");
  if (toggleSettingsBtn) {
    toggleSettingsBtn.addEventListener("click", () => {
      const drawer = document.getElementById("settings-drawer");
      if (!drawer) return;
      const isCollapsed = drawer.classList.contains("collapsed");
      if (isCollapsed) {
        drawer.classList.remove("collapsed");
        toggleSettingsBtn.innerHTML = "Hide Settings";
        toggleSettingsBtn.style.color = "var(--primary)";
        toggleSettingsBtn.style.borderColor = "var(--primary)";
      } else {
        drawer.classList.add("collapsed");
        toggleSettingsBtn.innerHTML = "Settings";
        toggleSettingsBtn.style.color = "";
        toggleSettingsBtn.style.borderColor = "";
      }
    });
  }

  const toggleAllBtn = document.getElementById("btn-toggle-all-drawers");
  if (toggleAllBtn) {
    toggleAllBtn.addEventListener("click", () => {
      const allDrawers = document.querySelectorAll(".branch-drawer");
      const anyCollapsed = Array.from(allDrawers).some(d => d.classList.contains("collapsed"));
      
      allDrawers.forEach(d => {
        const branchId = d.id.replace("drawer-", "");
        const toggleBtn = document.getElementById(`btn-toggle-${branchId}`);
        if (anyCollapsed) {
          d.classList.remove("collapsed");
          openDrawers.add(branchId);
          if (toggleBtn) toggleBtn.innerHTML = '<span>Hide Tools</span>';
        } else {
          d.classList.add("collapsed");
          openDrawers.delete(branchId);
          if (toggleBtn) toggleBtn.innerHTML = '<span>Tools</span>';
        }
      });
      toggleAllBtn.innerHTML = anyCollapsed ? 'Hide All Tools' : 'Toggle Tools';
    });
  }

  // Open Log Files
  document.getElementById("btn-open-txt").addEventListener("click", () => {
    postAPI("/api/open_file/txt");
    showToast("Opening sales_records.txt on your desktop...", "info");
  });

  document.getElementById("btn-open-csv").addEventListener("click", () => {
    postAPI("/api/open_file/csv");
    showToast("Opening sales_records.csv on your desktop...", "info");
  });

  document.getElementById("btn-clear-console").addEventListener("click", () => {
    document.getElementById("console-window").innerHTML = "";
  });

  // Google Sheets Listeners
  const gsChk = document.getElementById("gs-enabled-chk");
  if (gsChk) {
    gsChk.addEventListener("change", (e) => {
      postAPI("/api/update_settings", { google_sheets: { enabled: e.target.checked } });
      showToast(`Google Sheets Sync ${e.target.checked ? "Enabled" : "Disabled"}`, "info");
    });
  }

  const gsUrl = document.getElementById("gs-webhook-url");
  if (gsUrl) {
    gsUrl.addEventListener("change", (e) => {
      postAPI("/api/update_settings", { google_sheets: { webhook_url: e.target.value.trim() } });
      showToast("Google Sheets Webhook URL saved!", "success");
    });
  }

  const btnSyncGsNow = document.getElementById("btn-sync-gs-now");
  if (btnSyncGsNow) {
    btnSyncGsNow.addEventListener("click", () => {
      showToast("Syncing current live sales to Google Sheet...", "info");
      postAPI("/api/sync_google_sheets", { is_eod: false })
        .then(res => {
          if (res && res.success) {
            showToast("Successfully synced live sales to Google Sheet!", "success");
          } else {
            showToast("Sync failed: " + (res ? (res.error || res.message) : "Unknown error"), "error");
          }
        });
    });
  }

  const btnSyncGsEod = document.getElementById("btn-sync-gs-eod");
  if (btnSyncGsEod) {
    btnSyncGsEod.addEventListener("click", () => {
      showToast("Syncing EOD sales to table S44 in Google Sheet...", "info");
      postAPI("/api/sync_google_sheets", { is_eod: true })
        .then(res => {
          if (res && res.success) {
            showToast("Successfully synced EOD to S44 in Google Sheet!", "success");
          } else {
            showToast("Sync failed: " + (res ? (res.error || res.message) : "Unknown error"), "error");
          }
        });
    });
  }

  // Modal Close
  document.getElementById("modal-close-btn").addEventListener("click", closeModal);
  document.getElementById("modal-ok-btn").addEventListener("click", closeModal);
}

// Fetch Full Status from Backend
async function fetchStatus() {
  try {
    const res = await fetch("/api/status");
    if (!res.ok) return;
    const data = await res.json();
    updateDashboardUI(data);
  } catch (err) {
    console.error("Status fetch error:", err);
  }
}

function startStatusPolling() {
  fetchStatus();
  setInterval(fetchStatus, 3000);
}

// Server-Sent Events (SSE) for Real-Time Logs and Instant Updates
function setupSSE() {
  const evtSource = new EventSource("/api/events");

  evtSource.onmessage = (e) => {
    try {
      const msg = JSON.parse(e.data);
      if (msg.type === "log") {
        appendLog(msg.message, msg.level);
      } else if (msg.type === "scrape_finished" || msg.type === "status_update") {
        updateDashboardUI(msg.data || msg);
        if (msg.type === "scrape_finished" && msg.data && typeof msg.data.total_sales === "number") {
          showToast(`Scrape complete! Total: ₱ ${msg.data.total_sales.toLocaleString(undefined, {minimumFractionDigits: 2})}`, "success");
        }
      } else if (msg.type === "training_complete") {
        fetchStatus();
        showModal("Training Complete", msg.message);
      }
    } catch (err) {
      console.error("SSE parse error:", err);
    }
  };

  evtSource.onerror = () => {
    document.getElementById("backend-status-text").innerText = "Reconnecting...";
  };

  evtSource.onopen = () => {
    document.getElementById("backend-status-text").innerText = "Live Sync Active";
  };
}

// Update DOM elements with backend state
function updateDashboardUI(data) {
  if (!data) return;

  if (data.branches && Array.isArray(data.branches)) {
    appState.branches = data.branches;
  }
  if (data.stores && Array.isArray(data.stores)) {
    appState.stores = data.stores;
  }
  if (typeof data.total_sales === "number") {
    appState.total_sales = data.total_sales;
  }
  if (data.last_updated) {
    appState.last_updated = data.last_updated;
  }

  // EOD fields
  if (data.eod_stores && Array.isArray(data.eod_stores)) {
    appState.eod_stores = data.eod_stores;
  }
  if (typeof data.eod_total_sales === "number") {
    appState.eod_total_sales = data.eod_total_sales;
  }
  if (data.eod_last_updated) {
    appState.eod_last_updated = data.eod_last_updated;
  }
  if (typeof data.eod_recorded === "boolean") {
    appState.eod_recorded = data.eod_recorded;
  }
  if (typeof data.is_live_synced === "boolean") {
    appState.is_live_synced = data.is_live_synced;
    const statusTextEl = document.getElementById("backend-status-text");
    if (statusTextEl) {
      statusTextEl.innerText = data.is_live_synced ? "Live Sync Active" : "Not Synced";
    }
  }

  const isEodView = (currentAppTab === "eod");

  // Determine active dataset to display
  const activeStores = isEodView ? (appState.eod_stores.length > 0 ? appState.eod_stores : appState.stores) : appState.stores;
  const activeTotal = isEodView ? appState.eod_total_sales : appState.total_sales;
  const activeUpdated = isEodView ? appState.eod_last_updated : appState.last_updated;

  // Update Summary Banner Title Label
  const summaryLabel = document.getElementById("app-summary-label");
  if (summaryLabel) {
    summaryLabel.innerText = isEodView ? "COMBINED TOTAL SALES (YESTERDAY EOD)" : "COMBINED TOTAL SALES (TODAY)";
  }

  // Grand Total Sales
  const formatted = `₱ ${activeTotal.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  const totalEl = document.getElementById("total-combined-sales");
  if (totalEl) totalEl.innerText = formatted;

  // Last Updated
  const lastUpEl = document.getElementById("last-updated-time");
  if (lastUpEl && activeUpdated) {
    lastUpEl.innerText = `Last Updated: ${activeUpdated}`;
  }

  // Render 4 Consolidated Branch Cards
  renderBranches(appState.branches, activeStores, isEodView);

  // Auto Scraping Status
  if (typeof data.auto_running === "boolean") {
    appState.auto_running = data.auto_running;
    updateAutoButtonUI(data.auto_running);
  }

  if (typeof data.countdown_seconds === "number" && appState.auto_running) {
    appState.countdown_seconds = data.countdown_seconds;
    updateCountdownUI(data.countdown_seconds);
  }

  // Sync Input Values
  if (data.general) {
    if (document.activeElement !== document.getElementById("interval-input")) {
      document.getElementById("interval-input").value = data.general.interval_minutes || 1;
    }
    if (document.activeElement !== document.getElementById("wait-input")) {
      document.getElementById("wait-input").value = data.general.refresh_wait_seconds || 5;
    }
    const pWait = document.getElementById("panda-wait-input");
    if (pWait && document.activeElement !== pWait) {
      pWait.value = data.general.panda_refresh_wait_seconds || 10;
    }
    if (document.activeElement !== document.getElementById("retries-input")) {
      document.getElementById("retries-input").value = data.general.max_retries || 3;
    }
    document.getElementById("force-retry-chk").checked = data.general.force_retry_on_zero !== false;
  }

  // Sync Google Sheets Settings
  if (data.google_sheets) {
    const gsChk = document.getElementById("gs-enabled-chk");
    if (gsChk) gsChk.checked = data.google_sheets.enabled !== false;
    const gsUrl = document.getElementById("gs-webhook-url");
    if (gsUrl && document.activeElement !== gsUrl) {
      gsUrl.value = data.google_sheets.webhook_url || "";
    }
  }
}

// Default Branch Definitions if not loaded from backend yet
const DEFAULT_BRANCHES = [
  { id: "angeles", name: "Angeles City", grab_store_id: "grab_1", panda_store_id: "panda_1" },
  { id: "qc", name: "Quezon City", grab_store_id: "grab_2", panda_store_id: "panda_2" },
  { id: "caloocan", name: "Caloocan City", grab_store_id: "grab_3_caloocan", panda_store_id: "panda_3" },
  { id: "san_fernando", name: "San Fernando City", grab_store_id: "grab_4_san_fernando", panda_store_id: "panda_4" }
];

// Track opened drawers
const openDrawers = new Set();

function toggleBranchDrawer(branchId) {
  const drawer = document.getElementById(`drawer-${branchId}`);
  const toggleBtn = document.getElementById(`btn-toggle-${branchId}`);
  if (!drawer) return;

  const isCollapsed = drawer.classList.contains("collapsed");
  if (isCollapsed) {
    drawer.classList.remove("collapsed");
    openDrawers.add(branchId);
    if (toggleBtn) toggleBtn.innerHTML = '<span>Hide Tools</span>';
  } else {
    drawer.classList.add("collapsed");
    openDrawers.delete(branchId);
    if (toggleBtn) toggleBtn.innerHTML = '<span>Tools</span>';
  }
}

// Render the 4 Consolidated Branch Cards
function renderBranches(branches, stores, isEodView = false) {
  const container = document.getElementById("branches-grid");
  if (!container) return;

  const order = ["angeles", "qc", "caloocan", "san_fernando"];
  const rawList = (branches && branches.length > 0) ? branches : DEFAULT_BRANCHES;
  const branchList = [...rawList].sort((a, b) => {
    const idxA = order.indexOf(a.id);
    const idxB = order.indexOf(b.id);
    return (idxA === -1 ? 99 : idxA) - (idxB === -1 ? 99 : idxB);
  });

  const storeMap = {};
  (stores || []).forEach(s => { storeMap[s.id] = s; });

  branchList.forEach(branch => {
    const branchNameClean = (branch.name || "").replace(/\s*Branch\s*/gi, "").trim();
    const grabStore = storeMap[branch.grab_store_id] || { id: branch.grab_store_id, name: `${branchNameClean} (Grab)`, platform: "grab", last_amount: 0.0, status: "idle" };
    const pandaStore = storeMap[branch.panda_store_id] || { id: branch.panda_store_id, name: `${branchNameClean} (Foodpanda)`, platform: "foodpanda", last_amount: 0.0, status: "idle" };

    const grabAmt = typeof grabStore.last_amount === "number" ? grabStore.last_amount : 0.0;
    const pandaAmt = typeof pandaStore.last_amount === "number" ? pandaStore.last_amount : 0.0;
    const branchTotal = grabAmt + pandaAmt;

    const branchTotalFormatted = `₱ ${branchTotal.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
    const grabAmtFormatted = `₱ ${grabAmt.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
    const pandaAmtFormatted = `₱ ${pandaAmt.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

    let branchCardEl = document.getElementById(`branch-card-${branch.id}`);

    const grabBadgeText = "GRAB";
    const grabBadgeClass = "grab";

    const grabStatus = getStatusBadge(grabStore, grabAmt, isEodView);
    const pandaStatus = getStatusBadge(pandaStore, pandaAmt, isEodView);
    const heroSubText = isEodView ? "Yesterday EOD Total" : "Live Aggregate";

    const grabDetails = grabStore.last_raw_text ? grabStore.last_raw_text : "Not scraped yet";
    const pandaDetails = pandaStore.last_raw_text ? pandaStore.last_raw_text : (pandaStore.selector ? "Selector Trained" : "Not trained / scraped yet");

    const isDrawerOpen = openDrawers.has(branch.id);
    const drawerCls = isDrawerOpen ? "branch-drawer" : "branch-drawer collapsed";
    const toggleLabel = isDrawerOpen ? "Hide Tools" : "Tools";

    if (!branchCardEl) {
      branchCardEl = document.createElement("div");
      branchCardEl.className = "branch-card";
      branchCardEl.id = `branch-card-${branch.id}`;

      const isGrabMulti = Boolean(grabStore.expected_count || (grabStore.multi_selectors && grabStore.multi_selectors.length > 0));
      const grabTrainLabel = isGrabMulti ? `Train (${grabStore.expected_count || 30})` : "Train";

      branchCardEl.innerHTML = `
        <!-- 1. Header: City Name & Actions -->
        <div class="branch-header">
          <div class="branch-title-wrap">
            <h3 class="branch-title">${branchNameClean}</h3>
          </div>
          <div class="branch-header-actions">
            <button class="btn btn-branch-quick-scrape" id="btn-quick-scrape-${branch.id}" onclick="triggerScrapeBranch('${branch.id}')" title="Scrape ${branchNameClean} (Live)">
              Scrape
            </button>
            <button class="btn btn-branch-eod-scrape" id="btn-quick-scrape-eod-${branch.id}" onclick="triggerScrapeBranchEOD('${branch.id}')" title="Scrape Yesterday's EOD for ${branchNameClean}">
              Scrape EOD
            </button>
            <button class="btn btn-collapse-toggle" id="btn-toggle-${branch.id}" onclick="toggleBranchDrawer('${branch.id}')" title="Toggle Training Tools">
              <span>${toggleLabel}</span>
            </button>
          </div>
        </div>

        <!-- 2. Combined Total Sales (Prominent, Large, Bold) -->
        <div class="branch-total-hero">
          <div class="branch-total-meta">
            <span class="branch-total-title">Total (Grab + Panda)</span>
            <span class="branch-total-sub" id="branch-total-sub-${branch.id}">${heroSubText}</span>
          </div>
          <div class="branch-total-main" id="branch-total-${branch.id}">${branchTotalFormatted}</div>
        </div>

        <!-- 3. Side-by-Side Sales Row (Left Grab | Right Foodpanda) -->
        <div class="platforms-side-by-side">
          
          <!-- Grab Mini-Panel (Left) -->
          <div class="platform-mini-panel grab-mini" id="mini-${grabStore.id}">
            <div class="mini-panel-header">
              <span class="platform-tag ${grabBadgeClass}">${grabBadgeText}</span>
              <span class="card-status-pill ${grabStatus.cls}" id="status-pill-${grabStore.id}">${grabStatus.text}</span>
            </div>
            <div class="mini-sales-figure ${grabAmt > 0 ? 'positive' : 'zero'}" id="sales-figure-${grabStore.id}">
              ${grabAmtFormatted}
            </div>
          </div>

          <!-- Foodpanda Mini-Panel (Right) -->
          <div class="platform-mini-panel panda-mini" id="mini-${pandaStore.id}">
            <div class="mini-panel-header">
              <span class="platform-tag foodpanda">FOODPANDA</span>
              <span class="card-status-pill ${pandaStatus.cls}" id="status-pill-${pandaStore.id}">${pandaStatus.text}</span>
            </div>
            <div class="mini-sales-figure ${pandaAmt > 0 ? 'positive' : 'zero'}" id="sales-figure-${pandaStore.id}">
              ${pandaAmtFormatted}
            </div>
          </div>

        </div>

        <!-- 4. Collapsible Drawer (Default Hidden) -->
        <div class="${drawerCls}" id="drawer-${branch.id}">
          <div class="drawer-sections-grid">
            
            <!-- Grab Controls -->
            <div class="drawer-sub-section">
              <div class="drawer-sub-title">Grab Tools:</div>
              <div class="platform-actions-row">
                <button class="btn btn-card-train" onclick="triggerTrain('${grabStore.id}', ${isGrabMulti})">
                  ${grabTrainLabel}
                </button>
                <button class="btn btn-card-eod-train" onclick="triggerTrainEOD('${grabStore.id}')" title="Train Yesterday's EOD 3-Step Workflow">Train EOD</button>
                <button class="btn btn-card-action" onclick="triggerFocusBrowser('${grabStore.profile_id || grabStore.id}')" title="View Grab Browser">
                  View
                </button>
                <button class="btn btn-card-action btn-scrape-sm" onclick="triggerScrapeSingle('${grabStore.id}')" title="Scrape Grab Only (Live)">
                  Scrape
                </button>
                <button class="btn btn-card-action btn-eod-scrape-sm" onclick="triggerScrapeSingleEOD('${grabStore.id}')" title="Scrape Grab EOD Yesterday">
                  Scrape EOD
                </button>
              </div>
            </div>

            <!-- Foodpanda Controls -->
            <div class="drawer-sub-section">
              <div class="drawer-sub-title">Foodpanda Tools:</div>
              <div class="platform-actions-row">
                <button class="btn btn-card-train" onclick="triggerTrain('${pandaStore.id}', false)">
                  Train
                </button>
                <button class="btn btn-card-eod-train" onclick="triggerTrainEOD('${pandaStore.id}')" title="Train Foodpanda Yesterday's EOD 3-Step Workflow">
                  Train EOD
                </button>
                <button class="btn btn-card-action" onclick="triggerFocusBrowser('${pandaStore.profile_id || pandaStore.id}')" title="View Panda Browser">
                  View
                </button>
                <button class="btn btn-card-action btn-scrape-sm" onclick="triggerScrapeSingle('${pandaStore.id}')" title="Scrape Panda Only (Live)">
                  Scrape
                </button>
                <button class="btn btn-card-action btn-eod-scrape-sm" onclick="triggerScrapeSingleEOD('${pandaStore.id}')" title="Scrape Foodpanda EOD Yesterday">
                  Scrape EOD
                </button>
              </div>
            </div>

          </div>

          <div class="drawer-footer-actions">
            <button class="btn btn-branch-scrape" id="btn-scrape-branch-${branch.id}" onclick="triggerScrapeBranch('${branch.id}')">
              Scrape ${branchNameClean} (Live)
            </button>
            <button class="btn btn-branch-eod-scrape-lg" id="btn-scrape-branch-eod-${branch.id}" onclick="triggerScrapeBranchEOD('${branch.id}')">
              Scrape EOD (Yesterday)
            </button>
          </div>
        </div>
      `;
      container.appendChild(branchCardEl);
    } else {
      // Update existing branch card values
      const bSubEl = document.getElementById(`branch-total-sub-${branch.id}`);
      if (bSubEl) bSubEl.innerText = heroSubText;

      const bTotalEl = document.getElementById(`branch-total-${branch.id}`);
      if (bTotalEl) bTotalEl.innerText = branchTotalFormatted;

      // Update Grab row
      const grabSalesEl = document.getElementById(`sales-figure-${grabStore.id}`);
      if (grabSalesEl) {
        grabSalesEl.innerText = grabAmtFormatted;
        grabSalesEl.className = `mini-sales-figure ${grabAmt > 0 ? 'positive' : 'zero'}`;
      }
      const grabStatusEl = document.getElementById(`status-pill-${grabStore.id}`);
      if (grabStatusEl) {
        grabStatusEl.innerText = grabStatus.text;
        grabStatusEl.className = `card-status-pill ${grabStatus.cls}`;
      }

      // Update Panda row
      const pandaSalesEl = document.getElementById(`sales-figure-${pandaStore.id}`);
      if (pandaSalesEl) {
        pandaSalesEl.innerText = pandaAmtFormatted;
        pandaSalesEl.className = `mini-sales-figure ${pandaAmt > 0 ? 'positive' : 'zero'}`;
      }
      const pandaStatusEl = document.getElementById(`status-pill-${pandaStore.id}`);
      if (pandaStatusEl) {
        pandaStatusEl.innerText = pandaStatus.text;
        pandaStatusEl.className = `card-status-pill ${pandaStatus.cls}`;
      }
    }
  });
}

function getStatusBadge(store, amt, isEodView = false) {
  if (isEodView) {
    if (amt > 0) return { cls: "active", text: "EOD Saved" };
    return { cls: "idle", text: "No EOD Data" };
  }
  if (store.status === "not_synced" || (!appState.is_live_synced && amt === 0 && store.status !== "scraping" && store.status !== "retrying")) {
    return { cls: "idle", text: "Not Synced" };
  }
  if (store.status === "active" || (store.last_success && amt > 0)) {
    return { cls: "active", text: "Active" };
  } else if (store.status === "retrying") {
    return { cls: "retrying", text: "Retrying..." };
  } else if (store.status === "scraping") {
    return { cls: "retrying", text: "Scraping..." };
  } else if (store.last_success === false || amt === 0) {
    return { cls: "check", text: "0 / Check" };
  }
  return { cls: "idle", text: "Not Synced" };
}

// Actions
function triggerScrapeBranch(branchId) {
  const branch = appState.branches.find(b => b.id === branchId) || DEFAULT_BRANCHES.find(b => b.id === branchId);
  const branchNameClean = (branch ? branch.name : branchId).replace(/\s*Branch\s*/gi, "").trim();

  const btn = document.getElementById(`btn-scrape-branch-${branchId}`);
  if (btn) {
    btn.disabled = true;
    btn.innerText = `Scraping ${branchNameClean}...`;
    setTimeout(() => {
      btn.disabled = false;
      btn.innerText = `Scrape ${branchNameClean} (Live)`;
    }, 3500);
  }

  const quickBtn = document.getElementById(`btn-quick-scrape-${branchId}`);
  if (quickBtn) {
    quickBtn.disabled = true;
    quickBtn.innerText = `Scraping...`;
    setTimeout(() => {
      quickBtn.disabled = false;
      quickBtn.innerText = `Scrape`;
    }, 3500);
  }

  postAPI(`/api/scrape_branch/${branchId}`);
  showToast(`Scraping live sales for [${branchNameClean}]...`, "info");
}

function triggerScrapeBranchEOD(branchId) {
  const branch = appState.branches.find(b => b.id === branchId) || DEFAULT_BRANCHES.find(b => b.id === branchId);
  const branchNameClean = (branch ? branch.name : branchId).replace(/\s*Branch\s*/gi, "").trim();

  const btn = document.getElementById(`btn-scrape-branch-eod-${branchId}`);
  if (btn) {
    btn.disabled = true;
    btn.innerText = `Scraping EOD...`;
    setTimeout(() => {
      btn.disabled = false;
      btn.innerText = `Scrape EOD (Yesterday)`;
    }, 3500);
  }

  const quickBtn = document.getElementById(`btn-quick-scrape-eod-${branchId}`);
  if (quickBtn) {
    quickBtn.disabled = true;
    quickBtn.innerText = `Scraping...`;
    setTimeout(() => {
      quickBtn.disabled = false;
      quickBtn.innerText = `Scrape EOD`;
    }, 3500);
  }

  postAPI(`/api/scrape_branch_eod/${branchId}`);
  showToast(`Scraping yesterday's EOD sales for [${branchNameClean}]...`, "info");
}

function triggerTrainCSV(storeId) {
  const store = appState.stores.find((s) => s.id === storeId);
  const storeName = store ? store.name : storeId;

  showModal(
    `Train Grab CSV Export: ${storeName}`,
    `CSV EXPORT ACTION RECORDER:\n\n` +
    `1. Switch to the browser window for [${storeName}].\n` +
    `2. Click the Export / Download button(s) on the Grab Finances page.\n` +
    `3. When you see the download trigger, click the 'Save & Test Download' button on the floating top bar.\n\n` +
    `Playwright intercepts the download stream silently and computes sales automatically!`
  );
  postAPI(`/api/train_csv_export/${storeId}`);
}

function triggerTrain(storeId, isMulti) {
  const store = appState.stores.find((s) => s.id === storeId);
  const storeName = store ? store.name : storeId;

  if (isMulti) {
    const count = store ? (store.expected_count || 30) : 30;
    showModal(
      `Multi-Store Training: ${storeName}`,
      `You will now train the ${count} stores for [${storeName}]:\n\n` +
      `1. Switch to the Grab browser window.\n` +
      `2. Click each store's sales number from 1 to ${count}.\n` +
      `3. When finished, click the 'Done' button on the floating top bar.\n\n` +
      `All clicked stores will be saved and summed together automatically on every scrape!`
    );
    postAPI(`/api/train_multi/${storeId}`);
  } else {
    showModal(
      `Train Sales Element: ${storeName}`,
      `Training mode will now activate on [${storeName}]:\n\n` +
      `1. Switch to the browser window.\n` +
      `2. Hover over the sales number.\n` +
      `3. Click directly on the sales number to capture it.\n\n` +
      `The program records this selector location permanently for future scrapes!`
    );
    postAPI(`/api/train_single/${storeId}`);
  }
}

function triggerTrainEOD(storeId) {
  const store = appState.stores.find((s) => s.id === storeId);
  const storeName = store ? store.name : storeId;
  const isPanda = storeId.includes("panda") || (store && store.platform === "foodpanda");
  const isCaloocanGrab = !isPanda && (storeId.includes("caloocan") || storeId.includes("grab_3"));

  if (isPanda) {
    showModal(
      `Foodpanda 3-Step EOD Training Wizard: ${storeName}`,
      `Foodpanda 3-Step EOD Training Wizard for [${storeName}]:\n\n` +
      `Step 1: Click the Date Filter / Dropdown button on Foodpanda (or click 'Skip' if 'Yesterday' is already visible).\n` +
      `Step 2: Click the 'Yesterday' filter option (the program will click it to load yesterday's sales figures).\n` +
      `Step 3: Click directly on the Sales Amount / Net Sales text on the updated page.\n\n` +
      `The program saves all selectors for 100% automated EOD scraping!`
    );
  } else if (isCaloocanGrab) {
    showModal(
      `Caloocan Grab 3-Step EOD Training Wizard: ${storeName}`,
      `Caloocan Grab 3-Step EOD Training Wizard:\n\n` +
      `Step 1: Click the Date Filter / Dropdown button on Grab (or click 'Skip' if 'Yesterday' is already visible).\n` +
      `Step 2: Click the 'Yesterday' filter option (the program will click it to load yesterday's 30+ stores list).\n` +
      `Step 3: Select the 30 Caloocan stores (or click 'Auto-Detect 30') and compute Top Overall Sales minus Caloocan to get the San Fernando Net Sales balance!\n\n` +
      `All 30 stores and the shared deduction balance will be permanently saved for automated EOD scraping!`
    );
  } else {
    showModal(
      `3-Step EOD Training Wizard: ${storeName}`,
      `3-Step EOD Training Wizard for [${storeName}]:\n\n` +
      `Step 1: Click the Date Filter / Dropdown button on the Grab page (or click 'Skip' if 'Yesterday' is already visible).\n` +
      `Step 2: Click the 'Yesterday' filter option (the program will click it to load yesterday's data).\n` +
      `Step 3: Click directly on the Net Sales / Total Sales Amount on the updated page.\n\n` +
      `The program saves all selectors for 100% automated EOD scraping!`
    );
  }
  postAPI(`/api/train_eod/${storeId}`);
}

function triggerFocusBrowser(profileId) {
  postAPI(`/api/focus_browser/${profileId}`);
  showToast(`Bringing browser window [${profileId}] to front...`, "info");
}

function triggerScrapeSingle(storeId) {
  postAPI(`/api/scrape_single/${storeId}`);
  showToast(`Scraping portal [${storeId}] (Live)...`, "info");
}

function triggerScrapeSingleEOD(storeId) {
  postAPI(`/api/scrape_single_eod/${storeId}`);
  showToast(`Scraping portal [${storeId}] (EOD Yesterday)...`, "info");
}

function toggleAutoScraping() {
  const newRunning = !appState.auto_running;
  appState.auto_running = newRunning;
  updateAutoButtonUI(newRunning);

  postAPI("/api/toggle_auto", { running: newRunning });
  if (newRunning) {
    showToast(`Auto-scraping started (Every ${appState.interval_minutes} min)`, "success");
    startLocalCountdown();
  } else {
    showToast("Auto-scraping paused", "info");
    stopLocalCountdown();
  }
}

function updateAutoButtonUI(running) {
  const btn = document.getElementById("btn-toggle-auto");
  if (running) {
    btn.className = "btn btn-danger";
    btn.innerHTML = 'Stop Auto-Scraping';
  } else {
    btn.className = "btn btn-success";
    btn.innerHTML = 'Start Auto-Scraping';
  }
}

function updateCountdownUI(secs) {
  const badge = document.getElementById("countdown-badge");
  const text = document.getElementById("countdown-text");
  if (appState.auto_running) {
    badge.style.display = "flex";
    const mins = Math.floor(secs / 60);
    const remSecs = secs % 60;
    const formatted = `${mins.toString().padStart(2, '0')}:${remSecs.toString().padStart(2, '0')}`;
    text.innerText = `Next Scrape: ${formatted}`;
  } else {
    text.innerText = `Next Scrape: Stopped`;
  }
}

function startLocalCountdown() {
  if (countdownTimer) clearInterval(countdownTimer);
  countdownTimer = setInterval(() => {
    if (appState.auto_running && appState.countdown_seconds > 0) {
      appState.countdown_seconds -= 1;
      updateCountdownUI(appState.countdown_seconds);
    }
  }, 1000);
}

function stopLocalCountdown() {
  if (countdownTimer) clearInterval(countdownTimer);
  updateCountdownUI(0);
}

// Log Terminal Appender
function appendLog(message, level = "INFO") {
  const consoleEl = document.getElementById("console-window");
  if (!consoleEl) return;

  const now = new Date();
  const timeStr = now.toTimeString().split(" ")[0];

  const line = document.createElement("div");
  line.className = `log-line ${level.toLowerCase()}`;
  line.innerHTML = `<span class="log-ts">[${timeStr}]</span> <span class="log-badge">[${level.toUpperCase()}]</span> ${escapeHtml(message)}`;

  consoleEl.appendChild(line);
  consoleEl.scrollTop = consoleEl.scrollHeight;
}

// UI Modals & Toasts
function showModal(title, body) {
  document.getElementById("modal-title").innerText = title;
  document.getElementById("modal-body").innerText = body;
  document.getElementById("modal-backdrop").classList.add("open");
}

function closeModal() {
  document.getElementById("modal-backdrop").classList.remove("open");
}

function showToast(msg, type = "info") {
  const container = document.getElementById("toast-container");
  if (!container) return;

  const toast = document.createElement("div");
  toast.className = `toast ${type}`;
  toast.innerText = msg;
  container.appendChild(toast);

  setTimeout(() => {
    toast.style.opacity = "0";
    toast.style.transform = "translateX(50px)";
    setTimeout(() => toast.remove(), 300);
  }, 3500);
}

// API Helper
async function postAPI(endpoint, data = {}) {
  try {
    const res = await fetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data)
    });
    return await res.json();
  } catch (err) {
    console.error(`API Error on ${endpoint}:`, err);
    return { status: "error", error: err.toString() };
  }
}

function escapeHtml(str) {
  if (!str) return "";
  return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}
