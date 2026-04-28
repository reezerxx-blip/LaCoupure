# TikTok Bot — Pipeline automatisé YouTube → TikTok/Shorts

## Structure du projet

```
tiktok_bot/
├── watcher.py      # Surveille les chaînes YouTube
├── clipper.py      # Découpe + sous-titres avec IA
├── publisher.py    # Publie sur TikTok + YouTube Shorts
├── scheduler.py    # Orchestre tout en automatique
├── downloads/      # Vidéos YouTube téléchargées (auto-créé)
├── clips/          # Clips produits (auto-créé)
├── seen_videos.json  # Mémoire des vidéos déjà traitées
└── publish_log.json  # Log de toutes les publications
```

---

## Installation

### 1. Prérequis système
```bash
# Ubuntu / Debian
sudo apt install ffmpeg python3-pip

# macOS
brew install ffmpeg
```

### 2. Dépendances Python
```bash
pip install yt-dlp anthropic openai-whisper moviepy \
            requests google-auth google-auth-oauthlib \
            google-api-python-client
```

---

## Configuration

### Variables d'environnement (à mettre dans un fichier `.env`)
```bash
export ANTHROPIC_API_KEY="sk-ant-..."         # https://console.anthropic.com
export TIKTOK_CLIENT_KEY="..."               # https://developers.tiktok.com
export TIKTOK_CLIENT_SECRET="..."
export TIKTOK_ACCESS_TOKEN="..."             # Voir section TikTok OAuth ci-dessous
```

### Chaînes YouTube à surveiller
Dans `watcher.py`, modifie la liste `CHANNELS` :
```python
CHANNELS = [
    "https://www.youtube.com/@Squeezie",
    "https://www.youtube.com/@TaChaineIci",
]
```

---

## Obtenir les tokens API

### TikTok (le plus complexe)
1. Crée un compte développeur : https://developers.tiktok.com
2. Crée une app → active **Content Posting API**
3. Configure le redirect URI : `http://localhost:8080`
4. Lance le flow OAuth pour obtenir ton `access_token`
5. ⚠️ Le token expire — il faut le rafraîchir régulièrement

### YouTube Shorts
1. Va sur https://console.cloud.google.com
2. Crée un projet → active l'API **YouTube Data v3**
3. Crée des identifiants **OAuth 2.0** (type : application bureau)
4. Télécharge le JSON → renomme-le `youtube_credentials.json`
5. Au premier lancement, une fenêtre s'ouvre pour l'autorisation

---

## Lancement

### Test d'un seul cycle
```bash
python scheduler.py --once
```

### Lancement continu (toutes les 6h)
```bash
python scheduler.py
```

### Lancement en arrière-plan (Linux)
```bash
nohup python scheduler.py > /dev/null 2>&1 &
echo $! > bot.pid  # Sauvegarde le PID pour l'arrêter plus tard
kill $(cat bot.pid)  # Pour l'arrêter
```

### Avec cron (alternative)
```bash
# Toutes les 6 heures
crontab -e
0 */6 * * * cd /chemin/vers/tiktok_bot && python scheduler.py --once
```

---

## Personnalisation

### Modifier les chaînes surveillées
→ `watcher.py` : liste `CHANNELS`

### Changer le nombre de clips par vidéo
→ `clipper.py` : variable `CLIPS_PER_VIDEO`

### Changer la fréquence de publication
→ `scheduler.py` : variable `CYCLE_INTERVAL_HOURS`

### Modifier le style des sous-titres
→ `clipper.py` : variables `SUBTITLE_FONT_SIZE` + filtre FFmpeg dans `add_subtitles_to_clip`

---

## Notes importantes

- **Whisper** (transcription) tourne en local — prévoir ~2-3 min par vidéo
- **Modèle Whisper** : `base` est rapide, `medium` est plus précis (plus lent)
- Les clips sont d'abord postés en **privé** — change `privacy_level` dans `publisher.py` quand tu es prêt
- Respecte les CGU TikTok et YouTube sur le contenu réutilisé
