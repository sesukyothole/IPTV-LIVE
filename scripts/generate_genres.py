import xml.etree.ElementTree as ET

def is_valid_genre(genre):
    """Filter out numeric genres like '35', '10762'."""
    return genre and not genre.strip().isdigit()

def extract_genres(epg_file):
    tree = ET.parse(epg_file)
    root = tree.getroot()

    genres = set()

    for programme in root.findall('programme'):
        for category in programme.findall('category'):
            genre_text = category.text
            if is_valid_genre(genre_text):
                genres.add(genre_text.strip())

    return sorted(genres)

def generate_genres_xml(genres, output_file):
    root = ET.Element("genres")

    for genre in genres:
        genre_el = ET.SubElement(root, "genre")
        genre_el.text = genre

    tree = ET.ElementTree(root)
    tree.write(output_file, encoding="utf-8", xml_declaration=True)
    print(f"✅ genres.xml generated with {len(genres)} genres")

if __name__ == "__main__":
    input_epg = "epg.xml"
    output_genres = "genres.xml"

    genres = extract_genres(input_epg)
    generate_genres_xml(genres, output_genres)
