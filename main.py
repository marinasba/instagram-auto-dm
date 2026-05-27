import os
import json
import logging
import httpx
from fastapi import FastAPI, Request, Query, Depends, HTTPException
from fastapi.responses import PlainTextResponse, HTMLResponse
from pydantic import BaseModel

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


def check_admin(token: str = Query(default="")):
    if token != ADMIN_TOKEN:
        raise HTTPException(status_code=403, detail="Token invalide")


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
  .btn-save { background: #4a7c59; color: white; width: 100%; padding: 12px; font-size: 1em; }
  .btn-save:hover { background: #3d6b4a; }
  .btn-add { background: white; color: #4a7c59; border: 2px dashed #4a7c59; width: 100%; padding: 14px; font-size: 1em; margin-bottom: 16px; border-radius: 12px; }
  .btn-add:hover { background: #f0f7f2; }
  textarea { width: 100%; border: 1px solid #ddd; border-radius: 8px; padding: 12px; font-family: inherit; font-size: 0.9em; resize: vertical; min-height: 100px; }
  input[type=text] { width: 100%; border: 1px solid #ddd; border-radius: 8px; padding: 10px 12px; font-family: inherit; font-size: 1em; margin-bottom: 12px; }
  .toast { position: fixed; bottom: 20px; left: 50%; transform: translateX(-50%); background: #4a7c59; color: white; padding: 12px 24px; border-radius: 8px; display: none; font-weight: 600; }
  .empty { text-align: center; color: #999; padding: 40px; }
</style>
</head>
<body>
<h1>Messages Auto Instagram</h1>
<p class="subtitle">gariguettes_fr</p>

<button class="btn btn-add" onclick="addNew()">+ Ajouter un mot-clé</button>

<div id="keywords"></div>

<button class="btn btn-save" onclick="saveAll()">Enregistrer</button>

<div class="toast" id="toast">Enregistré !</div>

<script>
const TOKEN = new URLSearchParams(location.search).get('token');
let keywords = {};

async function load() {
  const r = await fetch('/api/keywords?token=' + TOKEN);
  keywords = await r.json();
  render();
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

function addNew() {
  const kw = prompt('Nouveau mot-clé (ex: CHARIOT, GUIDE, TISANE) :');
  if (!kw) return;
  const key = kw.toUpperCase().trim();
  if (keywords[key]) { alert('Ce mot-clé existe déjà !'); return; }
  keywords[key] = '';
  render();
  document.querySelector('.card:last-child textarea').focus();
}

function remove(k) {
  if (!confirm('Supprimer le mot-clé ' + k + ' ?')) return;
  delete keywords[k];
  render();
}

async function saveAll() {
  await fetch('/api/keywords?token=' + TOKEN, {
    method: 'PUT',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(keywords)
  });
  const t = document.getElementById('toast');
  t.style.display = 'block';
  setTimeout(() => t.style.display = 'none', 2000);
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
