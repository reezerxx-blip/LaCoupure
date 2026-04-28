"""
watcher.py — Surveille les chaînes YouTube et détecte les nouvelles vidéos
Dépendances : pip install yt-dlp requests
"""

import json
import os
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

# ─── CONFIG ────────────────────────────────────────────────────────────────────
CHANNELS = [
    "https://www.youtube.com/@McFlyEtCarlito",
    "https://www.youtube.com/@Amixem",
    "https://www.youtube.com/@LaBoiserie",
]

# Inclure les replays de lives YouTube
INCLUDE_LIVES = True

# Nombre de vidéos récentes à checker par chaîne (plus élevé pour capter les lives)
MAX_VIDEOS_PER_CHANNEL = 5

# Durée max — on accepte les lives jusqu'à 3h car on prend des extraits
MAX_VIDEO_DURATION = 10800  # 3h

# Fichier pour mémoriser les vidéos déjà traitées
SEEN_FILE = Path("seen_videos.json")

# Dossier où télécharger les vidéos
DOWNLOAD_DIR = Path("downloads")
DOWNLOAD_DIR.mkdir(exist_ok=True)
# ───────────────────────────────────────────────────────────────────────────────


def load_seen() -> set:
    if SEEN_FILE.exists():
        return set(json.loads(SEEN_FILE.read_text()))
    return set()


def save_seen(seen: set):
    SEEN_FILE.write_text(json.dumps(list(seen), indent=2))


def get_recent_videos(channel_url: str) -> list[dict]:
    """Récupère les vidéos récentes d'une chaîne via yt-dlp."""
    cmd = [
        "yt-dlp",
        "--dump-json",
        "--flat-playlist",
        f"--playlist-end={MAX_VIDEOS_PER_CHANNEL}",
        "--no-warnings",
        channel_url,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        videos = []
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            try:
                data = json.loads(line)
                videos.append({
                    "id": data.get("id"),
                    "title": data.get("title"),
                    "url": data.get("url") or f"https://www.youtube.com/watch?v={data.get('id')}",
                    "duration": data.get("duration", 0),
                    "channel": data.get("channel") or data.get("uploader"),
                    "upload_date": data.get("upload_date"),
                })
            except json.JSONDecodeError:
                continue
        return videos
    except subprocess.TimeoutExpired:
        print(f"  Timeout pour {channel_url}")
        return []
    except Exception as e:
        print(f"  Erreur pour {channel_url}: {e}")
        return []


def download_video(video: dict) -> Path | None:
    """Télécharge une vidéo en 720p max."""
    output_path = DOWNLOAD_DIR / f"{video['id']}.mp4"
    if output_path.exists():
        print(f"  Déjà téléchargée : {output_path}")
        return output_path

    cmd = [
        "yt-dlp",
        "-f", "bestvideo[height<=720]+bestaudio/best[height<=720]",
        "--merge-output-format", "mp4",
        "-o", str(output_path),
        "--no-warnings",
        video["url"],
    ]
    print(f"  Téléchargement : {video['title'][:60]}...")
    try:
        subprocess.run(cmd, check=True, timeout=300)
        return output_path
    except subprocess.CalledProcessError as e:
        print(f"  Erreur téléchargement : {e}")
        return None
    except subprocess.TimeoutExpired:
        print(f"  Timeout téléchargement")
        return None


def watch() -> list[dict]:
    """
    Scanne toutes les chaînes, retourne les nouvelles vidéos à traiter
    sous forme de liste de dicts {video_info, local_path}.
    """
    seen = load_seen()
    to_process = []

    for channel_url in CHANNELS:
        print(f"\nScan : {channel_url}")
        videos = get_recent_videos(channel_url)

        for video in videos:
            vid_id = video["id"]
            if not vid_id:
                continue
            if vid_id in seen:
                print(f"  Déjà vu : {video['title'][:50]}")
                continue
            if video.get("duration", 0) > MAX_VIDEO_DURATION:
                print(f"  Trop longue ({video['duration']}s) : {video['title'][:50]}")
                seen.add(vid_id)
                continue

            print(f"  Nouvelle vidéo : {video['title'][:60]}")
            local_path = download_video(video)
            if local_path:
                to_process.append({"info": video, "path": str(local_path)})
                seen.add(vid_id)

    save_seen(seen)
    return to_process


if __name__ == "__main__":
    print("=== Watcher démarré ===")
    new_videos = watch()
    print(f"\n{len(new_videos)} nouvelle(s) vidéo(s) à traiter.")
    for v in new_videos:
        print(f"  - {v['info']['title']} → {v['path']}")
