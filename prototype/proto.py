"""Prototype KAN-119: komen meldingen van een ad-hoc ondertekend .app betrouwbaar aan?

Een menubalk-app met drie knoppen, één per meldingsmethode, en een logbestand
zodat we achteraf zien wat het systeem teruggaf (rechten, fouten, kliks).
Bevat bewust geen echte gegevens; de URL is een voorbeeldadres.
"""

import subprocess
import threading
import time
from pathlib import Path

import rumps
from AppKit import NSWorkspace
from Foundation import NSURL, NSObject
from UserNotifications import (
    UNAuthorizationOptionAlert,
    UNAuthorizationOptionSound,
    UNMutableNotificationContent,
    UNNotificationRequest,
    UNNotificationSound,
    UNUserNotificationCenter,
)

URL = "https://example.com/?via=melding"
LOG = Path.home() / "Library/Logs/huurklaar-meldingen-proto.log"


def log(msg: str) -> None:
    with LOG.open("a") as f:
        f.write(f"{time.strftime('%H:%M:%S')} {msg}\n")


def open_url(url: str) -> None:
    NSWorkspace.sharedWorkspace().openURL_(NSURL.URLWithString_(url))


class Delegate(NSObject):
    # Klik op een melding: de URL zit in userInfo.
    def userNotificationCenter_didReceiveNotificationResponse_withCompletionHandler_(
        self, center, response, handler
    ):
        info = response.notification().request().content().userInfo()
        log(f"klik op melding, url={info.get('url')}")
        open_url(str(info.get("url", URL)))
        handler()

    # Ook tonen als de app vooraan staat.
    def userNotificationCenter_willPresentNotification_withCompletionHandler_(
        self, center, notification, handler
    ):
        handler(0b1110)  # banner | list | sound


class Proto(rumps.App):
    def __init__(self) -> None:
        super().__init__("Meldingen", title="🔔", quit_button="Stoppen")
        self.menu = [
            rumps.MenuItem("1. UNUserNotificationCenter", callback=self.via_un),
            rumps.MenuItem("2. osascript", callback=self.via_osascript),
            rumps.MenuItem("3. rumps.notification", callback=self.via_rumps),
        ]
        self.center = UNUserNotificationCenter.currentNotificationCenter()
        self.delegate = Delegate.alloc().init()
        self.center.setDelegate_(self.delegate)
        self.center.requestAuthorizationWithOptions_completionHandler_(
            UNAuthorizationOptionAlert | UNAuthorizationOptionSound,
            lambda granted, err: log(f"toestemming: granted={granted} err={err}"),
        )
        self.center.getNotificationSettingsWithCompletionHandler_(
            lambda s: log(f"instellingen: authorizationStatus={s.authorizationStatus()}")
        )

    def via_un(self, _):
        c = UNMutableNotificationContent.alloc().init()
        c.setTitle_("Huurklaar (UN)")
        c.setBody_("Klik om de voorbeeldpagina te openen.")
        c.setSound_(UNNotificationSound.defaultSound())
        c.setUserInfo_({"url": URL})
        req = UNNotificationRequest.requestWithIdentifier_content_trigger_(f"proto-{time.time()}", c, None)
        self.center.addNotificationRequest_withCompletionHandler_(
            req, lambda err: log(f"UN verstuurd: err={err}")
        )

    def via_osascript(self, _):
        r = subprocess.run(
            ["osascript", "-e", 'display notification "Via osascript" with title "Huurklaar (osascript)"'],
            capture_output=True,
            text=True,
        )
        log(f"osascript rc={r.returncode} {r.stderr.strip()}")

    def via_rumps(self, _):
        rumps.notification("Huurklaar (rumps)", "", "Via rumps.notification", data={"url": URL})
        log("rumps verstuurd")


if __name__ == "__main__":
    log("start")
    app = Proto()
    # Prototype: automatisch alle drie versturen zodat het ook zonder klikken te testen is.
    for delay, fn in ((4, app.via_un), (9, app.via_osascript), (14, app.via_rumps)):
        threading.Timer(delay, fn, args=(None,)).start()
    app.run()
