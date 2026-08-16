"""The X11 twin of the Windows app id: here the .desktop file is what names the app."""

from __future__ import annotations


def set_app_id(app_id: str) -> bool:
    """Nothing to do: `QApplication.setDesktopFileName` already ties us to com.defalt.dito."""
    return False
