"""
Main FastAPI application — StockSense v3.0
Smart Inventory Forecasting & Retail Management System
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
from app.routes.forecast_routes import router as forecast_router
from app.routes.reorder_routes  import router as reorder_router
from app.routes.upload_routes   import router as upload_router
from app.routes.billing_routes  import router as billing_router
from app.routes.product_routes  import router as product_router
from app.routes.report_routes   import router as report_router
from app.routes.auth_routes     import router as auth_router

from app.database.database import init_db, SessionLocal
from config import settings
import logging, sys, glob, os

logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout), logging.FileHandler('app.log')]
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="StockSense — Smart Inventory & Retail Management API",
    version="3.0.0",
    description=(
        "AI-powered inventory forecasting, live billing POS, EOQ-based reorder planning, "
        "and retail analytics for Indian SMBs. Supports Prophet, XGBoost, Random Forest."
    ),
    docs_url="/docs",
    redoc_url="/redoc"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


from fastapi import Request
from app.auth.utils import decode_access_token
from app.database.database import current_tenant_id

@app.middleware("http")
async def tenant_middleware(request: Request, call_next):
    try:
        auth = request.headers.get("Authorization")
        if auth and auth.startswith("Bearer "):
            token = auth.split(" ")[1]
            from app.auth.utils import decode_access_token
            payload = decode_access_token(token)
            if payload and "sub" in payload:
                current_tenant_id.set(payload["sub"])
        
        response = await call_next(request)
        return response
    except Exception as e:
        logger.error(f"Middleware error: {e}")
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=500, content={"detail": f"Internal Server Error: {str(e)}"})

from fastapi import Depends
from app.routes.auth_routes import _get_current_user

app.include_router(forecast_router, dependencies=[Depends(_get_current_user)])
app.include_router(reorder_router, dependencies=[Depends(_get_current_user)])
app.include_router(upload_router, dependencies=[Depends(_get_current_user)])
app.include_router(billing_router, dependencies=[Depends(_get_current_user)])
app.include_router(product_router, dependencies=[Depends(_get_current_user)])
app.include_router(report_router, dependencies=[Depends(_get_current_user)])
app.include_router(auth_router)

# Serve frontend static files
frontend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'frontend'))
if os.path.isdir(frontend_dir):
    app.mount('/app', StaticFiles(directory=frontend_dir, html=True), name='frontend')


@app.on_event("startup")
async def startup_event():
    logger.info("StockSense v3.0 starting...")
    try:
        # Create tables if they don't exist
        init_db()
        logger.info("Ready")


    except Exception as e:
        logger.error(f"Startup failed: {e}")
        raise


@app.get("/")
def home():
    return {
        "name": "StockSense API",
        "version": "3.0.0",
        "status": "healthy",
        "docs": "/docs",
        "endpoints": {

            "products":  "/products/ | /products/dashboard/summary | /products/alerts",
            "billing":   "/billing/ | /billing/stats",
            "forecast":  "/forecast/{product_name}",
            "reorder":   "/reorder/{product_name}",
            "upload":    "/upload/  (POST=import CSV, DELETE /upload/reset=clear all)",
            "reports":   "/reports/inventory/excel | /reports/sales/excel | /reports/billing/excel | /reports/forecast/excel | /reports/reorder/excel",
            "manual":    "/products/manual-sale | /products/manual-sales",
        }
    }


@app.get("/health")
def health_check():
    return {"status": "healthy", "version": "3.0.0", "database": "connected"}
