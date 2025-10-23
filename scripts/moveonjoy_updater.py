import requests
import time
import re

# Example channel
channel_id = "disneychannel"

# Subdomains that can be switched
subdomains = [
    "stream1.example.com",
    "stream2.example.com",
    "backup.example.com"
]

# Check video chunks (ts, m4s, mp4, avi, mpeg, etc.)
VIDEO_EXTENSIONS = re.compile(r'\.(ts|m4s|mp4|avi|mkv|webm|mpeg|mpg)$', re.IGNORECASE)

def stream_has_video_data(url):
    try:
        response = requests.get(url, stream=True, timeout=3)
        content_type = response.headers.get("Content-Type", "")

        # Check MIME type first
        if "video" in content_type:
            return True

        # Check last segments for actual video chunks (fast)
        lines = response.text.splitlines()
        video_lines = [line for line in lines if VIDEO_EXTENSIONS.search(line)]

        return len(video_lines) > 0
    except:
        return False


def get_stream_url(channel_id, subdomain):
    return f"https://{subdomain}/{channel_id}/index.m3u8"


def check_stream(channel_id):
    for subdomain in subdomains:
        stream_url = get_stream_url(channel_id, subdomain)

        print(f"Testing {stream_url} ...")

        # Retry 3 times to confirm offline
        for attempt in range(3):
            if stream_has_video_data(stream_url):
                print(f"✅ ONLINE via {subdomain}")
                return stream_url
            print(f"⚠️ Attempt {attempt + 1}/3 failed")

            time.sleep(0.5)  # tiny delay, still fast

        print(f"❌ {subdomain} failed. Switching to next subdomain...\n")

    print("❌ All subdomains offline")
    return None


if __name__ == "__main__":
    final_stream = check_stream(channel_id)
    if final_stream:
        print("✅ Final working stream:", final_stream)
    else:
        print("❌ No working streams found")