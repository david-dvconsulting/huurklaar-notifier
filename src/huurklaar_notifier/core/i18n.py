"""Teksten in nl, fr en en met dezelfde sleutels; Nederlands is de bron (een test bewaakt de gelijkheid)."""

from __future__ import annotations

LANGUAGES = ("nl", "fr", "en")

NL = {
    "status.not_configured": "Niet aangemeld",
    "status.offline": "Geen verbinding",
    "status.auth_failed": "Sleutel ongeldig of ingetrokken",
    "status.disabled": "Meldingen staan tijdelijk uit",
    "status.idle": "Niets te doen",
    "status.tasks": "{n} open",
    "status.overdue": "{n} te laat",
    "status.updated": "Bijgewerkt om {time}",
    "menu.more": "… en nog {n} in Huurklaar",
    "menu.open_app": "Huurklaar openen",
    "menu.refresh": "Nu vernieuwen",
    "menu.settings": "Instellingen…",
    "menu.language": "Taal",
    "menu.language_auto": "Automatisch (systeem)",
    "menu.autostart": "Start bij aanmelden",
    "menu.update": "Nieuwe versie v{version}",
    "menu.about": "Versie {version}",
    "menu.quit": "Stoppen",
    "kind.task": "Taak",
    "kind.complaint": "Klacht",
    "kind.report": "Melding",
    "kind.tenantTask": "Taak voor jou",
    "kind.myReport": "Jouw melding",
    "kind.invoiceAttention": "Factuur",
    "kind.other": "Melding",
    "toast.overdue": "Te laat",
    "toast.action": "Actie nodig",
    "toast.summary": "{n} nieuwe meldingen",
    "toast.summary_body": "Open Huurklaar om ze te bekijken.",
    "dialog.title": "Huurklaar Meldingen",
    "dialog.url_prompt": "Adres van de Huurklaar-API (begint met https://):",
    "dialog.key_prompt": "Meldingssleutel (je maakt hem aan in Huurklaar, onder Mijn profiel > Meldingen):",
    "dialog.key_keep": "Laat leeg om de bewaarde sleutel te behouden.",
    "dialog.save": "Bewaren",
    "dialog.cancel": "Annuleren",
    "dialog.invalid_url": "Dat adres is niet geldig. Gebruik een adres dat met https:// begint.",
    "dialog.invalid_key": "Dat is geen geldige meldingssleutel. Hij begint met hkn_.",
}

FR = {
    "status.not_configured": "Non connecté",
    "status.offline": "Pas de connexion",
    "status.auth_failed": "Clé invalide ou révoquée",
    "status.disabled": "Les notifications sont temporairement désactivées",
    "status.idle": "Rien à faire",
    "status.tasks": "{n} ouvert(s)",
    "status.overdue": "{n} en retard",
    "status.updated": "Mis à jour à {time}",
    "menu.more": "… et {n} de plus dans Huurklaar",
    "menu.open_app": "Ouvrir Huurklaar",
    "menu.refresh": "Actualiser maintenant",
    "menu.settings": "Paramètres…",
    "menu.language": "Langue",
    "menu.language_auto": "Automatique (système)",
    "menu.autostart": "Lancer à l'ouverture de session",
    "menu.update": "Nouvelle version v{version}",
    "menu.about": "Version {version}",
    "menu.quit": "Quitter",
    "kind.task": "Tâche",
    "kind.complaint": "Plainte",
    "kind.report": "Signalement",
    "kind.tenantTask": "Tâche pour vous",
    "kind.myReport": "Votre signalement",
    "kind.invoiceAttention": "Facture",
    "kind.other": "Notification",
    "toast.overdue": "En retard",
    "toast.action": "Action requise",
    "toast.summary": "{n} nouvelles notifications",
    "toast.summary_body": "Ouvrez Huurklaar pour les consulter.",
    "dialog.title": "Huurklaar Notifications",
    "dialog.url_prompt": "Adresse de l'API Huurklaar (commence par https://) :",
    "dialog.key_prompt": "Clé de notification (à créer dans Huurklaar, sous Mon profil > Notifications) :",
    "dialog.key_keep": "Laissez vide pour conserver la clé enregistrée.",
    "dialog.save": "Enregistrer",
    "dialog.cancel": "Annuler",
    "dialog.invalid_url": "Cette adresse n'est pas valide. Utilisez une adresse commençant par https://.",
    "dialog.invalid_key": "Ce n'est pas une clé de notification valide. Elle commence par hkn_.",
}

EN = {
    "status.not_configured": "Not signed in",
    "status.offline": "No connection",
    "status.auth_failed": "Key invalid or revoked",
    "status.disabled": "Notifications are temporarily off",
    "status.idle": "Nothing to do",
    "status.tasks": "{n} open",
    "status.overdue": "{n} overdue",
    "status.updated": "Updated at {time}",
    "menu.more": "… and {n} more in Huurklaar",
    "menu.open_app": "Open Huurklaar",
    "menu.refresh": "Refresh now",
    "menu.settings": "Settings…",
    "menu.language": "Language",
    "menu.language_auto": "Automatic (system)",
    "menu.autostart": "Start at login",
    "menu.update": "New version v{version}",
    "menu.about": "Version {version}",
    "menu.quit": "Quit",
    "kind.task": "Task",
    "kind.complaint": "Complaint",
    "kind.report": "Report",
    "kind.tenantTask": "Task for you",
    "kind.myReport": "Your report",
    "kind.invoiceAttention": "Invoice",
    "kind.other": "Notification",
    "toast.overdue": "Overdue",
    "toast.action": "Action needed",
    "toast.summary": "{n} new notifications",
    "toast.summary_body": "Open Huurklaar to view them.",
    "dialog.title": "Huurklaar Notifications",
    "dialog.url_prompt": "Address of the Huurklaar API (starts with https://):",
    "dialog.key_prompt": "Notification key (create it in Huurklaar under My profile > Notifications):",
    "dialog.key_keep": "Leave empty to keep the stored key.",
    "dialog.save": "Save",
    "dialog.cancel": "Cancel",
    "dialog.invalid_url": "That address is not valid. Use an address starting with https://.",
    "dialog.invalid_key": "That is not a valid notification key. It starts with hkn_.",
}

CATALOG = {"nl": NL, "fr": FR, "en": EN}


def resolve_language(setting: str, system_languages: list[str]) -> str:
    """`setting` is nl/fr/en of 'auto'; bij 'auto' de eerste systeemtaal die we kennen, anders Nederlands."""
    if setting in LANGUAGES:
        return setting
    for tag in system_languages:
        code = tag.replace("_", "-").split("-")[0].lower()
        if code in LANGUAGES:
            return code
    return "nl"


def translate(lang: str, key: str, **params: object) -> str:
    # Een ontbrekende sleutel geeft de sleutel zelf terug i.p.v. een KeyError (een menu mag niet crashen)
    text = CATALOG.get(lang, NL).get(key) or NL.get(key, key)
    return text.format(**params) if params else text
