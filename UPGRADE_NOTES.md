# StockSense v3.0 — Upgrade Notes

## What's New in This Upgrade

### New Backend Routes

| Route | Method | Description |
|-------|--------|-------------|
| `/billing/` | POST | Create a bill, deduct stock, record sales |
| `/billing/` | GET | List all bills with pagination |
| `/billing/stats` | GET | Today's and total revenue |
| `/billing/{id}` | GET | Full bill detail with line items |
| `/products/` | GET | List products with category filter |
| `/products/` | POST | Create a new product |
| `/products/{id}` | PUT | Update product details / stock |
| `/products/{id}` | DELETE | Soft-delete (deactivate) product |
| `/products/categories` | GET | All distinct categories |
| `/products/manual-sale` | POST | Log a manual daily sale |
| `/products/manual-sales` | GET | View manual sales log |
| `/products/alerts` | GET | Fetch stock alerts |
| `/products/alerts/{id}/read` | POST | Mark alert as read |
| `/products/dashboard/summary` | GET | All KPI data for dashboard |

### New Database Tables
- `bills` — invoice headers with GST, discount, payment method
- `billing_items` — line items per bill
- `stock_alerts` — auto-generated low-stock / out-of-stock alerts
- `manual_sales_entries` — manual sales log for sellers without CSV
- Extended `products` with `cost_price`, `unit`, `description`, `is_active`
- Extended `users` with `store_name`, `phone`

### New Frontend Pages
1. **Dashboard** — KPI cards, 7-day sales chart, category doughnut, top products
2. **Products** — Full CRUD with search + category filter
3. **Billing Desk** — Live POS with cart, GST, discount, payment method
4. **Bill History** — All invoices with detail modal
5. **AI Forecast** — Product + days selection, Chart.js visualization, metrics
6. **Reorder Plan** — EOQ + dynamic safety stock output
7. **Upload CSV** — Drag & drop with result summary
8. **Manual Entry** — Daily sales entry form + log table
9. **Alerts** — Stock alerts with mark-as-read

## Running the System

```bash
cd backend
pip install -r requirements.txt
python run.py
```

Then open `frontend/index.html` in your browser.
API runs at http://localhost:8000
API docs at http://localhost:8000/docs
