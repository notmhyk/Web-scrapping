// Executive Sales Dashboard Client Logic (Read-Only Live Viewer & EOD Browser)

const DEFAULT_BRANCHES = [
  { id: "angeles", name: "Angeles City", grab_store_id: "grab_1", panda_store_id: "panda_1" },
  { id: "qc", name: "Quezon City", grab_store_id: "grab_2", panda_store_id: "panda_2" },
  { id: "caloocan", name: "Caloocan City", grab_store_id: "grab_3_caloocan", panda_store_id: "panda_3" },
  { id: "san_fernando", name: "San Fernando City", grab_store_id: "grab_4_san_fernando", panda_store_id: "panda_4" }
];

let currentViewMode = "live"; // 'live' or 'eod'

let viewerState = {
  branches: [],
  stores: [],
  total_sales: 0.0,
  last_updated: "Not Synced Yet",
  is_live_synced: false,
  eod_stores: [],
  eod_total_sales: 0.0,
  eod_last_updated: "Not recorded yet",
  eod_recorded: false
};

// Theme Handling (Default: Light Mode for Viewer)
function initTheme() {
  const savedTheme = localStorage.getItem("viewer_theme") || "light";
  applyTheme(savedTheme);
}

function toggleTheme() {
  const current = document.documentElement.getAttribute("data-theme") || "light";
  const next = current === "light" ? "dark" : "light";
  applyTheme(next);
  localStorage.setItem("viewer_theme", next);
}

function applyTheme(theme) {
  document.documentElement.setAttribute("data-theme", theme);
  const themeBtn = document.getElementById("btn-toggle-theme");
  if (themeBtn) {
    themeBtn.innerHTML = theme === "light" 
      ? '<span>Dark Mode</span>' 
      : '<span>Light Mode</span>';
    themeBtn.setAttribute("title", `Switch to ${theme === "light" ? "Dark" : "Light"} mode`);
  }
}

// Initialize on DOM load
document.addEventListener("DOMContentLoaded", () => {
  initTheme();
  updateLiveClock();
  setInterval(updateLiveClock, 1000);
  initDataFeed();
});

function updateLiveClock() {
  const now = new Date();
  const dateEl = document.getElementById("live-clock-date");
  const timeEl = document.getElementById("live-clock-time");
  if (dateEl) {
    const options = { weekday: "long", year: "numeric", month: "long", day: "numeric" };
    dateEl.innerText = now.toLocaleDateString(undefined, options);
  }
  if (timeEl) {
    timeEl.innerText = now.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: true });
  }
}

function setViewerTab(mode) {
  currentViewMode = mode;
  
  const liveBtn = document.getElementById("btn-view-live");
  const eodBtn = document.getElementById("btn-view-eod");

  if (liveBtn && eodBtn) {
    if (mode === "live") {
      liveBtn.classList.add("active");
      eodBtn.classList.remove("active");
    } else {
      eodBtn.classList.add("active");
      liveBtn.classList.remove("active");
    }
  }

  // Immediately re-render with active view mode
  updateViewerUI(viewerState);
}

function initDataFeed() {
  // 1. Initial fetch
  fetchLatestData();

  // 2. Server-Sent Events (SSE) for instant real-time pushes
  setupSSE();

  // 3. Fallback polling every 2.5 seconds
  setInterval(fetchLatestData, 2500);
}

function fetchLatestData() {
  fetch("/api/status")
    .then(res => {
      if (!res.ok) throw new Error("API status not available");
      return res.json();
    })
    .then(data => {
      updateViewerUI(data);
      setConnectionStatus(true, Boolean(data && data.is_live_synced));
    })
    .catch(() => {
      // Static fallback for Cloudflare Pages / hosted JSON
      fetch("./sales_feed.json")
        .then(res => res.json())
        .then(data => {
          updateViewerUI(data);
          setConnectionStatus(true, Boolean(data && data.is_live_synced));
        })
        .catch(() => {
          setConnectionStatus(false);
        });
    });
}

function setupSSE() {
  if (!window.EventSource) return;
  try {
    const evtSource = new EventSource("/api/events");
    evtSource.onopen = () => setConnectionStatus(true, viewerState.is_live_synced);
    evtSource.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data);
        if (payload.type === "scrape_finished" || payload.type === "status_update" || payload.type === "eod_updated") {
          fetchLatestData();
        }
      } catch (e) {}
    };
  } catch (err) {}
}

