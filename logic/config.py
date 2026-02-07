import config as app_config


class RenataConfig:
    """
    Backward-compatible adapter.
    Keeps old attribute API while delegating to the central ConfigManager
    (no separate config.json side-channel).
    """

    def __init__(self, path="config.json"):
        # Keep signature for compatibility with old callers.
        self.path = path
        self.load()

    @property
    def exit_summary_enabled(self):
        return bool(app_config.get("exit_summary_enabled", True))

    @exit_summary_enabled.setter
    def exit_summary_enabled(self, value):
        app_config.save({"exit_summary_enabled": bool(value)})

    @property
    def voice_exit_summary(self):
        return bool(app_config.get("voice_exit_summary", True))

    @voice_exit_summary.setter
    def voice_exit_summary(self, value):
        app_config.save({"voice_exit_summary": bool(value)})

    def load(self):
        # Settings are loaded by central ConfigManager.
        return None

    def save(self):
        # Nothing to do: values are written by property setters.
        return None
