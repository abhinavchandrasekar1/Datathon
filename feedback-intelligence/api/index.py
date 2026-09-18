import sys
from pathlib import Path

# Add project root directory to sys.path so app and its dependencies can be imported
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app import app

# Export both app and application for broad WSGI/ASGI compatibility on Vercel
application = app
