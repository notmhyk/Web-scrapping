# Multi-Branch Sales Scraper Dashboard (4 Consolidated Branches / 8 Dedicated Browsers)

An automated application designed to scrape, aggregate, and log real-time sales data across **4 Consolidated Merchant Hubs** (8 dedicated browser windows):

### 4 City Branches:
1. **Angeles City Branch**:
   - Grab: `https://merchant.grab.com/portal` (`grab_1`)
   - Foodpanda: `https://partner.foodpanda.com/dashboard?vendor=FP_PH;klbr` (`panda_1`)
2. **Quezon City Branch**:
   - Grab: `https://merchant.grab.com/portal` (`grab_2`)
   - Foodpanda: `https://partner.foodpanda.com/dashboard?vendor=FP_PH;vt23` (`panda_2`)
3. **Caloocan City Branch**:
   - Grab: `https://merchant.grab.com/finances?page=ov&startDate={CURRENT_DATE}&endDate={CURRENT_DATE}&grabID=3b7229f2-4784-4fab-86fd-3fa97583b0d5` (`grab_3_caloocan`)
   - Foodpanda: `https://partner.foodpanda.com/dashboard?vendor=FP_PH;kc5x` (`panda_3`)
4. **San Fernando City Branch**:
   - Grab: Calculated automatically: `Overall Grab Finances Total - Caloocan Grab Sales` (`grab_4_san_fernando`)
   - Foodpanda: Scraped directly from dedicated browser (`panda_4`): `https://partner.foodpanda.com/dashboard?vendor=FP_PH;kc5x`

---

## Stationary 2x4 Screen Grid Tiling
- **Top Row (4 Windows)**: Angeles Grab, QC Grab, Caloocan Grab, San Fernando Grab
- **Bottom Row (4 Windows)**: Angeles Panda, QC Panda, Caloocan Panda, San Fernando Panda
- All 8 windows stay locked and non-overlapping on your screen without moving or closing during scrapes!

---

## Branch Computation & Grand Totals
- **Branch Total**:
  $$\text{Branch Sales} = \text{Branch Grab} + \text{Branch Foodpanda}$$
- **Grand Total**:
  $$\text{Grand Total} = \sum_{i=1}^4 \text{Branch Sales}_i$$

---

## Running the Web Dashboard
```bash
python web_app.py
```
Open **`http://localhost:5000`** in your browser.
1. Click **`Launch All 8 Browsers`** (tiles top 4 Grab and bottom 4 Panda).
2. Log in once per browser (saved permanently).
3. Use **`Train Panda`** on each branch to click the sales element on the Foodpanda page.
4. Click **`Scrape All 4 Branches`** (or scrape individual branches) to get real-time totals!
