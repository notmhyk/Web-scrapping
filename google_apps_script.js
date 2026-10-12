/**
 * =========================================================================
 * GOOGLE APPS SCRIPT: SALES REPORT AUTOMATIC HOURLY & EOD SYNC
 * =========================================================================
 * Sheet: "Sales Report - AirKitchen"
 *
 * HOW TO SET UP (Takes 2 minutes):
 * 1. In your Google Sheet, click "Extensions" in the top menu -> "Apps Script".
 * 2. Delete whatever is in the editor, and paste ALL the code from this file.
 * 3. Click "Save" (disk icon or Ctrl+S).
 * 4. Click the blue "Deploy" button at the top right -> "New deployment".
 * 5. Click the gear icon next to "Select type" -> choose "Web app".
 *    - Description: Sales Scraper Webhook
 *    - Execute as: Me (your Google email)
 *    - Who has access: Anyone
 * 6. Click "Deploy".
 *    (Google may ask for authorization: Click "Authorize access" -> choose your Google
 *     account -> Click "Advanced" -> Click "Go to Sales Scraper (unsafe)" -> Click "Allow").
 * 7. Copy the "Web app URL" (it looks like: https://script.google.com/macros/s/.../exec).
 * 8. Paste this URL into your Scraper Dashboard (in config.json or Settings).
 * =========================================================================
 */

// Exact coordinate map matching the "Sales Report - AirKitchen" sheet layout
const TABLE_COORDINATES = {
  // Block 1 (Columns B to E)
  "1:00 AM":  { headerRow: 12, branchStartRow: 14, pandaCol: 3,  grabCol: 4,  dateCol: 3 },
  "2:00 AM":  { headerRow: 20, branchStartRow: 22, pandaCol: 3,  grabCol: 4,  dateCol: 3 },
  "3:00 AM":  { headerRow: 28, branchStartRow: 30, pandaCol: 3,  grabCol: 4,  dateCol: 3 },
  "4:00 AM":  { headerRow: 36, branchStartRow: 38, pandaCol: 3,  grabCol: 4,  dateCol: 3 },
  "5:00 AM":  { headerRow: 44, branchStartRow: 46, pandaCol: 3,  grabCol: 4,  dateCol: 3 },

  // Block 2 (Columns H to K)
  "6:00 AM":  { headerRow: 4,  branchStartRow: 6,  pandaCol: 9,  grabCol: 10, dateCol: 9 },
  "7:00 AM":  { headerRow: 12, branchStartRow: 14, pandaCol: 9,  grabCol: 10, dateCol: 9 },
  "8:00 AM":  { headerRow: 20, branchStartRow: 22, pandaCol: 9,  grabCol: 10, dateCol: 9 },
  "9:00 AM":  { headerRow: 28, branchStartRow: 30, pandaCol: 9,  grabCol: 10, dateCol: 9 },
  "10:00 AM": { headerRow: 28, branchStartRow: 30, pandaCol: 9,  grabCol: 10, dateCol: 9 }, // Covers 10:00 AM header in slot 4
  "11:00 AM": { headerRow: 36, branchStartRow: 38, pandaCol: 9,  grabCol: 10, dateCol: 9 },
  "12:00 PM": { headerRow: 44, branchStartRow: 46, pandaCol: 9,  grabCol: 10, dateCol: 9 },
  "12:00 AM": { headerRow: 44, branchStartRow: 46, pandaCol: 9,  grabCol: 10, dateCol: 9 }, // In case labeled 12:00 AM at K44

  // Block 3 (Columns M to P)
  "1:00 PM":  { headerRow: 4,  branchStartRow: 6,  pandaCol: 14, grabCol: 15, dateCol: 14 },
  "2:00 PM":  { headerRow: 12, branchStartRow: 14, pandaCol: 14, grabCol: 15, dateCol: 14 },
  "3:00 PM":  { headerRow: 20, branchStartRow: 22, pandaCol: 14, grabCol: 15, dateCol: 14 },
  "4:00 PM":  { headerRow: 28, branchStartRow: 30, pandaCol: 14, grabCol: 15, dateCol: 14 },
  "5:00 PM":  { headerRow: 36, branchStartRow: 38, pandaCol: 14, grabCol: 15, dateCol: 14 },
  "6:00 PM":  { headerRow: 44, branchStartRow: 46, pandaCol: 14, grabCol: 15, dateCol: 14 },

  // Block 4 (Columns S to V)
  "7:00 PM":  { headerRow: 4,  branchStartRow: 6,  pandaCol: 20, grabCol: 21, dateCol: 20 },
  "8:00 PM":  { headerRow: 12, branchStartRow: 14, pandaCol: 20, grabCol: 21, dateCol: 20 },
  "9:00 PM":  { headerRow: 20, branchStartRow: 22, pandaCol: 20, grabCol: 21, dateCol: 20 },
  "10:00 PM": { headerRow: 28, branchStartRow: 30, pandaCol: 20, grabCol: 21, dateCol: 20 },
  "11:00 PM": { headerRow: 36, branchStartRow: 38, pandaCol: 20, grabCol: 21, dateCol: 20 },

  // THE EOD TABLE (S44: Cells S44 to V50)
  "EOD":      { headerRow: 44, branchStartRow: 46, pandaCol: 20, grabCol: 21, dateCol: 20 }
};

