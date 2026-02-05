# config.py

# Default threshold values (will be overwritten by the database if saved settings exist)
DEFAULT_THRESHOLDS = {
    'drum_wear_percent': 80,
    'roller_wear_percent': 75,
    'paper_jams_count': 20,
    'fuser_temperature': 210,
    'confidence_threshold': 0.70
}

DB_PATH = 'printer_system.db'
MODELS_DIR = 'models'