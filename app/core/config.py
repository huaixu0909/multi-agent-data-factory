from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = BASE_DIR / "data"
DATABASE_FILE = DATA_DIR / "factory.db"
APP_VERSION = "1.5.0"
