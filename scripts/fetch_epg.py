import requests
import shutil
import os
import gzip
import io
from datetime import datetime

# === CONFIG ===
EPG_GZ_URL = "https://epg,pw/xmltv/epg_US.xml.gz"
OUTPUT_FILE = "epg.xml"
BACKUP_FILE = f"guide_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xml"

# === FUNCTIONALITY ===

def fetch_and_decompress_gz(url, output_file, backup=True):
    try:
        print(f"[INFO] Downloading EPG from: {url}")
        response = requests.get(url, timeout=30)
        response.raise_for_status()

        # Backup current XML if exists
        if os.path.exists(output_file) and backup:
            shutil.copyfile(output_file, BACKUP_FILE)
            print(f"[INFO] Backup created: {BACKUP_FILE}")

        # Decompress in memory
        with gzip.GzipFile(fileobj=io.BytesIO(response.content)) as gz:
            xml_content = gz.read()

        # Save decompressed XML
        with open(output_file, "wb") as f:
            f.write(xml_content)
        print(f"[SUCCESS] EPG saved to: {output_file}")

    except Exception as e:
        print(f"[ERROR] Failed to fetch or decompress EPG: {e}")

if __name__ == "__main__":
    fetch_and_decompress_gz(EPG_GZ_URL, OUTPUT_FILE)
