import requests
import os
import sys

def send_pushbullet_notification(token, title, body):
    url = "https://api.pushbullet.com/v2/pushes"
    headers = {
        "Access-Token": token.strip(),  # Remove any newline issues
        "Content-Type": "application/json"
    }
    payload = {
        "type": "note",
        "title": title,
        "body": body
    }
    response = requests.post(url, json=payload, headers=headers)
    response.raise_for_status()
    print("✅ Pushbullet notification sent.")

def load_summary(file_path="new_shows_notification.txt"):
    if not os.path.exists(file_path):
        return "No summary file found."

    with open(file_path, "r", encoding="utf-8") as f:
        return f.read().strip()

if __name__ == "__main__":
    token = os.getenv("PUSHBULLET_TOKEN")
    if not token:
        print("❌ PUSHBULLET_TOKEN environment variable is not set.")
        sys.exit(1)

    message = load_summary()
    send_pushbullet_notification(token, "📢 New Airings Detected", message)
