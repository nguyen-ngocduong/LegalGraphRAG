from pathlib import Path
import yaml
import os

from dotenv import load_dotenv
load_dotenv()
# Đường dẫn đến config.yaml
CONFIG_PATH = Path(__file__).parent / "config.yaml"
def load_config():
    #Đọc file config.yaml
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

config = load_config()

# === Duong dan den thu muc data ===

RAW_PATH = config['PATH']['RAW_PATH']
PROCESSED_PATH = config['PATH']['PROCESSED_PATH']
CLEAN_PATH = config['PATH']['CLEANED_PATH']
CHUNK_PATH = config['PATH']['CHUNK_PATH']
GRAPH_PATH = config['PATH']['GRAPH_PATH']
# === GEMINI API KEY ===

config['KEY']['GEMINI_API_KEY'] = os.getenv('GEMINI_API_KEY')

# === MODEL EMBEDDING ===
MODEL_NAME = config['MODEL_NAME']['NAME']
MODEL_GRAPH = config['MODEL_NAME']['GRAPH']
# CHUNK
MIN_CHUNK_SIZE = config['CHUNK']['MIN_CHUNK_SIZE']
MAX_CHUNK_SIZE = config['CHUNK']['MAX_CHUNK_SIZE']
CHUNK_OVERLAP = config['CHUNK']['OVERLAP']