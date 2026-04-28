"""
publisher.py — Poste automatiquement sur TikTok et YouTube Shorts
Dépendances : pip install requests google-auth google-auth-oauthlib google-api-python-client
"""

import json
import os
import time
from pathlib import Path
import requests

# ─── CONFIG ────────────────────────────────────────────────────────────────────
# TikTok — Obtenir sur https://developers.tiktok.com
TIKTOK_CLIENT_KEY    = os.environ.get("TIKTOK_CLIENT_KEY", "")
TIKTOK_CLIENT_SECRET = os.environ.get("TIKTOK_CLIENT_SECRET", "")
TIKTOK_ACCESS_TOKEN  = os.environ.get("TIKTOK_ACCESS_TOKEN", "")  # OAuth flow requis

# YouTube — Fichier de credentials OAuth2 depuis Google Cloud Console
YOUTUBE_CREDENTIALS_FILE = "youtube_credentials.json"
YOUTUBE_TOKEN_FILE = "youtube_token.json"

# Délai entre chaque publication (secondes) — évite les bans
POST_DELAY_SECONDS = 300  # 5 min entre chaque post

# Logs des publications
PUBLISH_LOG = Path("publish_log.json")
# ───────────────────────────────────────────────────────────────────────────────


def load_publish_log() -> list:
    if PUBLISH_LOG.exists():
        return json.loads(PUBLISH_LOG.read_text())
    return []


def save_publish_log(log: list):
    PUBLISH_LOG.write_text(json.dumps(log, indent=2, ensure_ascii=False))


# ─── TIKTOK ──────────────────────────────────────────────────────────────────

def tiktok_upload(video_path: str, caption: str) -> dict:
    """
    Upload une vidéo sur TikTok via Content Posting API v2.
    Doc : https://developers.tiktok.com/doc/content-posting-api-get-started
    """
    video_size = Path(video_path).stat().st_size

    # Étape 1 : Initialiser l'upload
    init_url = "https://open.tiktokapis.com/v2/post/publish/video/init/"
    headers = {
        "Authorization": f"Bearer {TIKTOK_ACCESS_TOKEN}",
        "Content-Type": "application/json; charset=UTF-8",
    }
    payload = {
        "post_info": {
            "title": caption[:2200],  # Max 2200 chars
            "privacy_level": "SELF_ONLY",  # Commence en privé pour vérifier
            "disable_duet": False,
            "disable_comment": False,
            "disable_stitch": False,
        },
        "source_info": {
            "source": "FILE_UPLOAD",
            "video_size": video_size,
            "chunk_size": video_size,
            "total_chunk_count": 1,
        }
    }

    resp = requests.post(init_url, headers=headers, json=payload)
    if resp.status_code != 200:
        return {"success": False, "error": f"Init failed: {resp.text}"}

    data = resp.json().get("data", {})
    upload_url = data.get("upload_url")
    publish_id = data.get("publish_id")

    # Étape 2 : Upload du fichier binaire
    with open(video_path, "rb") as f:
        video_bytes = f.read()

    upload_headers = {
        "Content-Range": f"bytes 0-{video_size - 1}/{video_size}",
        "Content-Type": "video/mp4",
    }
    upload_resp = requests.put(upload_url, headers=upload_headers, data=video_bytes)
    if upload_resp.status_code not in (200, 201, 206):
        return {"success": False, "error": f"Upload failed: {upload_resp.text}"}

    return {"success": True, "publish_id": publish_id, "platform": "tiktok"}


def tiktok_check_status(publish_id: str) -> str:
    """Vérifie le statut d'une publication TikTok."""
    url = "https://open.tiktokapis.com/v2/post/publish/status/fetch/"
    headers = {"Authorization": f"Bearer {TIKTOK_ACCESS_TOKEN}"}
    resp = requests.post(url, headers=headers, json={"publish_id": publish_id})
    if resp.status_code == 200:
        return resp.json().get("data", {}).get("status", "UNKNOWN")
    return "ERROR"


# ─── YOUTUBE SHORTS ──────────────────────────────────────────────────────────

