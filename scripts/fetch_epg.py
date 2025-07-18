import requests

EPG_URL = "https://epg.pw/xmltv/epg_US.xml"

response = requests.get(EPG_URL)
if response.status_code == 200:
    with open("guide.xml", "wb") as f:
        f.write(response.content)
    print("✅ guide.xml generated successfully")
else:
    print("❌ Failed to download EPG:", response.status_code)
    exit(1)