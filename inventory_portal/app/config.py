import os


class Config:
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL", "sqlite:///inventory.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    # If set, every /api request (except /api/health) must send X-API-Key.
    ADMIN_API_KEY = os.environ.get("ADMIN_API_KEY")
    OFF_BASE_URL = os.environ.get("OFF_BASE_URL", "https://world.openfoodfacts.org")
    OFF_TIMEOUT = float(os.environ.get("OFF_TIMEOUT", "8"))
    OFF_USER_AGENT = os.environ.get(
        "OFF_USER_AGENT", "InventoryAdminPortal/1.0 (admin@example.com)"
    )
    LOW_STOCK_THRESHOLD = int(os.environ.get("LOW_STOCK_THRESHOLD", "5"))


class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    ADMIN_API_KEY = None
