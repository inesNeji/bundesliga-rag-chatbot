import requests
import re
import logging
import sys
from urllib.parse import quote_plus

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("logs/debug.log"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

SESSION = requests.Session()
SESSION.headers.update({'User-Agent': 'Bundesliga-RAG-Chatbot/1.0'})