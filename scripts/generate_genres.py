import xml.etree.ElementTree as ET

EPG_FILE = "epg.xml"
GENRE_FILE = "genres.xml"

tree = ET.parse(EPG_FILE)
root = tree.getroot()

unique_genres = set()

for programme in root.findall('programme'):
    for category in programme.findall('category'):
        if category.text:
            unique_genres.add(category.text.strip())

genre_root = ET.Element("genres")

for genre in sorted(unique_genres):
    genre_el = ET.SubElement(genre_root, "genre")
    genre_el.set("name", genre)
    genre_el.set("color", "#ffcc00")  # default color

tree = ET.ElementTree(genre_root)
tree.write(GENRE_FILE, encoding="utf-8", xml_declaration=True)

print(f"✅ {GENRE_FILE} created with {len(unique_genres)} genres.")
