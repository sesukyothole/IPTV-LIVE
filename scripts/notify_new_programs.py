import os
import sys
import requests

def send_pushbullet_notification(token, title, body):
    url = "https://api.pushbullet.com/v2/pushes"
    headers = {
        "Access-Token": token,
        "Content-Type": "application/json"
    }
    payload = {
        "type": "note",
        "title": title,
        "body": body
    }

    response = requests.post(url, json=payload, headers=headers)
    if response.status_code == 200:
        print("✅ Pushbullet notification sent successfully.")
    else:
        print(f"❌ Failed to send notification. Status code: {response.status_code}")
        print(response.text)

def get_notification_body(file_path, max_lines=5):
    if not os.path.exists(file_path):
        return "No new shows notification available."

    with open(file_path, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f.readlines() if line.strip()]
        return "\n".join(lines[:max_lines])

if __name__ == "__main__":
    token = os.getenv("PUSHBULLET_TOKEN")
    if not token:
        print("❌ PUSHBULLET_TOKEN environment variable is not set.")
        sys.exit(1)

    message = get_notification_body("new_shows_notification.txt")
    send_pushbullet_notification(token, "📺 New Programs Detected", message)
