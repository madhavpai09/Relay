from pathlib import Path
import os

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

PORT = int(os.getenv("PORT", "8000"))
GITHUB_WEBHOOK_SECRET = os.getenv("GITHUB_WEBHOOK_SECRET", "")
DATA_DIR = BASE_DIR / "data"
DATABASE_PATH = DATA_DIR / "relay.sqlite"
DEFAULT_PIPELINE_FILE = ".relay.yml"
