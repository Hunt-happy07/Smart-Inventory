# 📦 Smart Inventory Pro - Intelligent Offline Retail & POS Management System

> **A real-life, offline-first smart inventory management system engineered specifically for neighborhood retail shops, kirana stores, pharmacies, and supermarkets.**
> Built with 100% local persistence (SQLite), Machine Learning Demand Forecasting, Zero-Waste Expiry Markdown AI, Ghost Stock Pilferage Detection, and Speed POS Billing with WhatsApp Khata reminders.

---

## 🌟 Executive Summary & Unique Features

Smart Inventory Pro solves the acute problems of traditional offline stores with AI intelligence running entirely on your local counter computer—**with 0ms latency, zero internet requirement, and zero cloud subscription fees**.

### 🚀 Unique Innovations Not Present in Typical Inventory Systems:

1. **Zero-Waste Dynamic Markdown Engine (FEFO Profit Saver)**:
   - Evaluates remaining shelf life ($D_{\text{exp}}$) vs daily sales velocity ($V_{\text{daily}}$).
   - If stock will not sell out before expiry at standard prices, the AI dynamically suggests a staged clearance markdown (e.g., 20% to 50% OFF).
   - **Financial Impact**: Recovers up to 80% of invested cost and inventory margin rather than suffering a 100% loss by throwing expired items into the trash.

2. **Ghost Inventory & Pilferage / Shrinkage Detector**:
   - Detects when a historically fast-moving product abruptly records **0 sales for 7+ days** while positive stock is registered in the database.
   - Diagnoses shelf disconnects (misplaced stock behind other boxes, broken items, or shoplifting).
   - Generates a **60-Second Quick Cycle Count Checklist** with exact shelf locations (e.g. `Rack E-1`, `Aisle G-2`) for rapid staff reconciliation.

3. **Digital Smart Khata & 1-Click WhatsApp Reminder Generator**:
   - Over 40% of neighborhood retail sales happen on store credit ("Udhaar").
   - Replaces coffee-stained, torn paper notebooks with a tamper-proof digital ledger.
   - Enforces credit limits and generates a 1-click WhatsApp payment reminder link (`wa.me`) with a polite, pre-formatted breakdown of due balances and your store's UPI ID.

4. **Speed POS Billing Counter (Keyboard-First & Barcode-Gun Ready)**:
   - Designed for peak-hour rush counter traffic.
   - Full keyboard shortcuts: `F2` to Complete Bill, `Enter` to Add Scanned Item, `/` to Focus Search.
   - Real-time cart calculation (Subtotal, Tax/GST toggle, Item Clearance Discounts, Cash Tendered & Change Due calculator).
   - 58mm / 80mm thermal receipt printer view and A4 printable invoice.

5. **Machine Learning Demand Forecasting & Stockout Risk Analytics**:
   - Scikit-learn `RandomForestRegressor` with time-series feature engineering (day-of-week, month, day-of-year, lag-1, lag-7, lag-14, and rolling moving averages).
   - Dynamic forecast horizons (7, 14, 30 days).
   - Calculates **Days of Cover** (exact calendar date of stockout) and the **Optimal Reorder Quantity**:
     $$Q^* = \max\left(0, \lceil(\text{Lead Time Demand} + \text{Safety Stock}) - \text{Current Stock}\rceil\right)$$

6. **100% Offline-First Architecture & 1-Click Disaster Recovery**:
   - Runs locally on SQLite with zero external database server required.
   - 1-Click raw SQLite `.db` file backup to flash drive and JSON export for bookkeeping.

7. **Store Theft Protection & Loss Prevention Guard**:
   - AI evaluates high-theft risk items (small compact footprint, high value density) and flags EAS security tag requirements.
   - **POS Theft Reminder**: Displays security tag detacher badge on POS cards.
   - **Exit Gate Receipt Auditor**: Security guard bag-check tool that scans invoice barcodes and verifies authorized items.
   - **Aisle / Blindspot Heatmap**: Identifies store shelves with repeated pilferage to re-orient CCTV cameras and convex mirrors.

---

## 🛒 Offline Shopkeeper Problems Faced & Built-in Solutions