function setConnectionStatus(online, isLiveSynced = viewerState.is_live_synced) {
  const textEl = document.getElementById("viewer-status-text");
  const dotEl = document.getElementById("viewer-status-dot");
  if (textEl && dotEl) {
    if (!online) {
      textEl.innerText = "Reconnecting...";
      textEl.style.color = "var(--amber)";
      dotEl.className = "status-dot";
      dotEl.style.backgroundColor = "var(--amber)";
    } else if (!isLiveSynced) {
      textEl.innerText = "Not Synced";
      textEl.style.color = "var(--text-muted)";
      dotEl.className = "status-dot";
      dotEl.style.backgroundColor = "var(--text-dim)";
    } else {
      textEl.innerText = "Live Sync Active";
      textEl.style.color = "";
      dotEl.className = "status-dot pulse";
      dotEl.style.backgroundColor = "var(--emerald)";
    }
  }
}

function applyValueUpdate(el, newText) {
  if (!el) return;
  if (el.innerText !== newText) {
    el.innerText = newText;
    el.classList.remove("value-updated");
    void el.offsetWidth; // trigger reflow
    el.classList.add("value-updated");
    setTimeout(() => el.classList.remove("value-updated"), 800);
  }
}

function updateViewerUI(data) {
  if (!data) return;

  if (data.branches && data.branches.length > 0) {
    viewerState.branches = data.branches;
  } else if (!viewerState.branches || viewerState.branches.length === 0) {
    viewerState.branches = DEFAULT_BRANCHES;
  }

  if (data.stores && Array.isArray(data.stores)) {
    viewerState.stores = data.stores;
  }
  if (typeof data.total_sales === "number") {
    viewerState.total_sales = data.total_sales;
  }
  if (data.last_updated) {
    viewerState.last_updated = data.last_updated;
  }

  // EOD Data Cache
  if (data.eod_stores && Array.isArray(data.eod_stores)) {
    viewerState.eod_stores = data.eod_stores;
  }
  if (typeof data.eod_total_sales === "number") {
    viewerState.eod_total_sales = data.eod_total_sales;
  }
  if (data.eod_last_updated) {
    viewerState.eod_last_updated = data.eod_last_updated;
  }
  if (typeof data.eod_recorded === "boolean") {
    viewerState.eod_recorded = data.eod_recorded;
  }
  if (typeof data.is_live_synced === "boolean") {
    viewerState.is_live_synced = data.is_live_synced;
  }

  const isEodView = (currentViewMode === "eod");

  // Determine active dataset to display
  const activeStores = isEodView ? (viewerState.eod_stores.length > 0 ? viewerState.eod_stores : viewerState.stores) : viewerState.stores;
  const activeTotal = isEodView ? viewerState.eod_total_sales : viewerState.total_sales;
  const activeUpdated = isEodView ? viewerState.eod_last_updated : viewerState.last_updated;

  // Update Footer Mode Pill
  const modePill = document.getElementById("viewer-mode-pill");
  if (modePill) {
    if (isEodView) {
      modePill.innerText = "Mode: Yesterday's EOD Records";
      modePill.style.color = "#c084fc";
    } else {
      modePill.innerText = viewerState.is_live_synced ? "Mode: Live Operations (Today)" : "Mode: Not Synced Yet";
      modePill.style.color = viewerState.is_live_synced ? "#38bdf8" : "#94a3b8";
    }
  }

  // Update Summary Banner Title Label
  const summaryLabel = document.getElementById("viewer-summary-label");
  if (summaryLabel) {
    summaryLabel.innerText = isEodView ? "COMBINED TOTAL SALES (YESTERDAY EOD)" : "COMBINED TOTAL SALES (TODAY)";
  }

  // Update Grand Total Amount
  const totalEl = document.getElementById("viewer-total-sales");
  if (totalEl) {
    applyValueUpdate(totalEl, `₱ ${activeTotal.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`);
  }

  // Update Last Synced Badge
  const lastUpEl = document.getElementById("viewer-last-updated");
  if (lastUpEl && activeUpdated) {
    lastUpEl.innerText = `Last Updated: ${activeUpdated}`;
  }

  // Render 4 Branches with active dataset
  renderBranches(viewerState.branches, activeStores, isEodView);
}

