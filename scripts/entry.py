"""Startpunt voor PyInstaller (die heeft een los script nodig, geen `-m`)."""

import sys

from huurklaar_notifier.__main__ import main

sys.exit(main())