| # | Shopkeeper Problem | Real-World Pain Point | Built-in Solution in Smart Inventory Pro |
|---|-------------------|------------------------|------------------------------------------|
| **1** | **Silent Expiry & Dead-Loss Waste** | Perishables rot unnoticed on back shelves; 100% total loss of cost and margin. | **4-Tier FEFO Tracker & Dynamic Markdown Engine**: Alerts on near-expiry batches and automatically activates discount pricing in POS to liquidate stock safely. |
| **2** | **Peak-Hour Rush & Billing Bottlenecks** | Long queues in evening rush; manual math errors, wrong change returned, lost customers. | **Speed POS Terminal**: Instant USB/camera barcode lookup, F2 quick billing, automatic GST & change due calculation, and 58mm thermal receipts. |
| **3** | **Torn Paper Notebooks & Udhaar Chaos** | Forgotten customer debts, torn ledger pages, awkward calls to collect money. | **Smart Khata Ledger**: Tracks store credit directly during checkout with running balance, credit limits, and 1-click WhatsApp payment reminders. |
| **4** | **Bestseller Stockouts vs Dead Stock** | Running out of high-demand daily staples while cash is locked in dusty, unsellable boxes. | **AI Demand Forecasting**: Calculates daily sales velocity, days of cover, and auto-generates supplier purchase orders based on lead time. |
| **5** | **Ghost Stock & Inventory Shrinkage** | Computer says 15 in stock; customer wants it, but physical shelf is empty due to pilferage/damage. | **Ghost Stock Anomaly Detector**: Flags velocity stagnation and outputs a 60-second cycle count audit checklist for instant reconciliation. |
| **6** | **Internet Cuts & Cloud Downtime** | Cloud systems freeze when broadband drops; SaaS companies charge heavy recurring fees. | **100% Offline-First SQLite**: 0ms latency, zero internet requirement, accessible over local store Wi-Fi, with 1-click USB database backups. |

---

## 🏗️ System Architecture & Tech Stack

```
Smart Inventory Pro
├── Application Layer: Python 3.14 + Flask 3.1
│   ├── POS Billing Engine (pos.py)
│   ├── Zero-Waste Dynamic Markdown Engine (markdown_ai.py)
│   ├── Demand Forecasting AI (ml_model.py)
│   ├── Ghost Stock & Shrinkage Detector (anomaly_ai.py)
│   ├── Smart Khata Customer Credit Ledger (khata.py)
│   ├── Expiry & FEFO Intimation (expiry.py)
│   ├── Store Health Score (health_score.py)
│   └── Suppliers & Automated Purchase Orders (purchase.py)
│
├── Data Layer: SQLite 3 (inventory.db)
│   ├── products (SKU, barcode, rack_location, cost, price, stock, expiry, unit, discount_pct)
│   ├── sales_history (2+ years daily training data for ML forecasting)
│   ├── bills & bill_items (POS invoices and transactions)
│   ├── customers & customer_transactions (Khata credit accounts)
│   ├── suppliers & purchase_orders (Replenishment and lead times)
│   └── stock_adjustments (Audit & shrinkage discrepancy records)
│
└── Presentation Layer: Modern High-Contrast Responsive UI
    ├── Speed POS Terminal with Touch & Barcode controls
    ├── 58mm/80mm Thermal Receipt Generator (@media print)
    ├── Chart.js Dynamic Historical vs Predicted Demand Curves
    ├── JsBarcode EAN-13 & CODE128 Shelf Label Generator
    └── HTML5-QRCode Camera Scanner for phone/webcam input
```

---

## ⚡ Quick Start Guide (Run in VS Code)

### Prerequisites
- Python 3.10+ (Verified on Python 3.14)
- Packages: `Flask`, `scikit-learn`, `pandas`, `numpy`

### 1. Open Terminal in VS Code
Ensure your terminal is in the project directory:
```powershell
cd "d:\smart inventory pro\inventory_ai"
```

### 2. Verify / Install Dependencies
```powershell
python -m pip install -r requirements.txt
```

### 3. Initialize & Seed Database (Optional - Already Seeded)
```powershell
python seed_data.py
```

### 4. Run the Application
```powershell
python app.py
```

### 5. Access the Web Application
Open your browser and navigate to:
```
http://127.0.0.1:5000
```

---

## ⌨️ POS Keyboard Shortcuts Cheat Sheet

| Key Shortcut | Action |
|-------------|--------|
| `F2` | **Complete Sale & Open Printable Receipt** |
| `/` | **Instant Focus on Product & Barcode Search Bar** |
| `Enter` | **Add Scanned Barcode to Active Cart** |
| `Escape` | **Close Receipt Modal & Start New Bill** |

---

## 📱 Store Counter Setup Over Local Wi-Fi (No Internet Needed)
1. Keep the main shop PC running: `python app.py`.
2. Find the local IP of your PC using `ipconfig` (e.g. `192.168.1.15`).
3. Connect any Android tablet, iPad, or staff phone to the same shop Wi-Fi.
4. Open browser on tablet and type: `http://192.168.1.15:5000`.
5. Multiple staff members can scan barcodes and bill customers simultaneously!
