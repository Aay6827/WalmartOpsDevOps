import os

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./walmartops.db")
SERVICE_NAME = os.getenv("SERVICE_NAME", "fulfilment-api")
APP_VERSION = os.getenv("APP_VERSION", "1.0.0")
LOW_STOCK_THRESHOLD = int(os.getenv("LOW_STOCK_THRESHOLD", "5"))
