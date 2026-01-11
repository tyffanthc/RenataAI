import json
import os


class RenataConfig:
    def __init__(self, path="config.json"):
        self.path = path

        # wartości domyślne
        self.exit_summary_enabled = True
        self.voice_exit_summary = True

        self.load()

    def load(self):
        if not os.path.exists(self.path):
            # brak pliku? — zapisujemy domyślny
            self.save()
            return

        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)

            self.exit_summary_enabled = data.get("exit_summary_enabled", True)
            self.voice_exit_summary = data.get("voice_exit_summary", True)

        except Exception as e:
            print("Błąd podczas czytania config.json:", e)

    def save(self):
        data = {
            "exit_summary_enabled": self.exit_summary_enabled,
            "voice_exit_summary": self.voice_exit_summary
        }
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            print("Nie udało się zapisać config.json:", e)
