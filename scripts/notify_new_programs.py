import xml.etree.ElementTree as ET
import sys

def parse_epg(file_path):
    tree = ET.parse(file_path)
    root = tree.getroot()

    programs = set()
    details = {}

    for p in root.findall("programme"):
        title_el = p.find("title")
        desc_el = p.find("desc")

        if title_el is not None:
            title = title_el.text.strip()
            programs.add(title)
            details[title] = desc_el.text.strip() if desc_el is not None else ""

    return programs, details

def compare_epgs(old_file, new_file):
    old_titles, _ = parse_epg(old_file)
    new_titles, new_details = parse_epg(new_file)

    new_programs = new_titles - old_titles

    movies = []
    tv_shows = []

    for title in sorted(new_programs):
        description = new_details.get(title, "").lower()
        if "series" in description or "season" in description or "episode" in description:
            tv_shows.append(title)
        else:
            movies.append(title)

    return movies, tv_shows

def save_notification_file(movies, tv_shows, filename="new_shows_notification.txt"):
    with open(filename, "w", encoding="utf-8") as f:
        if not movies and not tv_shows:
            f.write("No new airings found today.\n")
            return

        if movies:
            f.write("🎬 New Movies:\n")
            for m in movies:
                f.write(f"- {m}\n")
            f.write("\n")

        if tv_shows:
            f.write("📺 New TV Shows:\n")
            for s in tv_shows:
                f.write(f"- {s}\n")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python3 notify_new_shows.py epg_yesterday.xml epg.xml")
        sys.exit(1)

    movies, shows = compare_epgs(sys.argv[1], sys.argv[2])
    save_notification_file(movies, shows)
