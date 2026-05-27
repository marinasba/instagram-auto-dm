import os
import json
import logging
import random
import httpx
from fastapi import FastAPI, Request, Query, Depends, HTTPException
from fastapi.responses import PlainTextResponse, HTMLResponse

app = FastAPI()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("insta-dm")

CONFIG_PATH = "config.json"

def load_config():
    with open(CONFIG_PATH) as f:
        return json.load(f)

def save_config(config):
    with open(CONFIG_PATH, "w") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)

CONFIG = load_config()

VERIFY_TOKEN = os.environ["VERIFY_TOKEN"]
ACCESS_TOKEN = os.environ["ACCESS_TOKEN"]
ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN", VERIFY_TOKEN)
GRAPH_API = "https://graph.instagram.com/v21.0"

sent_comments: set[str] = set()
recent_events: list[dict] = []


def check_admin(token: str = Query(default="")):
    if token != ADMIN_TOKEN:
        raise HTTPException(status_code=403, detail="Token invalide")


@app.get("/")
async def root():
    return {"status": "ok", "app": "instagram-auto-dm"}


@app.get("/privacy", response_class=HTMLResponse)
async def privacy():
    return """<!DOCTYPE html><html lang="fr"><head><meta charset="utf-8"><title>Politique de confidentialité</title>
<style>body{font-family:sans-serif;max-width:600px;margin:40px auto;padding:20px;color:#333;}</style></head><body>
<h1>Politique de confidentialité</h1>
<p>Cette application envoie des messages directs automatisés sur Instagram en réponse aux commentaires contenant des mots-clés spécifiques.</p>
<p><strong>Données collectées :</strong> Aucune donnée personnelle n'est stockée. Seul l'identifiant du commentaire est temporairement conservé en mémoire pour éviter les doublons.</p>
<p><strong>Utilisation :</strong> Les données sont utilisées uniquement pour envoyer le message automatique correspondant.</p>
<p><strong>Contact :</strong> contact@gariguettes.fr</p>
</body></html>"""


@app.get("/logs")
async def get_logs(_=Depends(check_admin)):
    return recent_events[-50:]


# ─── Admin interface ───

