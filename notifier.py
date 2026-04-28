"""
notifier.py — Notifie Windows quand des clips sont prêts à poster
Dépendances : pip install win10toast
"""

import os
import json
import shutil
from pathlib import Path
from datetime import datetime

READY_DIR = Path("a_poster")
READY_DIR.mkdir(exist_ok=True)
DONE_DIR = Path("postes")
DONE_DIR.mkdir(exist_ok=True)


def notify_windows(title: str, message: str):
    """Envoie une notification Windows."""
    try:
        from win10toast import ToastNotifier
        toaster = ToastNotifier()
        toaster.show_toast(title, message, duration=10, threaded=True)
    except ImportError:
        print(f"[NOTIF] {title} : {message}")
    except Exception as e:
        print(f"[NOTIF] {title} : {message} (erreur notif: {e})")


def prepare_clips(clips: list[dict]) -> list[dict]:
    """
    Copie les clips dans le dossier a_poster/ avec un fichier
    de description pour chaque clip (caption, source, etc.)
    """
    prepared = []

    for i, clip in enumerate(clips):
        clip_path = Path(clip["path"])
        if not clip_path.exists():
            continue

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        dest_video = READY_DIR / f"{timestamp}_clip{i+1}.mp4"
        dest_info  = READY_DIR / f"{timestamp}_clip{i+1}.txt"

        shutil.copy(clip_path, dest_video)

        info_text = f"""=== CLIP {i+1} — PRÊT À POSTER ===

CAPTION À COPIER :
{clip.get('caption', '#viral #foryou #fyp')}

SOURCE :
{clip.get('source_title', '')}
{clip.get('source_url', '')}

FICHIER VIDÉO :
{dest_video}
"""
        dest_info.write_text(info_text, encoding="utf-8")

        prepared.append({
            "video": str(dest_video),
            "info": str(dest_info),
            "caption": clip.get("caption", ""),
        })

    return prepared


def open_ready_folder():
    """Ouvre le dossier a_poster/ dans l'explorateur Windows."""
    os.startfile(str(READY_DIR.absolute()))


def notify_clips_ready(clips: list[dict]):
    """Notifie que les clips sont prêts et ouvre le dossier."""
    prepared = prepare_clips(clips)

    if not prepared:
        return

    notify_windows(
        "LaCoupure — Clips prêts !",
        f"{len(prepared)} clip(s) prêt(s) à poster sur TikTok Studio"
    )

    open_ready_folder()

    print(f"\n{'='*50}")
    print(f"  {len(prepared)} CLIP(S) PRÊT(S) À POSTER !")
    print(f"{'='*50}")
    for p in prepared:
        print(f"\n  Vidéo  : {p['video']}")
        print(f"  Caption: {p['caption'][:80]}...")
    print(f"\n  Dossier ouvert : {READY_DIR.absolute()}")
    print(f"  Poste sur TikTok Studio : https://studio.tiktok.com")
    print(f"{'='*50}\n")


if __name__ == "__main__":
    print("Test notifier — ouverture du dossier a_poster/")
    open_ready_folder()
