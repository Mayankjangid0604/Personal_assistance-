"""
Planned Built-in Plugins (Phase 10).

The plugin *catalogue* in the AISHA v2.0 brief includes capabilities that need
external services, hardware, or heavier dependencies (Terminal, Browser, PDF,
OCR, Weather, Calendar, Email, Camera, Microphone, Image Generation).

Rather than fake them, each is registered as a real, discoverable plugin that
publishes a correct manifest (permissions, capabilities, version, docs) but
honestly reports ``unavailable`` health and returns a clear "not yet
implemented" result.  This makes the ecosystem *complete in shape* -- the
Plugin Manager UI, capability index, and permission model all see every
catalogue member -- while being truthful about what actually runs today.

Each is a two-line replacement away from a working implementation.
"""

from __future__ import annotations

from typing import Any

from ..base import Capability, HealthState, Permission, PluginHealth, PluginManifest
from ..sdk import SimplePlugin, action


class PlannedPlugin(SimplePlugin):
    """Base for catalogue plugins that are declared but not yet implemented."""

    _NAME = "planned"
    _VERSION = "0.1.0"
    _CAPS: list[Capability] = []
    _PERMS: list[Permission] = []
    _DESC = "Planned capability (not yet implemented)."
    _DOC = ""

    def manifest(self) -> PluginManifest:
        return PluginManifest(
            name=self._NAME,
            version=self._VERSION,
            capabilities=list(self._CAPS),
            permissions=list(self._PERMS),
            description=self._DESC,
            documentation=self._DOC or f"{self._NAME}: planned; reports unavailable until implemented.",
            tags=["planned"],
        )

    @action
    def info(self) -> dict[str, Any]:
        return {"plugin": self._NAME, "implemented": False,
                "message": f"{self._NAME} is declared but not yet implemented"}

    def health(self) -> PluginHealth:
        return self.health_of(HealthState.UNAVAILABLE, "planned; not yet implemented")


class TerminalPlugin(PlannedPlugin):
    _NAME = "terminal"; _CAPS = [Capability.TERMINAL]
    _PERMS = [Permission.PROCESS_SPAWN]
    _DESC = "Governed shell command execution (Milestone 2)."


class BrowserPlugin(PlannedPlugin):
    _NAME = "browser"; _CAPS = [Capability.BROWSER]
    _PERMS = [Permission.NETWORK]
    _DESC = "Headless browser automation and page fetch."


class PdfPlugin(PlannedPlugin):
    _NAME = "pdf"; _CAPS = [Capability.PDF]
    _PERMS = [Permission.FS_READ]
    _DESC = "PDF text/table extraction and generation."


class OcrPlugin(PlannedPlugin):
    _NAME = "ocr"; _CAPS = [Capability.OCR]
    _PERMS = [Permission.FS_READ]
    _DESC = "Optical character recognition over images/PDFs."


class WeatherPlugin(PlannedPlugin):
    _NAME = "weather"; _CAPS = [Capability.WEATHER]
    _PERMS = [Permission.NETWORK]
    _DESC = "Current conditions and forecast lookup."


class CalendarPlugin(PlannedPlugin):
    _NAME = "calendar"; _CAPS = [Capability.CALENDAR]
    _PERMS = [Permission.NETWORK]
    _DESC = "Calendar events read/write."


class EmailPlugin(PlannedPlugin):
    _NAME = "email"; _CAPS = [Capability.EMAIL]
    _PERMS = [Permission.NETWORK]
    _DESC = "Email read/compose/send."


class CameraPlugin(PlannedPlugin):
    _NAME = "camera"; _CAPS = [Capability.CAMERA]
    _PERMS = [Permission.CAMERA]
    _DESC = "Still capture from a connected camera."


class MicrophonePlugin(PlannedPlugin):
    _NAME = "microphone"; _CAPS = [Capability.MICROPHONE]
    _PERMS = [Permission.MICROPHONE]
    _DESC = "Audio capture from the microphone."


class ImageGenerationPlugin(PlannedPlugin):
    _NAME = "image_generation"; _CAPS = [Capability.IMAGE_GENERATION]
    _PERMS = [Permission.NETWORK]
    _DESC = "Local/remote text-to-image generation."


PLANNED_PLUGINS = [
    TerminalPlugin, BrowserPlugin, PdfPlugin, OcrPlugin, WeatherPlugin,
    CalendarPlugin, EmailPlugin, CameraPlugin, MicrophonePlugin,
    ImageGenerationPlugin,
]
