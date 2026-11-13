"""Dialogen op Windows: een instellingenvenster met tkinter (zit in Python, dus ook in de .exe) en een
berichtvenster via `MessageBoxW`. Dun gehouden: de logica staat in de kern."""

from __future__ import annotations

import threading

from ..core.i18n import translate


def alert(lang: str, message: str) -> None:
    import ctypes

    ctypes.windll.user32.MessageBoxW(0, message, translate(lang, "dialog.title"), 0x40)  # MB_ICONINFORMATION


def ask_settings(lang: str, base_url: str, key_saved: bool) -> tuple[str, str] | None:
    """Eén venster met adres en sleutel (verborgen). `None` = geannuleerd. Draait in een eigen thread, want
    de tray-lus bezet de hoofdthread en tkinter hoort bij de thread die het venster maakt."""
    result: list[tuple[str, str] | None] = [None]

    def run() -> None:
        import tkinter as tk
        from tkinter import ttk

        t = lambda key: translate(lang, key)  # noqa: E731
        root = tk.Tk()
        root.title(t("dialog.title"))
        root.resizable(False, False)
        frame = ttk.Frame(root, padding=14)
        frame.grid()
        ttk.Label(frame, text=t("dialog.url_prompt"), wraplength=420, justify="left").grid(sticky="w")
        url = tk.StringVar(value=base_url)
        ttk.Entry(frame, textvariable=url, width=56).grid(sticky="we", pady=(2, 10))
        prompt = t("dialog.key_prompt") + (("\n" + t("dialog.key_keep")) if key_saved else "")
        ttk.Label(frame, text=prompt, wraplength=420, justify="left").grid(sticky="w")
        key = tk.StringVar()
        entry = ttk.Entry(frame, textvariable=key, width=56, show="•")
        entry.grid(sticky="we", pady=(2, 12))
        buttons = ttk.Frame(frame)
        buttons.grid(sticky="e")

        def save() -> None:
            result[0] = (url.get(), key.get())
            root.destroy()

        ttk.Button(buttons, text=t("dialog.cancel"), command=root.destroy).grid(row=0, column=0, padx=6)
        ttk.Button(buttons, text=t("dialog.save"), command=save).grid(row=0, column=1)
        root.bind("<Return>", lambda _e: save())
        root.bind("<Escape>", lambda _e: root.destroy())
        root.attributes("-topmost", True)
        entry.focus_set()
        root.mainloop()

    worker = threading.Thread(target=run, name="settings-dialog")
    worker.start()
    worker.join()
    return result[0]
