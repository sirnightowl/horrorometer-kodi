import json
from pathlib import Path
import runpy
import stat
import sys
from tempfile import TemporaryDirectory
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from urllib.parse import urlsplit

import requests


ADDON = Path(__file__).resolve().parents[1] / "plugin.video.horrorometer" / "main.py"
PLUGIN_URL = "plugin://plugin.video.horrorometer/"


def response(status, payload, headers=None):
    reply = requests.Response()
    reply.status_code = status
    reply._content = json.dumps(payload).encode()
    reply.headers.update(headers or {})
    return reply


class AddonTest(unittest.TestCase):
    def setUp(self):
        profile = self.enter(TemporaryDirectory())
        modules = {
            name: ModuleType(name)
            for name in ("xbmc", "xbmcgui", "xbmcplugin", "xbmcaddon", "xbmcvfs")
        }
        self.xbmc = modules["xbmc"]
        self.gui = modules["xbmcgui"]
        self.plugin = modules["xbmcplugin"]
        self.xbmc.executebuiltin = Mock()
        self.gui.Dialog = Mock()
        self.gui.DialogProgress = Mock()
        self.gui.DialogProgress.return_value.iscanceled.return_value = False
        self.gui.ListItem = Mock()
        for level in ("INFO", "WARNING", "ERROR"):
            setattr(self.gui, "NOTIFICATION_" + level, level)
        self.plugin.addDirectoryItem = Mock()
        self.plugin.endOfDirectory = Mock()
        modules["xbmcaddon"].Addon = lambda: SimpleNamespace(getAddonInfo=lambda _: profile)
        modules["xbmcvfs"].translatePath = lambda path: path
        self.enter(patch.dict(sys.modules, modules))
        self.enter(patch.object(sys, "argv", [PLUGIN_URL, "1", ""]))
        self.addon = runpy.run_path(str(ADDON))
        self.token_file = Path(profile) / "token.json"

    def enter(self, context):
        result = context.__enter__()
        self.addCleanup(context.__exit__, None, None, None)
        return result

    def open_link(self, url):
        sys.argv[2] = "?" + urlsplit(url).query
        self.addon["router"]()

    def route(self, **query):
        self.open_link(self.addon["build_url"](query))

    def notices(self):
        return [call.args[1] for call in self.gui.Dialog.return_value.notification.call_args_list]

    def device_session(self, poll_responses):
        clock = [0]
        self.enter(patch("time.monotonic", side_effect=lambda: clock[0]))

        def wait(seconds):
            clock[0] += seconds
            return False

        self.xbmc.Monitor = lambda: SimpleNamespace(
            abortRequested=lambda: False, waitForAbort=wait,
        )
        poll_times = []
        code = {
            "device_code": "device",
            "user_code": "ABCD2345",
            "verification_uri": "https://horrorometer.com/activate",
            "expires_in": 60,
            "interval": 5,
        }

        def post(url, **kwargs):
            if url.endswith("/code"):
                return response(200, code)
            poll_times.append(clock[0])
            result = next(poll_responses)
            if isinstance(result, Exception):
                raise result
            return result

        self.enter(patch("requests.post", side_effect=post))
        return poll_times

    def test_device_sign_in_then_all_watchlist(self):
        self.route()
        authorize_url = self.plugin.addDirectoryItem.call_args.args[1]
        poll_times = self.device_session(iter([
            response(400, {"error": "authorization_pending"}),
            requests.Timeout(),
            response(429, {}, {"Retry-After": "17"}),
            response(200, {"access_token": "ho_test"}),
        ]))

        self.open_link(authorize_url)
        self.assertEqual(poll_times, [5, 10, 20, 37])
        self.gui.DialogProgress.return_value.close.assert_called_once()
        self.assertEqual(self.addon["load_token"](), "ho_test")
        if sys.platform != "win32":
            self.assertEqual(stat.S_IMODE(self.token_file.stat().st_mode), 0o600)

        self.plugin.addDirectoryItem.reset_mock()
        self.route()
        all_url = self.plugin.addDirectoryItem.call_args_list[0].args[1]
        with patch("requests.get", return_value=response(200, {"watchlist": []})) as get:
            self.open_link(all_url)
        self.assertEqual(get.call_args.kwargs["params"], {"all": "true"})
        self.assertEqual(get.call_args.kwargs["headers"], {"Authorization": "Bearer ho_test"})
        self.assertEqual(self.plugin.endOfDirectory.call_args.kwargs, {"cacheToDisc": False})
        self.assertIn("Your watchlist is empty.", self.notices())

    def test_cancel_stops_polling_and_closes_dialog(self):
        poll_times = self.device_session(iter([]))
        self.gui.DialogProgress.return_value.iscanceled.return_value = True
        self.route(action="authorize")
        self.assertEqual(poll_times, [])
        self.gui.DialogProgress.return_value.close.assert_called_once()
        self.assertFalse(self.token_file.exists())

    def test_book_details_use_the_filter_and_only_context_menu_marks_watched(self):
        self.addon["save_token"]("ho_test")
        book = {"id": "book-1", "title": "A Book", "type": "book",
                "userRatingAverage": 4.2, "userRatingCount": 12}
        with patch("requests.get", return_value=response(200, {"watchlist": [book]})) as get:
            with patch("requests.post", return_value=response(200, {"success": True})) as post:
                self.route(type="book")
                self.open_link(self.plugin.addDirectoryItem.call_args.args[1])
                self.assertEqual(get.call_args.kwargs["params"], {"all": "true", "type": "book"})
                details = self.gui.Dialog.return_value.textviewer.call_args.args[1]
                self.assertIn("Rating: 4.2/5 (12 votes)", details)
                post.assert_not_called()

                menu = self.gui.ListItem.return_value.addContextMenuItems.call_args.args[0]
                self.open_link(menu[0][1][len("RunPlugin("):-1])
                self.assertTrue(post.call_args.args[0].endswith("/watchlist/book-1/watch"))
                self.assertIn("Marked as watched!", self.notices())

    def test_bad_watchlist_response_does_not_claim_list_is_empty(self):
        self.addon["save_token"]("ho_test")
        malformed = response(200, None)
        malformed._content = b"<html>error</html>"
        with patch("requests.get", side_effect=[requests.ConnectionError(), malformed]):
            self.route(action="list")
            self.route(action="list")
        self.assertEqual(len(self.notices()), 2)
        self.assertIn("Could not reach Horrorometer", self.notices()[0])
        self.assertIn("invalid watchlist", self.notices()[1])
        self.assertFalse(self.plugin.endOfDirectory.call_args.kwargs["succeeded"])

    def test_revoked_token_recovers_and_failed_signout_is_reported(self):
        self.token_file.write_text("[]", encoding="utf-8")
        self.assertIsNone(self.addon["load_token"]())
        self.addon["save_token"]("ho_test")
        with patch("os.remove", side_effect=PermissionError):
            self.route(action="signout")
        self.assertIn("Could not sign out.", self.notices()[-1])
        self.assertEqual(self.addon["load_token"](), "ho_test")

        with patch("requests.post", return_value=response(401, {})):
            self.route(action="watch", id="title-id")
        self.assertIsNone(self.addon["load_token"]())
        self.route()
        self.assertIn("action=authorize", self.plugin.addDirectoryItem.call_args.args[1])


if __name__ == "__main__":
    unittest.main()
