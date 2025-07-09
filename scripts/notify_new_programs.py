import xml.etree.ElementTree as ET
import sys
from datetime import datetime

def parse_epg(epg_file):
    tree = ET.parse(epg_file)
    root = tree.getroot()

    programmes = []
    for p in root.findall("programme"):
        title_el = p.find("title")
        start = p.get("start")
        channel = p.get("channel")
        desc_el = p.find("desc")
        categories = [c.text.lower() for c in p.findall("category") if c.text]

        if title_el is not None:
            programmes.append({
                "title": title_el.text.strip(),
                "start": start,
                "channel": channel,
                "desc": desc_el.text.strip() if desc_el is not None else "",
                "categories": categories
            })
    return programmes

def get_unique_titles(programmes):
    return set(p["title"] for p in programmes)

def classify_program(p):
    genres = p["categories"]
    if "movie" in genres or "tv movie" in genres:
        return "movie"
    if "tv show" in genres or "kids" in genres or "animation" in genres or "series" in genres:
        return "tv"
    # fallback using title patterns
    if any(keyword in p["title"].lower() for keyword in ["movie", "film", ": the", ": a"]):
        return "movie"
    return "tv"

def format_time(ts):
    try:
        return datetime.strptime(ts[:12], "%Y%m%d%H%M").strftime("%Y-%m-%d %H:%M")
    except:
        return ts

def compare_epgs(epg_yesterday, epg_today):
    old_programmes = parse_epg(epg_yesterday)
    new_programmes = parse_epg(epg_today)

    old_titles = get_unique_titles(old_programmes)
    new_shows = [p for p in new_programmes if p["title"] not in old_titles]

    movies = [p for p in new_shows if classify_program(p) == "movie"]
    tv_shows = [p for p in new_shows if classify_program(p) == "tv"]
    return movies, tv_shows

def save_notifications(movies, tv_shows, output_file="new_shows_notification.txt"):
    with open(output_file, "w", encoding="utf-8") as f:
        if not movies and not tv_shows:
            f.write("🎉 No new programs aired today.\n")
            print("✅ No new shows.")
            return

        if movies:
            f.write("🎬 NEW MOVIES AIRED TODAY:\n\n")
            for show in movies:
                f.write(f"- {show['title']} on Channel {show['channel']} at {format_time(show['start'])}\n")
                if show["desc"]:
                    f.write(f"  📝 {show['desc']}\n")
                f.write("\n")

        if tv_shows:
            f.write("📺 NEW TV SHOWS AIRED TODAY:\n\n")
            for show in tv_shows:
                f.write(f"- {show['title']} on Channel {show['channel']} at {format_time(show['start'])}\n")
                if show["desc"]:
                    f.write(f"  📝 {show['desc']}\n")
                f.write("\n")

    print(f"✅ Notification saved to {output_file}")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python3 notify_new_shows.py epg_yesterday.xml epg.xml")
        sys.exit(1)

    movies, tv_shows = compare_epgs(sys.argv[1], sys.argv[2])
    save_notifications(movies, tv_shows)
