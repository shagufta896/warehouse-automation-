# 📊 AI-Powered Inventory Management System

## MCA Final Year Project

An intelligent inventory management system using machine learning for demand forecasting and automated reorder recommendations.

## 🌟 Key Features

- **Multi-Model Forecasting**: Prophet, Random Forest, Gradient Boosting
- **Automated Reorder Calculations**: EOQ optimization + Dynamic safety stock
- **Database Integration**: SQLAlchemy ORM with support for SQLite/PostgreSQL/MySQL
- **Real-time Dashboard**: Interactive web interface with visualizations
- **Model Performance Tracking**: MAE, RMSE, MAPE metrics
- **RESTful API**: FastAPI with automatic Swagger documentation

## 🏗️ Project Structure

```
backend/
├── app/
│   ├── database/
│   │   ├── models.py          # Database models
│   │   ├── database.py        # DB connection
│   │   └── crud.py            # CRUD operations
│   ├── ml/
│   │   ├── train_model.py     # ML training
│   │   ├── forecast_service.py # Forecasting
│   │   └── reorder_service.py  # Reorder logic
│   └── routes/                # API endpoints
├── config.py                  # Configuration
├── requirements.txt
└── .env.example

frontend/
└── index.html                 # Dashboard UI
```

## 🚀 Quick Start

### 1. Setup Environment

```bash
cd backend

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Start Application

The easiest way to start the system is using the included run script. This will start the backend server and automatically open the frontend in your web browser:

```bash
cd backend
python run.py
```

This starts the application at: **http://127.0.0.1:8000/app/**

Alternatively, to run the server manually:
```bash
cd backend
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

API Documentation: http://127.0.0.1:8000/docs

## 📊 Usage

1. **Upload CSV**: Upload inventory data file
2. **Select Product**: Choose from dropdown
3. **Analyze**: Get forecast and reorder recommendations

## 📈 Machine Learning Models

- **Prophet**: Time series with seasonality
- **Random Forest**: Ensemble learning
- **Gradient Boosting**: Sequential ensemble

Best model automatically selected based on MAE.

## 🗄️ Database Schema

- **Products**: Product master data
- **Sales History**: Transaction records
- **Forecast Results**: Cached predictions
- **Model Metrics**: Performance tracking

## 📝 API Endpoints

- `GET /forecast/{product_name}` - Generate forecast
- `GET /reorder/{product_name}` - Calculate reorder
- `POST /upload/` - Upload CSV data
- `GET /forecast/products` - List products

## 🔧 Configuration

Create `.env` file from `.env.example`:

```bash
cp .env.example .env
```

Default SQLite database works out of the box.

## 📚 For MCA Report

Covers: ML algorithms, system design, database architecture, API development, frontend development, testing, and deployment.

---

**Author**: Your Name | MCA 2026