ADMIN_HTML = """<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Messages Auto - Admin</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #f5f0eb; color: #2d2d2d; padding: 20px; max-width: 700px; margin: 0 auto; }
  h1 { font-size: 1.5em; margin-bottom: 8px; color: #4a7c59; }
  .subtitle { color: #888; font-size: 0.9em; margin-bottom: 24px; }
  .card { background: white; border-radius: 12px; padding: 20px; margin-bottom: 16px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); }
  .card-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
  .keyword { font-weight: 700; font-size: 1.1em; color: #4a7c59; text-transform: uppercase; }
  .btn { border: none; border-radius: 8px; padding: 8px 16px; cursor: pointer; font-size: 0.9em; font-weight: 600; }
  .btn-delete { background: #f5e6e6; color: #c0392b; }
  .btn-delete:hover { background: #e8d0d0; }
  .btn-save { background: #2563eb; color: white; width: 100%; padding: 12px; font-size: 1em; transition: background 0.3s; }
  .btn-save:hover { background: #1d4ed8; }
  .btn-save.saved { background: #16a34a; }
  .btn-save.saved:hover { background: #16a34a; }
  .btn-add { background: white; color: #4a7c59; border: 2px dashed #4a7c59; width: 100%; padding: 14px; font-size: 1em; margin-bottom: 16px; border-radius: 12px; }
  .btn-add:hover { background: #f0f7f2; }
  textarea { width: 100%; border: 1px solid #ddd; border-radius: 8px; padding: 12px; font-family: inherit; font-size: 0.9em; resize: vertical; min-height: 100px; }
  input[type=text] { width: 100%; border: 1px solid #ddd; border-radius: 8px; padding: 10px 12px; font-family: inherit; font-size: 1em; margin-bottom: 12px; }
  .tabs { display: flex; gap: 0; margin-bottom: 20px; }
  .tab { flex: 1; padding: 12px; text-align: center; font-weight: 600; font-size: 1em; cursor: pointer; border: none; background: white; color: #888; border-bottom: 3px solid #ddd; transition: all 0.2s; }
  .tab.active { color: #4a7c59; border-bottom-color: #4a7c59; }
  .tab:first-child { border-radius: 8px 0 0 0; }
  .tab:last-child { border-radius: 0 8px 0 0; }
  .tab-content { display: none; }
  .tab-content.active { display: block; }
  .empty { text-align: center; color: #999; padding: 40px; }
</style>
</head>
<body>
<h1>Messages Auto Instagram</h1>
<p class="subtitle">gariguettes_fr</p>

<div class="tabs">
  <button class="tab active" onclick="switchTab('keywords')">Mots-cles</button>
  <button class="tab" onclick="switchTab('replies')">Reponses aux commentaires</button>
</div>

<div id="tab-keywords" class="tab-content active">
  <button class="btn btn-add" onclick="addNew()">+ Ajouter un mot-cle</button>
  <div id="keywords"></div>
  <button class="btn btn-save" onclick="saveAll()">Enregistrer</button>
</div>

<div id="tab-replies" class="tab-content">
  <button class="btn btn-add" onclick="addReply()">+ Ajouter une reponse</button>
  <p class="subtitle">Une reponse sera choisie au hasard pour chaque commentaire</p>
  <div id="replies" class="card" style="margin-bottom:16px;"></div>
  <button class="btn btn-save" onclick="saveAll()">Enregistrer</button>
</div>

<script>
const TOKEN = new URLSearchParams(location.search).get('token');
let keywords = {};
let replies = [];

function switchTab(tab) {
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
  document.getElementById('tab-' + tab).classList.add('active');
  document.querySelector('.tab[onclick*="' + tab + '"]').classList.add('active');
}

async function load() {
  const r = await fetch('/api/config?token=' + TOKEN);
  const data = await r.json();
  keywords = data.keywords;
  replies = data.replies;
  render();
  renderReplies();
}

function render() {
  const el = document.getElementById('keywords');
  const keys = Object.keys(keywords);
  if (!keys.length) { el.innerHTML = '<div class="empty">Aucun mot-clé configuré</div>'; return; }
  el.innerHTML = keys.map(k => `
    <div class="card">
      <div class="card-header">
        <span class="keyword">${k}</span>
        <button class="btn btn-delete" onclick="remove('${k}')">Supprimer</button>
      </div>
      <textarea onchange="keywords['${k}']=this.value">${keywords[k]}</textarea>
    </div>
  `).join('');
}

function renderReplies() {
  const el = document.getElementById('replies');
  if (!replies.length) { el.innerHTML = '<div class="empty">Aucune réponse configurée</div>'; return; }
  el.innerHTML = replies.map((r, i) => `
    <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px;">
      <input type="text" value="${r}" onchange="replies[${i}]=this.value" style="margin:0;flex:1;">
      <button class="btn btn-delete" onclick="replies.splice(${i},1);renderReplies();">X</button>
    </div>
  `).join('');
}

function addNew() {
  const kw = prompt('Nouveau mot-clé (ex: CHARIOT, GUIDE, TISANE) :');
  if (!kw) return;
  const key = kw.toUpperCase().trim();
  if (keywords[key]) { alert('Ce mot-clé existe déjà !'); return; }
  const updated = {};
  updated[key] = '';
  Object.keys(keywords).forEach(k => updated[k] = keywords[k]);
  keywords = updated;
  render();
  document.querySelector('.card:first-child textarea').focus();
}

function addReply() {
  replies.push('');
  renderReplies();
  document.querySelector('#replies input:last-of-type').focus();
}

function remove(k) {
  if (!confirm('Supprimer le mot-clé ' + k + ' ?')) return;
  delete keywords[k];
  render();
}

async function saveAll() {
  const btns = document.querySelectorAll('.btn-save');
  await fetch('/api/config?token=' + TOKEN, {
    method: 'PUT',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({keywords, replies: replies.filter(r => r.trim())})
  });
  btns.forEach(btn => { btn.textContent = 'Enregistre !'; btn.classList.add('saved'); });
  setTimeout(() => btns.forEach(btn => { btn.textContent = 'Enregistrer'; btn.classList.remove('saved'); }), 2500);
}

load();
</script>
</body>
</html>"""


