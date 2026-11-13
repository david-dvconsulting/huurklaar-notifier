"""Een klein nep-`winreg` in het geheugen, met dezelfde namen als het echte module."""

HKEY_CURRENT_USER = "HKCU"
HKEY_LOCAL_MACHINE = "HKLM"
KEY_READ, KEY_SET_VALUE = 1, 2
REG_SZ = 1


class _Key:
    def __init__(self, values: dict) -> None:
        self.values = values

    def __enter__(self):
        return self

    def __exit__(self, *exc) -> None:
        return None


class FakeWinreg:
    HKEY_CURRENT_USER = HKEY_CURRENT_USER
    HKEY_LOCAL_MACHINE = HKEY_LOCAL_MACHINE
    KEY_READ = KEY_READ
    KEY_SET_VALUE = KEY_SET_VALUE
    REG_SZ = REG_SZ

    def __init__(self) -> None:
        self.keys: dict[tuple[str, str], dict[str, str]] = {}

    def OpenKey(self, root, path, reserved=0, access=0):  # noqa: N802
        if (root, path) not in self.keys:
            raise FileNotFoundError(path)
        return _Key(self.keys[(root, path)])

    def CreateKeyEx(self, root, path, reserved=0, access=0):  # noqa: N802
        return _Key(self.keys.setdefault((root, path), {}))

    def SetValueEx(self, key, name, reserved, kind, value):  # noqa: N802
        key.values[name] = value

    def QueryValueEx(self, key, name):  # noqa: N802
        if name not in key.values:
            raise FileNotFoundError(name)
        return key.values[name], REG_SZ

    def DeleteValue(self, key, name):  # noqa: N802
        if name not in key.values:
            raise FileNotFoundError(name)
        del key.values[name]
