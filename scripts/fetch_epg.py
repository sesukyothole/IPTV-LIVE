import requests
import gzip
import io
import xml.etree.ElementTree as ET

# List of your EPG .gz URLs
EPG_GZ_URLS = [
    "https://epg.pw/xmltv/epg_US.xml.gz",
    "https://epgshare01.online/epgshare01/epg_ripper_US1.xml.gz"
]

# Function to download and extract EPG XML
def fetch_epg(url):
    print(f"Fetching EPG from {url} ...")
    response = requests.get(url)
    if response.status_code == 200:
        with gzip.GzipFile(fileobj=io.BytesIO(response.content)) as gz:
            epg_xml = gz.read().decode("utf-8")
        print(f"EPG fetched successfully from {url}")
        return epg_xml
    else:
        print(f"Failed to fetch {url}: {response.status_code}")
        return None

# Create root element for merged XML
merged_root = ET.Element("tv")

# To keep track of added channels to avoid duplicates
added_channels = set()

for url in EPG_GZ_URLS:
    epg_data = fetch_epg(url)
    if not epg_data:
        continue

    root = ET.fromstring(epg_data)
    
    # Merge <channel> elements
    for channel in root.findall("channel"):
        channel_id = channel.get("id")
        if channel_id not in added_channels:
            merged_root.append(channel)
            added_channels.add(channel_id)

    # Merge <programme> elements
    for programme in root.findall("programme"):
        merged_root.append(programme)

# Convert merged XML tree to string
merged_tree = ET.ElementTree(merged_root)
merged_tree.write("merged_epg.xml", encoding="utf-8", xml_declaration=True)

print("Merged EPG saved as merged_epg.xml")
