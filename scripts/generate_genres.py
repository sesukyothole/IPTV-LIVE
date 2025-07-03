import xml.etree.ElementTree as ET

# Define your genre colors (you can customize these)
GENRE_COLOR_MAP = {
    "Animation": "FF33CCFF",
    "Comedy": "FFFFFF00",
    "Drama": "FFFF9900",
    "Action": "FFFF0000",
    "Adventure": "FFCC00CC",
    "Family": "FF00FF00",
    "Fantasy": "FF9900FF",
    "Science Fiction": "FF00FFFF",
    "Music": "FFFF66FF",
    "Reality": "FF66FF66",
    "Documentary": "FF999999",
    "Horror": "FFFF3300",
    "Mystery": "FF6600CC",
    "Romance": "FFFF99CC",
    "TV Movie": "FF00CCCC",
    "Crime": "FFCC0000",
    "Thriller": "FF660000",
    "War": "FFCC6666",
    "Western": "FF996633",
    "History": "FF3333FF",
    "Sport": "FF33FF33",
}

DEFAULT_COLOR = "FFCCCCCC"  # Grey for unknown genres

# File to process
EPG_FILE = "epg.xml"
OUTPUT_FILE = "genres.xml"

def extract_genres_from_epg(epg_file):
    tree = ET.parse(epg_file)
    root = tree.getroot()

    genres_found = set()

    for programme in root.findall('programme'):
        for category in programme.findall('category'):
            if category.text:
                genres_found.add(category.text.strip())

    return genres_found

def generate_genres_file(epg_file, output_file):
    genres_in_epg = extract_genres_from_epg(epg_file)

    root = ET.Element('genres')

    for genre in sorted(genres_in_epg):
        genre_element = ET.SubElement(root, 'genre')
        genre_element.set('name', genre)
        genre_element.set('color', GENRE_COLOR_MAP.get(genre, DEFAULT_COLOR))

    tree = ET.ElementTree(root)
    tree.write(output_file, encoding='utf-8', xml_declaration=True)
    print(f"✅ Merged genres and colors written to {output_file}")

if __name__ == "__main__":
    generate_genres_file(EPG_FILE, OUTPUT_FILE)
