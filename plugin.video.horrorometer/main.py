"""
Horrorometer Kodi Addon — main entry point

Browse your Horrorometer horror watchlist on Kodi.
Authorize via OAuth Device Flow — no password needed on the device.
"""

import sys
import os
import json
import time
import urllib.parse

import xbmc
import xbmcgui
import xbmcplugin
import xbmcaddon

import requests

# --- Constants ---------------------------------------------------------------

ADDON = xbmcaddon.Addon()
ADDON_HANDLE = int(sys.argv[1])
ADDON_URL = sys.argv[0]

BASE_URL = "https://horrorometer.com"
API_BASE = f"{BASE_URL}/api/v1"
OAUTH_DEVICE_CODE = f"{BASE_URL}/api/oauth/device/code"
OAUTH_DEVICE_TOKEN = f"{BASE_URL}/api/oauth/device/token"
OAUTH_GRANT_TYPE = "urn:ietf:params:oauth:grant-type:device_code"

CLIENT_ID = "kodi-horrorometer-official"
CLIENT_NAME = "Kodi Horrorometer Addon"

# Persisted token path
PROFILE_DIR = xbmc.translatePath(ADDON.getAddonInfo("profile"))
TOKEN_FILE = os.path.join(PROFILE_DIR, "token.json")

# --- Token management --------------------------------------------------------

def load_token():
    """Load the persisted access token, or None if not authenticated."""
    try:
        with open(TOKEN_FILE, "r") as f:
            data = json.load(f)
            return data.get("access_token")
    except (IOOError, ValueError, KeyError):
        return None


def save_token(token):
    """Persist the access token to the addon profile dir."""
    if not os.path.isdir(PROFILE_DIR):
        os.makedirs(PROFILE_DIR)
    with open(TOKEN_FILE, "w") as f:
        json.dump({"access_token": token}, f)


def clear_token():
    """Remove the persisted token (sign out)."""
    try:
        os.remove(TOKEN_FILE)
    except OSError:
        pass


def auth_headers():
    """Return Authorization header dict, or None if not authenticated."""
    token = load_token()
    if not token:
        return None
    return {"Authorization": f"Bearer {token}"}


# --- OAuth Device Flow -------------------------------------------------------