def get_youtube_service():
    """Initialise le service YouTube API avec OAuth2."""
    try:
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build

        SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
        creds = None

        if Path(YOUTUBE_TOKEN_FILE).exists():
            creds = Credentials.from_authorized_user_file(YOUTUBE_TOKEN_FILE, SCOPES)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                from google.auth.transport.requests import Request
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    YOUTUBE_CREDENTIALS_FILE, SCOPES
                )
                creds = flow.run_local_server(port=0)
            Path(YOUTUBE_TOKEN_FILE).write_text(creds.to_json())

        return build("youtube", "v3", credentials=creds)
    except ImportError:
        print("  google-api-python-client non installé")
        return None


def youtube_upload(video_path: str, title: str, description: str) -> dict:
    """Upload une vidéo sur YouTube comme Short."""
    youtube = get_youtube_service()
    if not youtube:
        return {"success": False, "error": "Service YouTube non disponible"}

    try:
        from googleapiclient.http import MediaFileUpload

        body = {
            "snippet": {
                "title": f"{title[:95]} #Shorts",  # Max 100 chars pour Shorts
                "description": description,
                "tags": ["shorts", "viral", "france", "clip"],
                "categoryId": "24",  # Entertainment
            },
            "status": {
                "privacyStatus": "private",  # Commence en privé
                "selfDeclaredMadeForKids": False,
            }
        }

        media = MediaFileUpload(
            video_path,
            mimetype="video/mp4",
            resumable=True,
            chunksize=1024 * 1024,  # 1MB chunks
        )

        request = youtube.videos().insert(
            part=",".join(body.keys()),
            body=body,
            media_body=media,
        )

        response = None
        while response is None:
            status, response = request.next_chunk()
            if status:
                print(f"  YouTube upload : {int(status.progress() * 100)}%")

        video_id = response.get("id")
        return {
            "success": True,
            "video_id": video_id,
            "url": f"https://www.youtube.com/shorts/{video_id}",
            "platform": "youtube_shorts",
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


# ─── ORCHESTRATION ───────────────────────────────────────────────────────────

def publish_clip(clip: dict, platforms: list[str] = None) -> dict:
    """
    Publie un clip sur les plateformes spécifiées.
    clip = {path, caption, source_title, source_channel, source_url}
    """
    if platforms is None:
        platforms = ["tiktok", "youtube_shorts"]

    results = {"clip_path": clip["path"], "published": {}}
    caption = clip.get("caption", "#viral #foryou #fyp")

    # Ajoute l'attribution à la source
    source = clip.get("source_channel", "")
    if source:
        caption += f"\n\nVia @{source} sur YouTube"

    for platform in platforms:
        print(f"  Publication sur {platform}...")

        if platform == "tiktok":
            if not TIKTOK_ACCESS_TOKEN:
                results["published"]["tiktok"] = {"success": False, "error": "Token manquant"}
                continue
            result = tiktok_upload(clip["path"], caption)

        elif platform == "youtube_shorts":
            title = clip.get("source_title", "")[:95] or "Clip viral"
            description = f"{caption}\n\nSource : {clip.get('source_url', '')}"
            result = youtube_upload(clip["path"], title, description)

        else:
            result = {"success": False, "error": f"Plateforme inconnue : {platform}"}

        results["published"][platform] = result

        if result.get("success"):
            print(f"  OK {platform} — {result.get('url') or result.get('publish_id')}")
        else:
            print(f"  Echec {platform} : {result.get('error')}")

        # Délai anti-ban entre les publications
        time.sleep(POST_DELAY_SECONDS)

    return results


def publish_all(clips: list[dict], platforms: list[str] = None) -> list[dict]:
    """Publie tous les clips avec logs."""
    log = load_publish_log()
    all_results = []

    for i, clip in enumerate(clips):
        print(f"\nClip {i+1}/{len(clips)} : {Path(clip['path']).name}")
        result = publish_clip(clip, platforms)
        result["timestamp"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        result["caption"] = clip.get("caption", "")
        all_results.append(result)
        log.append(result)

    save_publish_log(log)
    return all_results


if __name__ == "__main__":
    # Test avec un fichier local
    import sys
    if len(sys.argv) < 2:
        print("Usage : python publisher.py <clip.mp4> [caption]")
        sys.exit(1)

    test_clip = {
        "path": sys.argv[1],
        "caption": sys.argv[2] if len(sys.argv) > 2 else "#viral #foryou #fyp",
        "source_title": "Test",
        "source_channel": "Test",
        "source_url": "",
    }
    results = publish_clip(test_clip)
    print(json.dumps(results, indent=2, ensure_ascii=False))
