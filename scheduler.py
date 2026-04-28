"""
scheduler.py — Orchestre le pipeline complet en automatique
Lance : python scheduler.py

Dépendances globales :
  pip install yt-dlp anthropic openai-whisper moviepy \
              requests google-auth google-auth-oauthlib google-api-python-client

Variables d'environnement à définir :
  ANTHROPIC_API_KEY    → clé API Anthropic (https://console.anthropic.com)
  TIKTOK_ACCESS_TOKEN  → token OAuth TikTok (https://developers.tiktok.com)
  TIKTOK_CLIENT_KEY    → clé app TikTok
  TIKTOK_CLIENT_SECRET → secret app TikTok
"""

import os
import time
import traceback
from datetime import datetime
from pathlib import Path

from watcher import watch
from clipper import process_video
from notifier import notify_clips_ready

# ─── CONFIG ────────────────────────────────────────────────────────────────────
# Intervalle entre chaque cycle complet (secondes)
CYCLE_INTERVAL_HOURS = 6
CYCLE_INTERVAL = CYCLE_INTERVAL_HOURS * 3600

# Plateformes cibles
PLATFORMS = ["tiktok", "youtube_shorts"]

# Supprimer les vidéos source après traitement (économise de la place)
DELETE_SOURCE_AFTER = True

# Supprimer les clips après publication
DELETE_CLIPS_AFTER = False

# Nombre max de clips postés par cycle (évite le spam)
MAX_CLIPS_PER_CYCLE = 4

# Fichier de log global
LOG_FILE = Path("scheduler.log")
# ───────────────────────────────────────────────────────────────────────────────


def log(msg: str):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {msg}"
    print(line)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def run_cycle():
    """Exécute un cycle complet du pipeline."""
    log("═" * 60)
    log("Nouveau cycle démarré")

    # ── 1. Surveillance & téléchargement ──
    log("Étape 1 : Surveillance des chaînes YouTube...")
    try:
        new_videos = watch()
        log(f"  {len(new_videos)} nouvelle(s) vidéo(s) détectée(s)")
    except Exception:
        log(f"  ERREUR surveillance : {traceback.format_exc()}")
        return

    if not new_videos:
        log("  Rien de nouveau. Cycle terminé.")
        return

    # ── 2. Découpage & sous-titres ──
    log("Étape 2 : Découpage et sous-titres...")
    all_clips = []
    for video_data in new_videos:
        try:
            clips = process_video(video_data["info"], video_data["path"])
            all_clips.extend(clips)
            log(f"  {len(clips)} clip(s) produits depuis : {video_data['info'].get('title', '')[:50]}")

            # Supprime la vidéo source si configuré
            if DELETE_SOURCE_AFTER:
                Path(video_data["path"]).unlink(missing_ok=True)
                log(f"  Source supprimée : {video_data['path']}")

        except Exception:
            log(f"  ERREUR découpage : {traceback.format_exc()}")

    if not all_clips:
        log("  Aucun clip produit. Cycle terminé.")
        return

    # ── 3. Limite par cycle ──
    if len(all_clips) > MAX_CLIPS_PER_CYCLE:
        log(f"  Limite : {MAX_CLIPS_PER_CYCLE} clips max par cycle (avait {len(all_clips)})")
        all_clips = all_clips[:MAX_CLIPS_PER_CYCLE]

    # ── 4. Notification & préparation pour TikTok Studio ──
    log(f"Étape 3 : Préparation de {len(all_clips)} clip(s) pour TikTok Studio...")
    try:
        notify_clips_ready(all_clips)
        log(f"  Clips prêts dans le dossier a_poster/")
        log(f"  Poste sur https://studio.tiktok.com")
    except Exception:
        log(f"  ERREUR notification : {traceback.format_exc()}")

    log("Cycle terminé.")


def run_forever():
    """Boucle infinie — lance un cycle toutes les X heures."""
    log("╔══════════════════════════════════════╗")
    log("║    TikTok Bot démarré                ║")
    log(f"║    Cycle toutes les {CYCLE_INTERVAL_HOURS}h               ║")
    log("╚══════════════════════════════════════╝")

    # Vérifie les variables d'environnement critiques
    if not os.environ.get("ANTHROPIC_API_KEY"):
        log("ATTENTION : ANTHROPIC_API_KEY non défini !")
    if not os.environ.get("TIKTOK_ACCESS_TOKEN"):
        log("ATTENTION : TIKTOK_ACCESS_TOKEN non défini — publication TikTok désactivée")

    while True:
        try:
            run_cycle()
        except KeyboardInterrupt:
            log("Arrêt manuel (Ctrl+C)")
            break
        except Exception:
            log(f"ERREUR CRITIQUE : {traceback.format_exc()}")

        log(f"Prochaine exécution dans {CYCLE_INTERVAL_HOURS}h...")
        try:
            time.sleep(CYCLE_INTERVAL)
        except KeyboardInterrupt:
            log("Arrêt manuel (Ctrl+C)")
            break


if __name__ == "__main__":
    import sys

    if "--once" in sys.argv:
        # Lance un seul cycle (pour test)
        run_cycle()
    else:
        run_forever()
