import requests
import shutil
import os
from datetime import datetime

# === CONFIG ===
EPG_URL = "- name: Download EPG XML
  run: |
    curl -L "https://dl.dropboxusercontent.com/scl/fi/nyucb2eh02jddrbfz94r7/epg_ripper_US1.xml?rlkey=vd32vbxaedz07sqyu27fuurqp&st=d57xq7" -o epg.xml
"  # Your source EPG URL
OUTPUT_FILE = "epg.xml"
BACKUP_FILE = f"guide_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xml"

# === FUNCTIONALITY ===

def fetch_epg(url, output_file, backup=True):
    try:
        print(f"[INFO] Downloading EPG from: {url}")
        response = requests.get(url, timeout=15)
        response.raise_for_status()

        # Backup current file if exists
        if os.path.exists(output_file) and backup:
            shutil.copyfile(output_file, BACKUP_FILE)
            print(f"[INFO] Backup created: {BACKUP_FILE}")

        # Write new EPG
        with open(output_file, 'wb') as f:
            f.write(response.content)
        print(f"[SUCCESS] EPG saved to: {output_file}")
    except Exception as e:
        print(f"[ERROR] Failed to fetch EPG: {e}")

if __name__ == "__main__":
    fetch_epg(EPG_URL, OUTPUT_FILE)
