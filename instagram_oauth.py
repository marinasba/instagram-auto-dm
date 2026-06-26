import os
import re
import httpx

META_APP_ID = os.environ.get("META_APP_ID", "1445863310917375")
META_APP_SECRET = os.environ.get("META_APP_SECRET", "")
REDIRECT_URI = os.environ.get("REDIRECT_URI", "")

AUTH_URL = "https://www.instagram.com/oauth/authorize"
TOKEN_URL = "https://api.instagram.com/oauth/access_token"
GRAPH_URL = "https://graph.instagram.com"


def get_authorize_url(state: str = "") -> str:
    return (
        f"{AUTH_URL}"
        f"?client_id={META_APP_ID}"
        f"&redirect_uri={REDIRECT_URI}"
        f"&scope=instagram_business_basic,instagram_business_manage_messages,instagram_business_manage_comments"
        f"&response_type=code"
        f"&state={state}"
    )


async def exchange_code(code: str) -> dict:
    async with httpx.AsyncClient() as client:
        resp = await client.post(TOKEN_URL, data={
            "client_id": META_APP_ID,
            "client_secret": META_APP_SECRET,
            "grant_type": "authorization_code",
            "redirect_uri": REDIRECT_URI,
            "code": code,
        })
    if resp.status_code != 200:
        return {"error": resp.text}
    return resp.json()


async def get_long_lived_token(short_token: str) -> dict:
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{GRAPH_URL}/access_token", params={
            "grant_type": "ig_exchange_token",
            "client_secret": META_APP_SECRET,
            "access_token": short_token,
        })
    if resp.status_code != 200:
        return {"error": resp.text}
    return resp.json()


async def get_profile(access_token: str) -> dict:
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{GRAPH_URL}/v21.0/me", params={
            "fields": "id,username",
            "access_token": access_token,
        })
    if resp.status_code != 200:
        return {"error": resp.text}
    return resp.json()


def parse_shortcode(post_url: str) -> str | None:
    if not post_url:
        return None
    m = re.search(r"/(p|reel|reels|tv)/([^/?#]+)", post_url)
    return m.group(2) if m else None


async def resolve_post_info(post_url: str, ig_user_id: str, access_token: str, max_pages: int = 10) -> dict | None:
    """Look up a post's media_id and a usable thumbnail URL on the connected IG account.

    Returns {id, thumbnail, permalink, media_type} or None if not found.
    """
    shortcode = parse_shortcode(post_url)
    if not shortcode or not ig_user_id or not access_token:
        return None

    url = f"{GRAPH_URL}/v21.0/{ig_user_id}/media"
    params: dict = {
        "fields": "id,permalink,media_url,thumbnail_url,media_type",
        "access_token": access_token,
        "limit": 100,
    }

    async with httpx.AsyncClient(timeout=20.0) as client:
        for _ in range(max_pages):
            resp = await client.get(url, params=params)
            if resp.status_code != 200:
                return None
            data = resp.json()
            for media in data.get("data", []):
                permalink = media.get("permalink", "")
                if f"/{shortcode}/" in permalink or permalink.endswith(f"/{shortcode}"):
                    media_type = media.get("media_type", "")
                    if media_type == "VIDEO":
                        thumbnail = media.get("thumbnail_url") or media.get("media_url")
                    else:
                        thumbnail = media.get("media_url") or media.get("thumbnail_url")
                    return {
                        "id": str(media.get("id")),
                        "thumbnail": thumbnail,
                        "permalink": permalink,
                        "media_type": media_type,
                    }
            next_url = data.get("paging", {}).get("next")
            if not next_url:
                return None
            url = next_url
            params = {}
    return None


async def resolve_media_id(post_url: str, ig_user_id: str, access_token: str, max_pages: int = 10) -> str | None:
    info = await resolve_post_info(post_url, ig_user_id, access_token, max_pages)
    return info["id"] if info else None