def start_device_flow():
    """
    Initiate the OAuth Device Flow. Shows the user code on screen and
    instructs the user to visit the activation URL. Polls until approved
    or expired. Returns the access token on success, None on failure.
    """
    try:
        resp = requests.post(OAUTH_DEVICE_CODE, json={
            "client_id": CLIENT_ID,
            "client_name": CLIENT_NAME,
        }, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        xbmcgui.Dialog().ok(
            "Horrorometer",
            f"Failed to start authorization.\n\n{e}",
        )
        return None

    device_code = data["device_code"]
    user_code = data["user_code"]
    verification_url = data["verification_uri_complete"]
    expires_in = data["expires_in"]
    interval = data["interval"]

    # Show the code + URL to the user
    dialog = xbmcgui.Dialog()
    choice = dialog.ok(
        "Authorize Horrorometer",
        f"Go to:\n{verification_url}\n\n"
        f"and approve access for Kodi.\n\n"
        f"Code: {user_code}\n\n"
        f"Expires in {expires_in // 60} minutes.\n\n"
        f"Press OK once you've approved, or Cancel to abort.",
    )
    if not choice:
        return None

    # Poll for the token
    deadline = time.time() + expires_in
    while time.time() < deadline:
        time.sleep(interval)
        try:
            resp = requests.post(OAUTH_DEVICE_TOKEN, json={
                "grant_type": OAUTH_GRANT_TYPE,
                "device_code": device_code,
            }, timeout=10)
            body = resp.json()
        except requests.RequestException:
            continue

        if resp.status_code == 200:
            token = body["access_token"]
            save_token(token)
            xbmcgui.Dialog().notification(
                "Horrorometer", "Successfully authorized!", xbmcgui.NOTIFICATION_INFO
            )
            return token

        err = body.get("error", "")
        if err == "authorization_pending":
            continue
        elif err == "slow_down":
            interval = body.get("interval", interval * 2)
            continue
        elif err == "access_denied":
            xbmcgui.Dialog().ok("Horrorometer", "Authorization denied.")
            return None
        elif err == "expired_token":
            xbmcgui.Dialog().ok("Horrorometer", "The code expired. Please try again.")
            return None
        else:
            xbmcgui.Dialog().ok("Horrorometer", f"Authorization failed: {err}")
            return None

    xbmcgui.Dialog().ok("Horrorometer", "The code expired. Please try again.")
    return None


# --- API calls ---------------------------------------------------------------

def fetch_watchlist(status=None, content_type=None):
    """
    Fetch the user's watchlist from the Horrorometer API.
    Returns a list of watchlist item dicts, or None on auth failure.
    """
    headers = auth_headers()
    if not headers:
        return None

    params = {}
    if status:
        params["status"] = status
    if content_type:
        params["type"] = content_type

    try:
        resp = requests.get(
            f"{API_BASE}/watchlist",
            headers=headers,
            params=params,
            timeout=15,
        )
    except requests.RequestException as e:
        xbmcgui.Dialog().notification(
            "Horrorometer", f"Network error: {e}", xbmcgui.NOTIFICATION_ERROR
        )
        return []

    if resp.status_code == 401:
        # Token revoked or expired — clear it
        clear_token()
        xbmcgui.Dialog().notification(
            "Horrorometer",
            "Token expired or revoked. Please re-authorize.",
            xbmcgui.NOTIFICATION_ERROR,
        )
        return None

    if resp.status_code != 200:
        xbmcgui.Dialog().notification(
            "Horrorometer",
            f"Failed to fetch watchlist (HTTP {resp.status_code})",
            xbmcgui.NOTIFICATION_ERROR,
        )
        return []

    data = resp.json()
    return data.get("watchlist", [])


def mark_watched(title_id):
    """Mark a title as watched via the API."""
    headers = auth_headers()
    if not headers:
        return False

    try:
        resp = requests.post(
            f"{API_BASE}/watchlist/{title_id}/watch",
            headers=headers,
            timeout=15,
        )
    except requests.RequestException:
        return False

    return resp.status_code == 200


# --- Kodi UI -----------------------------------------------------------------

def build_url(query):
    """Build a plugin URL with the given query parameters."""
    return f"{ADDON_URL}?{urllib.parse.urlencode(query)}"


def list_root():
    """Show the root menu: filters and watchlist."""
    if not load_token():
        # Not authenticated — offer to authorize
        listitem = xbmcgui.ListItem(label="Authorize Horrorometer")
        listitem.setInfo("video", {"title": "Authorize Horrorometer"})
        xbmcplugin.addDirectoryItem(
            ADDON_HANDLE,
            build_url({"action": "authorize"}),
            listitem,
            isFolder=False,
        )
        xbmcplugin.endOfDirectory(ADDON_HANDLE)
        return

    # Authenticated — show filter options
    items = [
        ("All Watchlist", {}),
        ("Movies", {"type": "movie"}),
        ("TV Shows", {"type": "tv"}),
        ("Books", {"type": "book"}),
        ("Pending (Not Watched)", {"status": "pending"}),
        ("Watched", {"status": "watched"}),
        ("Sign Out", {"action": "signout"}),
    ]

    for label, params in items:
        listitem = xbmcgui.ListItem(label=label)
        is_folder = params.get("action") not in ("signout",)
        xbmcplugin.addDirectoryItem(
            ADDON_HANDLE,
            build_url(params),
            listitem,
            isFolder=is_folder,
        )

    xbmcplugin.endOfDirectory(ADDON_HANDLE)


def list_watchlist(content_type=None, status=None):
    """Fetch and display the watchlist as a Kodi directory."""
    items = fetch_watchlist(status=status, content_type=content_type)
    if items is None:
        # Auth failure — redirect to root
        list_root()
        return

    for item in items:
        title = item.get("title", "Unknown")
        year = item.get("year", "")
        poster = item.get("poster_url", "")
        watched = item.get("watched", False)
        in_watchlist = item.get("in_watchlist", True)
        item_type = item.get("type", "movie")
        title_id = item.get("id", "")
        rating = item.get("user_rating_average")
        rating_count = item.get("user_rating_count")
        synopsis = item.get("synopsis", "")

        # Build display label
        label = f"{title} ({year})" if year else title
        if watched:
            label = f"[Watched] {label}"

        listitem = xbmcgui.ListItem(label=label, offscreen=True)
        listitem.setInfo("video", {
            "title": title,
            "year": year or 0,
            "plot": synopsis or "",
            "mediatype": "movie" if item_type == "movie" else "episode",
        })
        if poster:
            listitem.setArt({"poster": poster, "icon": poster, "thumb": poster})
        if rating:
            listitem.setInfo("video", {"rating": float(rating)})
            listitem.setProperty("rating", str(rating))
            if rating_count:
                listitem.setProperty("rating_count", str(rating_count))

        # Context menu: mark as watched
        if not watched:
            context_menu = [
                ("Mark as Watched", f"RunPlugin({build_url({'action': 'watch', 'id': title_id})})")
            ]
            listitem.addContextMenuItems(context_menu)

        xbmcplugin.addDirectoryItem(
            ADDON_HANDLE,
            build_url({"action": "watch", "id": title_id}),
            listitem,
            isFolder=False,
        )

    xbmcplugin.endOfDirectory(ADDON_HANDLE, succeeded=len(items) > 0)


def handle_action(action, title_id=None):
    """Handle non-list actions: authorize, signout, mark watched."""
    if action == "authorize":
        token = start_device_flow()
        if token:
            xbmc.executebuiltin(f"Container.Refresh")
        return

    if action == "signout":
        clear_token()
        xbmcgui.Dialog().notification(
            "Horrorometer", "Signed out.", xbmcgui.NOTIFICATION_INFO
        )
        xbmc.executebuiltin(f"Container.Refresh")
        return

    if action == "watch":
        if title_id:
            if mark_watched(title_id):
                xbmcgui.Dialog().notification(
                    "Horrorometer", "Marked as watched!", xbmcgui.NOTIFICATION_INFO
                )
                xbmc.executebuiltin(f"Container.Refresh")
            else:
                xbmcgui.Dialog().notification(
                    "Horrorometer", "Failed to mark as watched.",
                    xbmcgui.NOTIFICATION_ERROR,
                )
        return


# --- Entry point -------------------------------------------------------------

def router():
    """Route the plugin URL to the appropriate handler."""
    parsed = urllib.parse.parse_qs(sys.argv[2][1:]) if len(sys.argv) > 2 else {}
    action = parsed.get("action", [None])[0]
    content_type = parsed.get("type", [None])[0]
    status = parsed.get("status", [None])[0]
    title_id = parsed.get("id", [None])[0]

    if action == "authorize":
        handle_action("authorize")
    elif action == "signout":
        handle_action("signout")
    elif action == "watch":
        handle_action("watch", title_id)
    elif content_type or status:
        list_watchlist(content_type=content_type, status=status)
    else:
        list_root()


if __name__ == "__main__":
    router()