"""
clipper.py — Découpe les moments viraux avec Claude + sous-titres Whisper
Dépendances : pip install anthropic moviepy openai-whisper
               pip install ffmpeg-python
               + ffmpeg installé sur le système (apt install ffmpeg)
"""

import json
import os
import subprocess
from pathlib import Path
import anthropic

# ─── CONFIG ────────────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
CLIPS_DIR = Path("clips")
CLIPS_DIR.mkdir(exist_ok=True)

# Durée max d'un clip TikTok (secondes)
CLIP_MAX_DURATION = 55

# Nombre de clips à extraire par vidéo
CLIPS_PER_VIDEO = 2

# Taille de la police pour les sous-titres
SUBTITLE_FONT_SIZE = 22
# ───────────────────────────────────────────────────────────────────────────────


def get_video_duration(video_path: str) -> float:
    """Retourne la durée d'une vidéo en secondes."""
    cmd = [
        "ffprobe", "-v", "quiet", "-print_format", "json",
        "-show_streams", video_path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    data = json.loads(result.stdout)
    for stream in data.get("streams", []):
        if stream.get("codec_type") == "video":
            return float(stream.get("duration", 0))
    return 0.0


def transcribe_video(video_path: str) -> list[dict]:
    """
    Transcrit la vidéo avec Whisper.
    Retourne une liste de segments : [{start, end, text}, ...]
    """
    print("  Transcription Whisper en cours...")
    try:
        import whisper
        model = whisper.load_model("base")
        result = model.transcribe(video_path, language="fr", word_timestamps=True)
        segments = []
        for seg in result.get("segments", []):
            segments.append({
                "start": seg["start"],
                "end": seg["end"],
                "text": seg["text"].strip(),
            })
        return segments
    except ImportError:
        print("  Whisper non installé — transcription simulée")
        return []


def find_viral_moments(video_info: dict, transcript: list[dict], duration: float) -> list[dict]:
    """
    Utilise Claude pour identifier les moments les plus viraux dans la transcription.
    Retourne une liste de moments : [{start, end, reason}, ...]
    """
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    # Formate la transcription pour le prompt
    transcript_text = "\n".join(
        f"[{seg['start']:.1f}s - {seg['end']:.1f}s] {seg['text']}"
        for seg in transcript[:200]  # Limite pour le context window
    ) if transcript else "Transcription non disponible."

    prompt = f"""Tu es un expert en montage TikTok et en contenu viral francophone.

Voici les informations sur une vidéo YouTube :
- Titre : {video_info.get('title', 'Inconnue')}
- Chaîne : {video_info.get('channel', 'Inconnue')}
- Durée totale : {duration:.0f} secondes

Transcription :
{transcript_text}

Identifie exactement {CLIPS_PER_VIDEO} moments qui feraient d'excellents clips TikTok (max {CLIP_MAX_DURATION}s chacun).
Critères de sélection :
- Moment drôle, surprenant, ou très émotionnel
- Début et fin clairs (pas en plein milieu d'une phrase)
- Compréhensible sans contexte
- Accrocheur dès les premières secondes

Réponds UNIQUEMENT en JSON valide, sans markdown :
{{
  "clips": [
    {{
      "start": 45.0,
      "end": 98.0,
      "reason": "Moment hilarant où...",
      "tiktok_caption": "Caption TikTok avec emojis et hashtags FR tendance"
    }}
  ]
}}"""

    try:
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1000,
            messages=[{"role": "user", "content": prompt}]
        )
        text = response.content[0].text
        clean = text.replace("```json", "").replace("```", "").strip()
        data = json.loads(clean)
        return data.get("clips", [])
    except Exception as e:
        print(f"  Erreur Claude : {e}")
        # Fallback : découpe en segments réguliers
        segment_duration = min(CLIP_MAX_DURATION, duration / (CLIPS_PER_VIDEO + 1))
        clips = []
        for i in range(CLIPS_PER_VIDEO):
            start = segment_duration * (i + 0.5)
            end = min(start + CLIP_MAX_DURATION, duration - 5)
            clips.append({
                "start": start,
                "end": end,
                "reason": "Sélection automatique",
                "tiktok_caption": f"{video_info.get('title', '')} #foryou #fyp #viral"
            })
        return clips


def extract_clip(video_path: str, start: float, end: float, output_path: str) -> bool:
    """Extrait un clip et le convertit au format vertical 9:16 pour TikTok."""
    duration = end - start
    cmd = [
        "ffmpeg", "-y",
        "-ss", str(start),
        "-i", video_path,
        "-t", str(duration),
        # Filtre : crop au centre + resize 1080x1920
        "-vf", "crop=ih*9/16:ih,scale=1080:1920",
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "23",
        "-c:a", "aac",
        "-b:a", "128k",
        "-movflags", "+faststart",
        output_path,
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=120)
        return True
    except subprocess.CalledProcessError as e:
        print(f"  Erreur FFmpeg : {e.stderr.decode()[:200]}")
        return False