// Fixed Branch Order in each table
const BRANCH_ORDER = [
  "ANGELES CITY",
  "QUEZON CITY",
  "CALOOCAN CITY",
  "SAN FERNANDO"
];

/**
 * Handles incoming POST requests from Python scraper.
 */
function doPost(e) {
  try {
    if (!e || !e.postData || !e.postData.contents) {
      return jsonResponse({ status: "error", message: "No data payload received" }, 400);
    }

    const payload = JSON.parse(e.postData.contents);
    const ss = SpreadsheetApp.getActiveSpreadsheet();
    const sheetName = payload.sheet_name || "Sales Report - AirKitchen";
    const sheet = ss.getSheetByName(sheetName);

    if (!sheet) {
      return jsonResponse({
        status: "error",
        message: `Sheet tab "${sheetName}" was not found in spreadsheet. Check tab name!`
      }, 404);
    }

    const isEOD = payload.is_eod === true;
    let timeSlot = payload.time_slot || (isEOD ? "EOD" : "1:00 PM");
    const dateStr = payload.date_str || Utilities.formatDate(new Date(), Session.getScriptTimeZone(), "MMMM d, yyyy");
    const branches = payload.branches || [];

    // Find table target
    let target = isEOD ? TABLE_COORDINATES["EOD"] : (TABLE_COORDINATES[timeSlot] || findTableByHeader(sheet, timeSlot));

    if (!target) {
      // Fallback normalization
      const normSlot = normalizeTimeSlot(timeSlot);
      target = TABLE_COORDINATES[normSlot] || findTableByHeader(sheet, normSlot);
    }

    if (!target) {
      return jsonResponse({
        status: "error",
        message: `Could not determine table location for time slot "${timeSlot}".`
      }, 400);
    }

    // 1. Update Date Header Cell
    try {
      sheet.getRange(target.headerRow, target.dateCol).setValue(dateStr);
    } catch (err) {
      Logger.log("Notice on date cell update: " + err);
    }

    // 2. Update Branch Rows (Panda & Grab columns)
    // Map branch data by upper name
    const dataMap = {};
    branches.forEach(b => {
      const key = (b.name || b.id || "").toUpperCase().trim();
      dataMap[key] = b;
    });

    const updatedBranches = [];
    for (let i = 0; i < BRANCH_ORDER.length; i++) {
      const bName = BRANCH_ORDER[i];
      const row = target.branchStartRow + i;

      // Find matching branch payload
      let bData = dataMap[bName];
      if (!bData) {
        // Partial fuzzy match
        for (const k in dataMap) {
          if (bName.includes(k) || k.includes(bName) || (bName.includes("SAN") && k.includes("FERNANDO"))) {
            bData = dataMap[k];
            break;
          }
        }
      }

      const pandaVal = bData ? Number(bData.panda || 0) : 0;
      const grabVal = bData ? Number(bData.grab || 0) : 0;

      // Set Panda Column
      sheet.getRange(row, target.pandaCol).setValue(pandaVal);
      // Set Grab Column
      sheet.getRange(row, target.grabCol).setValue(grabVal);

      updatedBranches.push({ branch: bName, row: row, panda: pandaVal, grab: grabVal });
    }

    return jsonResponse({
      status: "success",
      message: `Updated table for [${isEOD ? "EOD (S44)" : timeSlot}] on date ${dateStr}`,
      table: {
        headerRow: target.headerRow,
        branchStartRow: target.branchStartRow,
        pandaCol: target.pandaCol,
        grabCol: target.grabCol
      },
      updated: updatedBranches
    });

  } catch (error) {
    return jsonResponse({
      status: "error",
      message: error.toString(),
      stack: error.stack
    }, 500);
  }
}

