import os

# All settings can be overridden with environment variables so the same
# code works locally, on a server, or in a container.
DB_CONFIG = {
    "host": os.environ.get("DB_HOST", "localhost"),
    "port": int(os.environ.get("DB_PORT", "3306")),
    "user": os.environ.get("DB_USER", "root"),
    "password": os.environ.get("DB_PASSWORD", ""),
    "database": os.environ.get("DB_NAME", "krishisetu"),
    "charset": "utf8mb4",
}

# Business rules — kept identical to the constants in krishisetu.html
SLOT_CAPACITY = int(os.environ.get("SLOT_CAPACITY", "12"))
AVG_MIN_PER_FARMER = int(os.environ.get("AVG_MIN_PER_FARMER", "6"))
SLOTS = [
    "07:00–08:00", "08:00–09:00", "09:00–10:00", "10:00–11:00",
    "11:00–12:00", "12:00–13:00", "13:00–14:00", "14:00–15:00",
    "15:00–16:00", "16:00–17:00", "17:00–18:00",
]

# Demo admin PIN (matches the '1234' check in wireAdmin()).
# Move this to a real auth system before going to production.
ADMIN_PIN = os.environ.get("ADMIN_PIN", "1234")

SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-me")
