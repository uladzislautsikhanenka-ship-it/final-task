TELEGRAM_BOT_TOKEN = "8412461303:AAEoJybmDJeyzfeGOdrqQWBZJX8rnvL3E-A"
ADMIN_CHAT_ID = "" 

ODOO_URL = "http://localhost:8017"
ODOO_DB = "tennis_club_clean"

ODOO_USERNAME = "admin"
ODOO_PASSWORD = "admin123"
DEFAULT_SPORTS_CENTER_ID = ""

MANAGER_USER_ID = 2  # ID=2


WEBAPP_URL = "https://6v7876sr-6000.euw.devtunnels.ms/"
USE_WEBAPP = True  

def load_config():
    return {
        'TELEGRAM_BOT_TOKEN': TELEGRAM_BOT_TOKEN,
        'ADMIN_CHAT_ID': ADMIN_CHAT_ID,
        'ODOO_URL': ODOO_URL,
        'ODOO_DB': ODOO_DB,
        'ODOO_USERNAME': ODOO_USERNAME,
        'ODOO_PASSWORD': ODOO_PASSWORD,
        'DEFAULT_SPORTS_CENTER_ID': DEFAULT_SPORTS_CENTER_ID,
        'MANAGER_USER_ID': MANAGER_USER_ID,
        'WEBAPP_URL': WEBAPP_URL,
        'USE_WEBAPP': USE_WEBAPP,
    }


def validate_config(cfg: dict) -> None:
    missing = [
        key for key in ['TELEGRAM_BOT_TOKEN', 'ODOO_URL', 'ODOO_DB', 'ODOO_USERNAME', 'ODOO_PASSWORD']
        if not cfg.get(key)
    ]
    if missing:
        raise RuntimeError(f"Missing required config values: {', '.join(missing)}")


