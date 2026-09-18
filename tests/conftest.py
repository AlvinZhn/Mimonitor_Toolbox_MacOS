import os
import sys
from unittest.mock import MagicMock

# Ensure offscreen platform during pytest execution if needed
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

if sys.platform == "darwin":
    try:
        import qframelesswindow.mac as mac_frameless
        # In headless / offscreen mode on macOS, Qt does not create native NSViews.
        # Calling objc.objc_object on an offscreen winId() causes a Cocoa segfault.
        if os.environ.get("QT_QPA_PLATFORM") == "offscreen":
            def dummy_update(self):
                self._MacFramelessWindow__nsWindow = MagicMock()
            mac_frameless.MacFramelessWindow.updateFrameless = dummy_update
    except ImportError:
        pass
