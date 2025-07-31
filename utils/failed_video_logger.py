# utils/failed_video_logger.py
import json
import os
from datetime import datetime

LOG_FILE = 'failed_videos.json'

def get_log_path():
    # This function should be kept in sync with how other helpers find the project root
    script_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(script_dir, '..', LOG_FILE)

def log_failed_videos(videos):
    """Logs a list of videos that failed to process."""
    log_path = get_log_path()
    try:
        with open(log_path, 'r+', encoding='utf-8') as f:
            log_data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        log_data = {}

    for video in videos:
        video_id = video['id']
        log_data[video_id] = {
            'title': video['title'],
            'failed_at': datetime.now().isoformat()
        }
    
    with open(log_path, 'w', encoding='utf-8') as f:
        json.dump(log_data, f, ensure_ascii=False, indent=4)

def load_failed_videos():
    """Loads the set of failed video IDs."""
    log_path = get_log_path()
    try:
        with open(log_path, 'r', encoding='utf-8') as f:
            log_data = json.load(f)
            return set(log_data.keys())
    except (FileNotFoundError, json.JSONDecodeError):
        return set()

def clear_log():
    """Clears the log file."""
    log_path = get_log_path()
    if os.path.exists(log_path):
        os.remove(log_path)