function renderBranches(branches, stores, isEodView = false) {
  const container = document.getElementById("viewer-branches-grid");
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

    const grabStatus = getStatusBadge(grabStore, grabAmt, isEodView);
    const pandaStatus = getStatusBadge(pandaStore, pandaAmt, isEodView);
    const heroSubText = isEodView ? "Yesterday EOD Total" : (viewerState.is_live_synced ? "Live Aggregate" : "Not Synced Yet");

    let branchCardEl = document.getElementById(`viewer-card-${branch.id}`);

    if (!branchCardEl) {
      branchCardEl = document.createElement("div");
      branchCardEl.className = "branch-card";
      branchCardEl.id = `viewer-card-${branch.id}`;

      branchCardEl.innerHTML = `
        <!-- 1. Header: City Name -->
        <div class="branch-header">
          <div class="branch-title-wrap">
            <h3 class="branch-title">${branchNameClean}</h3>
          </div>
          <div class="branch-header-actions">
            <span class="card-status-pill active" id="viewer-hub-pill-${branch.id}">Active Hub</span>
          </div>
        </div>

        <!-- 2. Combined Total Sales (Hero) -->
        <div class="branch-total-hero">
          <div class="branch-total-meta">
            <span class="branch-total-title">TOTAL (GRAB + PANDA)</span>
            <span class="branch-total-sub" id="viewer-branch-sub-${branch.id}">${heroSubText}</span>
          </div>
          <div class="branch-total-main" id="viewer-branch-total-${branch.id}">${branchTotalFormatted}</div>
        </div>

        <!-- 3. Side-by-Side Sales Row (Left Grab | Right Foodpanda) -->
        <div class="platforms-side-by-side">
          
          <!-- Grab Mini-Panel -->
          <div class="platform-mini-panel grab-mini" id="viewer-mini-${grabStore.id}">
            <div class="mini-panel-header">
              <span class="platform-tag grab">GRAB</span>
              <span class="card-status-pill ${grabStatus.cls}" id="viewer-status-pill-${grabStore.id}">${grabStatus.text}</span>
            </div>
            <div class="mini-sales-figure ${grabAmt > 0 ? 'positive' : 'zero'}" id="viewer-sales-figure-${grabStore.id}">
              ${grabAmtFormatted}
            </div>
          </div>

          <!-- Foodpanda Mini-Panel -->
          <div class="platform-mini-panel panda-mini" id="viewer-mini-${pandaStore.id}">
            <div class="mini-panel-header">
              <span class="platform-tag foodpanda">FOODPANDA</span>
              <span class="card-status-pill ${pandaStatus.cls}" id="viewer-status-pill-${pandaStore.id}">${pandaStatus.text}</span>
            </div>
            <div class="mini-sales-figure ${pandaAmt > 0 ? 'positive' : 'zero'}" id="viewer-sales-figure-${pandaStore.id}">
              ${pandaAmtFormatted}
            </div>
          </div>

        </div>
      `;
      container.appendChild(branchCardEl);
    } else {
      // Update existing branch card
      const bSubEl = document.getElementById(`viewer-branch-sub-${branch.id}`);
      if (bSubEl) bSubEl.innerText = heroSubText;

      const bTotalEl = document.getElementById(`viewer-branch-total-${branch.id}`);
      if (bTotalEl) applyValueUpdate(bTotalEl, branchTotalFormatted);

      // Update Grab row
      const grabSalesEl = document.getElementById(`viewer-sales-figure-${grabStore.id}`);
      if (grabSalesEl) {
        applyValueUpdate(grabSalesEl, grabAmtFormatted);
        grabSalesEl.className = `mini-sales-figure ${grabAmt > 0 ? 'positive' : 'zero'}`;
      }
      const grabStatusEl = document.getElementById(`viewer-status-pill-${grabStore.id}`);
      if (grabStatusEl) {
        grabStatusEl.innerText = grabStatus.text;
        grabStatusEl.className = `card-status-pill ${grabStatus.cls}`;
      }

      // Update Panda row
      const pandaSalesEl = document.getElementById(`viewer-sales-figure-${pandaStore.id}`);
      if (pandaSalesEl) {
        applyValueUpdate(pandaSalesEl, pandaAmtFormatted);
        pandaSalesEl.className = `mini-sales-figure ${pandaAmt > 0 ? 'positive' : 'zero'}`;
      }
      const pandaStatusEl = document.getElementById(`viewer-status-pill-${pandaStore.id}`);
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
  if (store.status === "not_synced" || (!viewerState.is_live_synced && amt === 0 && store.status !== "scraping" && store.status !== "retrying")) {
    return { cls: "idle", text: "Not Synced" };
  }
  if (store.status === "active" || (store.last_success && amt > 0)) {
    return { cls: "active", text: "Active" };
  } else if (store.status === "retrying" || store.status === "scraping") {
    return { cls: "retrying", text: "Updating..." };
  } else if (store.last_success === false || amt === 0) {
    return { cls: "check", text: "0 / Check" };
  }
  return { cls: "idle", text: "Not Synced" };
}