@app.get("/admin", response_class=HTMLResponse)
async def admin_page(token: str = Query(default="")):
    if token != ADMIN_TOKEN:
        return HTMLResponse("<h1>Accès refusé</h1><p>Ajoute ?token=TON_TOKEN à l'URL</p>", status_code=403)
    return ADMIN_HTML


@app.get("/api/keywords")
async def get_keywords(_=Depends(check_admin)):
    return CONFIG["keywords"]


@app.get("/api/config")
async def get_config(_=Depends(check_admin)):
    return {"keywords": CONFIG["keywords"], "replies": CONFIG.get("replies", [])}


@app.put("/api/config")
async def update_config(request: Request, _=Depends(check_admin)):
    data = await request.json()
    CONFIG["keywords"] = data.get("keywords", {})
    CONFIG["replies"] = data.get("replies", [])
    save_config(CONFIG)
    return {"status": "ok"}


@app.put("/api/keywords")
async def update_keywords(request: Request, _=Depends(check_admin)):
    CONFIG["keywords"] = await request.json()
    save_config(CONFIG)
    return {"status": "ok"}


# ─── Webhook ───

@app.get("/webhook")
async def verify_webhook(
    hub_mode: str = Query(alias="hub.mode", default=""),
    hub_token: str = Query(alias="hub.verify_token", default=""),
    hub_challenge: str = Query(alias="hub.challenge", default=""),
):
    if hub_mode == "subscribe" and hub_token == VERIFY_TOKEN:
        logger.info("Webhook verifie")
        return PlainTextResponse(hub_challenge)
    return PlainTextResponse("Forbidden", status_code=403)


@app.post("/webhook")
async def handle_webhook(request: Request):
    body = await request.json()
    recent_events.append(body)
    if len(recent_events) > 50:
        recent_events.pop(0)
    logger.info(f"Webhook recu: {json.dumps(body, ensure_ascii=False)[:500]}")

    for entry in body.get("entry", []):
        for change in entry.get("changes", []):
            if change.get("field") != "comments":
                continue

            value = change.get("value", {})
            comment_id = value.get("id")
            comment_text = value.get("text", "").upper().strip()
            username = value.get("from", {}).get("username", "inconnu")

            if not comment_id or comment_id in sent_comments:
                continue

            for keyword, message in CONFIG["keywords"].items():
                if keyword.upper() in comment_text:
                    await send_dm(comment_id, message, username, keyword)
                    await reply_to_comment(comment_id, username)
                    break

    return {"status": "ok"}


async def send_dm(comment_id: str, message: str, username: str, keyword: str):
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{GRAPH_API}/me/messages",
            headers={"Authorization": f"Bearer {ACCESS_TOKEN}"},
            json={
                "recipient": {"comment_id": comment_id},
                "message": {"text": message},
            },
        )

    if resp.status_code == 200:
        sent_comments.add(comment_id)
        logger.info(f"DM envoye a @{username} (mot-cle: {keyword})")
    else:
        logger.error(f"Erreur DM @{username}: {resp.status_code} - {resp.text}")


async def reply_to_comment(comment_id: str, username: str):
    replies = CONFIG.get("replies", [])
    if not replies:
        return
    reply_text = random.choice(replies)
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{GRAPH_API}/{comment_id}/replies",
            headers={"Authorization": f"Bearer {ACCESS_TOKEN}"},
            json={"message": reply_text},
        )
    if resp.status_code == 200:
        logger.info(f"Reponse commentaire @{username}: {reply_text}")
    else:
        logger.error(f"Erreur reponse commentaire @{username}: {resp.status_code} - {resp.text}")