def add_subtitles_to_clip(
    clip_path: str,
    transcript: list[dict],
    clip_start: float,
    clip_end: float,
    output_path: str
) -> bool:
    """
    Ajoute les sous-titres correspondants au clip.
    Utilise ffmpeg avec filtre drawtext.
    """
    # Filtre les segments qui appartiennent au clip
    clip_segments = [
        s for s in transcript
        if s["end"] > clip_start and s["start"] < clip_end
    ]

    if not clip_segments:
        # Pas de transcription → copie simple
        import shutil
        shutil.copy(clip_path, output_path)
        return True

    # Construit un fichier SRT temporaire
    srt_path = clip_path.replace(".mp4", ".srt")
    with open(srt_path, "w", encoding="utf-8") as f:
        for i, seg in enumerate(clip_segments, 1):
            start_rel = max(0, seg["start"] - clip_start)
            end_rel = min(clip_end - clip_start, seg["end"] - clip_start)

            def fmt_time(t):
                h = int(t // 3600)
                m = int((t % 3600) // 60)
                s = int(t % 60)
                ms = int((t % 1) * 1000)
                return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

            f.write(f"{i}\n{fmt_time(start_rel)} --> {fmt_time(end_rel)}\n{seg['text']}\n\n")

    # FFmpeg avec sous-titres brûlés
    cmd = [
        "ffmpeg", "-y",
        "-i", clip_path,
        "-vf", (
            f"subtitles={srt_path}:force_style='"
            f"FontName=Arial,FontSize={SUBTITLE_FONT_SIZE},"
            f"PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,"
            f"BorderStyle=3,Outline=2,Shadow=1,"
            f"Alignment=2,MarginV=80'"
        ),
        "-c:a", "copy",
        output_path,
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=120)
        Path(srt_path).unlink(missing_ok=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f"  Sous-titres échoués : {e.stderr.decode()[:200]}")
        import shutil
        shutil.copy(clip_path, output_path)
        Path(srt_path).unlink(missing_ok=True)
        return True  # Retourne quand même le clip sans sous-titres


def process_video(video_info: dict, video_path: str) -> list[dict]:
    """
    Pipeline complet : transcription → sélection IA → découpage → sous-titres.
    Retourne la liste des clips produits avec leurs métadonnées.
    """
    print(f"\nTraitement : {video_info.get('title', video_path)[:60]}")

    duration = get_video_duration(video_path)
    print(f"  Durée : {duration:.0f}s")

    transcript = transcribe_video(video_path)
    print(f"  Segments transcrits : {len(transcript)}")

    moments = find_viral_moments(video_info, transcript, duration)
    print(f"  Moments viraux identifiés : {len(moments)}")

    clips = []
    video_id = video_info.get("id", Path(video_path).stem)

    for i, moment in enumerate(moments):
        start = float(moment["start"])
        end = min(float(moment["end"]), start + CLIP_MAX_DURATION)

        clip_raw = CLIPS_DIR / f"{video_id}_clip{i+1}_raw.mp4"
        clip_final = CLIPS_DIR / f"{video_id}_clip{i+1}.mp4"

        print(f"  Clip {i+1} : {start:.0f}s → {end:.0f}s ({moment.get('reason', '')[:50]})")

        if extract_clip(video_path, start, end, str(clip_raw)):
            add_subtitles_to_clip(str(clip_raw), transcript, start, end, str(clip_final))
            clip_raw.unlink(missing_ok=True)

            clips.append({
                "path": str(clip_final),
                "caption": moment.get("tiktok_caption", ""),
                "reason": moment.get("reason", ""),
                "source_title": video_info.get("title", ""),
                "source_channel": video_info.get("channel", ""),
                "source_url": video_info.get("url", ""),
            })
            print(f"  Clip {i+1} produit : {clip_final.name}")
        else:
            print(f"  Clip {i+1} échoué")

    return clips


if __name__ == "__main__":
    # Test rapide avec une vidéo locale
    import sys
    if len(sys.argv) < 2:
        print("Usage : python clipper.py <video.mp4>")
        sys.exit(1)

    test_info = {"id": "test", "title": "Test vidéo", "channel": "Test"}
    clips = process_video(test_info, sys.argv[1])
    print(f"\n{len(clips)} clip(s) produit(s).")