/**
 * Normalizes time string formats (e.g., '1pm' -> '1:00 PM', '13:00' -> '1:00 PM').
 */
function normalizeTimeSlot(raw) {
  if (!raw) return "1:00 PM";
  let s = raw.toString().trim().toUpperCase();
  if (s.includes("EOD")) return "EOD";
  
  // Format variations
  if (/^(\d{1,2}):00\s*(AM|PM)$/.test(s)) return s;
  if (/^(\d{1,2})\s*(AM|PM)$/.test(s)) {
    const parts = s.match(/^(\d{1,2})\s*(AM|PM)$/);
    return `${parts[1]}:00 ${parts[2]}`;
  }
  return s;
}

/**
 * Dynamic fallback: Scans headers in rows 4, 12, 20, 28, 36, 44 to find exact time text.
 */
function findTableByHeader(sheet, timeStr) {
  const searchRows = [4, 12, 20, 28, 36, 44];
  const searchCols = [5, 11, 16, 22]; // E, K, P, V

  for (let r of searchRows) {
    for (let c of searchCols) {
      const val = sheet.getRange(r, c).getDisplayValue().trim().toUpperCase();
      if (val && (val === timeStr.toUpperCase() || val.includes(timeStr.toUpperCase()))) {
        let pCol = c - 2;
        let gCol = c - 1;
        let dCol = c - 2;
        return {
          headerRow: r,
          branchStartRow: r + 2,
          pandaCol: pCol,
          grabCol: gCol,
          dateCol: dCol
        };
      }
    }
  }
  return null;
}

/**
 * Health check endpoint for browser verification.
 */
function doGet(e) {
  return HtmlService.createHtmlOutput(
    "<div style='font-family:sans-serif;padding:30px;text-align:center;background:#0f172a;color:#f8fafc;border-radius:12px;margin:40px auto;max-width:600px;'>" +
    "<h2 style='color:#38bdf8;'>Sales Report Scraper Webhook is ACTIVE!</h2>" +
    "<p style='color:#94a3b8;font-size:15px;'>This Webhook is ready to receive automated hourly and EOD updates from your sales scraper.</p>" +
    "<p style='color:#10b981;font-weight:bold;'>Status: 200 OK</p>" +
    "</div>"
  );
}

function jsonResponse(obj, code) {
  return ContentService.createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}

/**
 * Manual Test Function: Run this directly in Apps Script to verify it updates your sheet!
 */
function testManualSync() {
  const testPayload = {
    postData: {
      contents: JSON.stringify({
        sheet_name: "Sales Report - AirKitchen",
        is_eod: false,
        time_slot: "1:00 PM",
        date_str: "October 12, 2026",
        branches: [
          { name: "ANGELES CITY", panda: 4926, grab: 37376.80 },
          { name: "QUEZON CITY", panda: 3400, grab: 18500 },
          { name: "CALOOCAN CITY", panda: 6200, grab: 25100 },
          { name: "SAN FERNANDO", panda: 2800, grab: 14200 }
        ]
      })
    }
  };
  const result = doPost(testPayload);
  Logger.log("Result: " + result.getContent());
}

/**
 * Test EOD Sync directly to cell S44!
 */
function testEODSync() {
  const testPayload = {
    postData: {
      contents: JSON.stringify({
        sheet_name: "Sales Report - AirKitchen",
        is_eod: true,
        time_slot: "EOD",
        date_str: "October 11, 2026",
        branches: [
          { name: "ANGELES CITY", panda: 5100, grab: 41200 },
          { name: "QUEZON CITY", panda: 3600, grab: 19800 },
          { name: "CALOOCAN CITY", panda: 6500, grab: 26400 },
          { name: "SAN FERNANDO", panda: 3000, grab: 15300 }
        ]
      })
    }
  };
  const result = doPost(testPayload);
  Logger.log("EOD Result: " + result.getContent());
}
