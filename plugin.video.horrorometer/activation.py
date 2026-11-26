"""The TV sign-in dialog. The device link is rendered locally."""

from pathlib import Path
from tempfile import TemporaryDirectory

import qrcode
import xbmcgui
import xbmcvfs


class ActivationWindow(xbmcgui.WindowXMLDialog):
    def __init__(self, *args):
        self.cancelled = False

    def onClick(self, control_id):
        if control_id == 10:
            self.cancelled = True

    def onAction(self, action):
        if action.getId() in (9, 10, 92):  # Parent, previous menu, back.
            self.cancelled = True


class QrActivationDialog:
    def __init__(self, addon_path, verification_url, user_code, complete_url):
        self.directory = TemporaryDirectory(
            prefix="horrorometer-qr-", dir=xbmcvfs.translatePath("special://temp/")
        )
        try:
            image_path = Path(self.directory.name) / "activation.png"
            qrcode.make(complete_url, box_size=12, border=4).save(str(image_path))
            self.window = ActivationWindow("activation.xml", addon_path, "Default", "1080i")
            self.window.setProperty("Horrorometer.QR", str(image_path))
            self.window.setProperty("Horrorometer.URL", verification_url)
            self.window.setProperty("Horrorometer.Code", user_code)
            self.window.show()
        except Exception:
            self.directory.cleanup()
            raise

    def update(self, _percent):
        # The waiting message stays visible until the phone approves the code.
        pass

    def iscanceled(self):
        return self.window.cancelled

    def close(self):
        try:
            self.window.close()
        finally:
            self.directory.cleanup()
