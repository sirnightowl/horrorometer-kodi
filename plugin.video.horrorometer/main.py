"""
Horrorometer Kodi Addon — main entry point

Browse your Horrorometer horror watchlist on Kodi.
Authorize via OAuth Device Flow — no password needed on the device.
"""

import sys
import os
import json
import time
import tempfile
import urllib.parse

import xbmc
import xbmcgui
import xbmcplugin
import xbmcaddon
import xbmcvfs

import requests

# --- Constants ---------------------------------------------------------------

ADDON = xbmcaddon.Addon()
ADDON_HANDLE = int(sys.argv[1])
ADDON_URL = sys.argv[0]

BASE_URL = "https://horrorometer.com"
API_BASE = "{}/api/v1".format(BASE_URL)
OAUTH_DEVICE_CODE = "{}/api/oauth/device/code".format(BASE_URL)
OAUTH_DEVICE_TOKEN = "{}/api/oauth/device/token".format(BASE_URL)
OAUTH_GRANT_TYPE = "urn:ietf:params:oauth:grant-type:device_code"

CLIENT_ID = "kodi-horrorometer-official"
CLIENT_NAME = "Kodi Horrorometer Addon"

# Persisted token path
PROFILE_DIR = xbmcvfs.translatePath(ADDON.getAddonInfo("profile"))
TOKEN_FILE = os.path.join(PROFILE_DIR, "token.json")

# --- Token management --------------------------------------------------------

def load_token():
    """Load the persisted access token, or None if not authenticated."""
    try:
        with open(TOKEN_FILE, encoding="utf-8") as f:
            data = json.load(f)
            token = data.get("access_token") if isinstance(data, dict) else None
            return token if isinstance(token, str) and token else None
    except (OSError, ValueError):
        return None


def save_token(token):
    """Persist the access token to the addon profile dir."""
    os.makedirs(PROFILE_DIR, mode=0o700, exist_ok=True)
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=PROFILE_DIR, delete=False
        ) as f:
            temporary_path = f.name
            json.dump({"access_token": token}, f)
        os.replace(temporary_path, TOKEN_FILE)
    finally:
        if temporary_path is not None:
            try:
                os.unlink(temporary_path)
            except FileNotFoundError:
                pass


def clear_token():
    """Remove the persisted token (sign out)."""
    try:
        os.remove(TOKEN_FILE)
    except FileNotFoundError:
        pass


def notify(message, level=xbmcgui.NOTIFICATION_ERROR):
    xbmcgui.Dialog().notification("Horrorometer", message, level)


def handle_expired_token(headers):
    if auth_headers() != headers:
        return
    try:
        clear_token()
    except OSError:
        notify("Could not remove the expired sign-in. Check Kodi's profile permissions.")
        return
    notify("Sign-in expired or was revoked. Please authorize Horrorometer again.")


def auth_headers():
    """Return Authorization header dict, or None if not authenticated."""
    token = load_token()
    if not token:
        return None
    return {"Authorization": "Bearer {}".format(token)}


# --- OAuth Device Flow -------------------------------------------------------

def start_device_flow():
    """
    Initiate the OAuth Device Flow. Shows the user code on screen and
    instructs the user to visit the activation URL. Polls until approved
    or expired. Returns the access token on success, None on failure.
    """
    dialog = xbmcgui.Dialog()
    try:
        resp = requests.post(OAUTH_DEVICE_CODE, json={
            "client_id": CLIENT_ID,
            "client_name": CLIENT_NAME,
        }, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        device_code = data["device_code"]
        user_code = data["user_code"]
        verification_url = data["verification_uri"]
        expires_in = data["expires_in"]
        interval = data.get("interval", 5)
        if (
            not all(isinstance(value, str) and value for value in
                    (device_code, user_code, verification_url))
            or type(expires_in) is not int or expires_in <= 0
            or type(interval) is not int or interval <= 0
        ):
            raise ValueError("Invalid device authorization response")
    except (requests.RequestException, KeyError, TypeError, ValueError):
        dialog.ok("Horrorometer", "Could not start authorization. Please try again.")
        return None

    deadline = time.monotonic() + expires_in
    monitor = xbmc.Monitor()
    progress = xbmcgui.DialogProgress()
    message = (
        "On your phone or computer, go to {}.\n"
        "Enter code {} and approve access for Kodi."
    ).format(verification_url, user_code)
    progress.create("Authorize Horrorometer", message)
    error = "The code expired. Please try again."
    try:
        next_poll = time.monotonic() + interval
        while time.monotonic() < deadline:
            if progress.iscanceled() or monitor.abortRequested():
                return None
            now = time.monotonic()
            progress.update(int((1 - max(0, deadline - now) / expires_in) * 100), message)
            if now < next_poll:
                if monitor.waitForAbort(min(0.5, next_poll - now, max(0, deadline - now))):
                    return None
                continue
            if now >= deadline:
                break
            try:
                resp = requests.post(OAUTH_DEVICE_TOKEN, json={
                    "grant_type": OAUTH_GRANT_TYPE,
                    "device_code": device_code,
                }, timeout=min(5, deadline - now))
                if resp.status_code == 429:
                    retry_after = resp.headers.get("Retry-After", "")
                    interval += 5
                    if retry_after.isascii() and retry_after.isdecimal() and len(retry_after) <= 10:
                        interval = max(interval, int(retry_after))
                    next_poll = time.monotonic() + interval
                    continue
                body = resp.json()
            except (requests.ConnectionError, requests.Timeout):
                interval *= 2
                next_poll = time.monotonic() + interval
                continue
            except requests.RequestException:
                error = "Could not check authorization. Please try again."
                break

            if progress.iscanceled() or monitor.abortRequested():
                return None
            if not isinstance(body, dict):
                error = "Horrorometer returned an invalid authorization response."
                break
            token = body.get("access_token")
            if resp.status_code == 200 and isinstance(token, str) and token:
                try:
                    save_token(token)
                except OSError:
                    error = "Could not save your sign-in. Check Kodi's profile permissions."
                    break
                notify("Signed in to Horrorometer.", xbmcgui.NOTIFICATION_INFO)
                return token

            outcome = body.get("error")
            if outcome == "slow_down":
                server_interval = body.get("interval")
                interval += 5
                if type(server_interval) is int:
                    interval = max(interval, server_interval)
            elif outcome == "access_denied":
                error = "Authorization denied."
                break
            elif outcome == "expired_token":
                break
            elif outcome != "authorization_pending":
                error = "Authorization failed. Please try again."
                break
            next_poll = time.monotonic() + interval
    finally:
        progress.close()

    dialog.ok("Horrorometer", error)
    return None


# --- API calls ---------------------------------------------------------------

class WatchlistError(Exception):
    """The watchlist could not be loaded."""


def fetch_watchlist(status=None, content_type=None):
    """
    Fetch the user's watchlist from the Horrorometer API.
    Returns a list of watchlist item dicts, or None on auth failure.
    """
    headers = auth_headers()
    if not headers:
        return None

    params = {"all": "true"}
    if status:
        params["status"] = status
    if content_type:
        params["type"] = content_type

    try:
        resp = requests.get(
            "{}/watchlist".format(API_BASE),
            headers=headers,
            params=params,
            timeout=15,
        )
    except requests.RequestException as error:
        raise WatchlistError("Could not reach Horrorometer. Check your connection.") from error

    if resp.status_code == 401:
        handle_expired_token(headers)
        return None

    if resp.status_code != 200:
        raise WatchlistError(
            "Could not load the watchlist (HTTP {}).".format(resp.status_code)
        )

    try:
        data = resp.json()
    except ValueError as error:
        raise WatchlistError("Horrorometer returned an invalid watchlist.") from error
    items = data.get("watchlist") if isinstance(data, dict) else None
    if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
        raise WatchlistError("Horrorometer returned an invalid watchlist.")
    return items


def mark_watched(title_id):
    """Mark a title as watched via the API."""
    headers = auth_headers()
    if not headers:
        notify("Authorize Horrorometer before marking a title as watched.")
        return False

    try:
        resp = requests.post(
            "{}/watchlist/{}/watch".format(API_BASE, urllib.parse.quote(title_id, safe="")),
            headers=headers,
            timeout=15,
        )
    except requests.RequestException:
        notify("Could not confirm the update. Refresh the watchlist and check the title.")
        return False

    if resp.status_code == 401:
        handle_expired_token(headers)
        xbmc.executebuiltin("Container.Update({},replace)".format(ADDON_URL))
        return False
    if resp.status_code != 200:
        notify("Could not mark the title as watched (HTTP {}).".format(resp.status_code))
        return False
    try:
        data = resp.json()
    except ValueError:
        data = None
    if isinstance(data, dict) and data.get("success") is True:
        return True
    notify("Could not confirm the update. Refresh the watchlist and check the title.")
    return False


# --- Kodi UI -----------------------------------------------------------------

def build_url(query):
    """Build a plugin URL with the given query parameters."""
    return "{}?{}".format(ADDON_URL, urllib.parse.urlencode(query))


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
        xbmcplugin.endOfDirectory(ADDON_HANDLE, cacheToDisc=False)
        return

    # Authenticated — show filter options
    items = [
        ("All Watchlist", {"action": "list"}),
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

    xbmcplugin.endOfDirectory(ADDON_HANDLE, cacheToDisc=False)


def list_watchlist(content_type=None, status=None):
    """Fetch and display the watchlist as a Kodi directory."""
    try:
        items = fetch_watchlist(status=status, content_type=content_type)
    except WatchlistError as error:
        notify(str(error))
        xbmcplugin.endOfDirectory(ADDON_HANDLE, succeeded=False, cacheToDisc=False)
        return
    if items is None:
        list_root()
        return

    if not items:
        notify(
            "No titles match this filter." if content_type or status else "Your watchlist is empty.",
            xbmcgui.NOTIFICATION_INFO,
        )

    for item in items:
        title_id = item.get("id")
        if not isinstance(title_id, str) or not title_id:
            continue
        title = item.get("title") or "Unknown"
        year = item.get("year")
        poster = item.get("poster_url")
        watched = item.get("watched", False)
        item_type = item.get("type", "movie")
        rating, rating_count = get_rating(item)

        # Build display label
        label = "{} ({})".format(title, year) if year else title
        if watched:
            label = "[Watched] {}".format(label)

        listitem = xbmcgui.ListItem(label=label, offscreen=True)
        info = {
            "title": title,
            "year": year or 0,
            "plot": item.get("synopsis") or "",
        }
        media_type = {"movie": "movie", "tv": "tvshow"}.get(item_type)
        if media_type:
            info["mediatype"] = media_type
        if rating is not None:
            info["rating"] = rating * 2  # Horrorometer uses 0–5, Kodi uses 0–10.
            listitem.setProperty("rating", str(rating))
            if rating_count is not None:
                listitem.setProperty("rating_count", str(rating_count))
        listitem.setInfo("video", info)
        if poster:
            listitem.setArt({"poster": poster, "icon": poster, "thumb": poster})

        # Context menu: mark as watched (only via context menu, not click)
        if not watched:
            context_menu = [
                ("Mark as Watched",
                 "RunPlugin({})".format(build_url({"action": "watch", "id": title_id})))
            ]
            listitem.addContextMenuItems(context_menu)

        # Clicking the item shows an info dialog — does NOT mark as watched.
        # The mark-watched action is only via the context menu above.
        details = {"action": "info", "id": title_id}
        if status:
            details["status"] = status
        if content_type:
            details["type"] = content_type
        xbmcplugin.addDirectoryItem(
            ADDON_HANDLE,
            build_url(details),
            listitem,
            isFolder=False,
        )

    xbmcplugin.endOfDirectory(ADDON_HANDLE, cacheToDisc=False)


def get_rating(item):
    """Accept the server's current and documented rating fields."""
    rating = item.get("userRatingAverage", item.get("user_rating_average"))
    count = item.get("userRatingCount", item.get("user_rating_count"))
    try:
        rating = float(rating)
    except (TypeError, ValueError):
        rating = None
    return rating, count


def show_info(title_id, content_type=None, status=None):
    """Find a title in the same watchlist view and show its details."""
    try:
        items = fetch_watchlist(status=status, content_type=content_type)
    except WatchlistError as error:
        notify(str(error))
        return
    if items is None:
        return

    for item in items:
        if item.get("id") == title_id:
            title = item.get("title") or "Unknown"
            year = item.get("year")
            synopsis = item.get("synopsis") or "No synopsis available."
            rating, rating_count = get_rating(item)
            watched = item.get("watched", False)

            info_text = "{} ({})\n\n".format(title, year) if year else "{}\n\n".format(title)
            if rating is not None:
                info_text += "Rating: {}/5".format(rating)
                if rating_count:
                    info_text += " ({} votes)".format(rating_count)
                info_text += "\n"
            if watched:
                info_text += "Status: Watched\n"
            info_text += "\n{}".format(synopsis)

            xbmcgui.Dialog().textviewer("Horrorometer", info_text)
            return

    xbmcgui.Dialog().notification(
        "Horrorometer", "Title not found.", xbmcgui.NOTIFICATION_WARNING
    )


def handle_action(action, title_id=None, content_type=None, status=None):
    """Handle non-list actions: authorize, signout, mark watched, info."""
    if action == "authorize":
        token = start_device_flow()
        if token:
            xbmc.executebuiltin("Container.Refresh")
        return

    if action == "signout":
        try:
            clear_token()
        except OSError:
            notify("Could not sign out. Check Kodi's profile permissions.")
            return
        xbmcgui.Dialog().notification(
            "Horrorometer", "Signed out.", xbmcgui.NOTIFICATION_INFO
        )
        xbmc.executebuiltin("Container.Refresh")
        return

    if action == "watch":
        if title_id:
            if mark_watched(title_id):
                xbmcgui.Dialog().notification(
                    "Horrorometer", "Marked as watched!", xbmcgui.NOTIFICATION_INFO
                )
                xbmc.executebuiltin("Container.Refresh")
        return

    if action == "info":
        if title_id:
            show_info(title_id, content_type=content_type, status=status)
        return


# --- Entry point -------------------------------------------------------------

def router():
    """Route the plugin URL to the appropriate handler."""
    parsed = urllib.parse.parse_qs(sys.argv[2][1:]) if len(sys.argv) > 2 else {}
    action = parsed.get("action", [None])[0]
    content_type = parsed.get("type", [None])[0]
    status = parsed.get("status", [None])[0]
    title_id = parsed.get("id", [None])[0]

    if action in ("authorize", "signout", "watch", "info"):
        handle_action(action, title_id, content_type=content_type, status=status)
    elif action == "list" or content_type or status:
        list_watchlist(content_type=content_type, status=status)
    else:
        list_root()


if __name__ == "__main__":
    router()
