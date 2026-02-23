from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class F28RuntimePlTextAuditAsciiAndMojibakeTests(unittest.TestCase):
    def test_critical_runtime_messages_no_ascii_pl_regressions(self) -> None:
        checks: list[tuple[str, list[str]]] = [
            (
                "logic/events/cash_in_assistant.py",
                [
                    "Rozwaz cash-in teraz",
                    "Uzywam offline indexu stacji, sprawdz panel.",
                    "brak pelnych danych stacyjnych",
                    "Rozwaz teraz, po domknieciu systemu albo pozniej.",
                ],
            ),
            (
                "logic/events/combat_awareness.py",
                [
                    "Rozwaz przerwanie eskalacji",
                    "Jesli chcesz, sprawdz panel",
                ],
            ),
            (
                "logic/events/survival_rebuy_awareness.py",
                [
                    "Rozwaz wycofanie",
                    "Kontynuuj swiadomie",
                    "kadlub",
                    "wzgledem danych lub ladunku",
                ],
            ),
            (
                "logic/events/high_g_warning.py",
                [
                    "przeciazenie grawitacyjne",
                ],
            ),
            (
                "logic/utils/notify.py",
                [
                    "Tryb glosowy STT niedostepny",
                    "Uzyj UI/hotkey",
                    "Akcja glosowa STT chwilowo niedostepna",
                ],
            ),
            (
                "gui/strings.py",
                [
                    'LABEL_USE_MAP = "Uzyj mapy"',
                ],
            ),
            (
                "gui/tabs/settings.py",
                [
                    "Brak konwersji. Uzyj 'Zbuduj offline index' po pobraniu dumpa.",
                ],
            ),
            (
                "gui/tabs/logbook.py",
                [
                    "Niepoprawny format daty. Uzyj YYYY-MM-DD.",
                ],
            ),
            (
                "gui/tabs/journal_map.py",
                [
                    "planner neutronowy jest niedostepny",
                    "Sprobuj za chwile",
                ],
            ),
            (
                "gui/tabs/pulpit.py",
                [
                    "route handoff niedostepna",
                    "Copy next hop niedostepna",
                    "zmiana trybu niedostepna",
                ],
            ),
        ]

        for rel_path, forbidden_substrings in checks:
            content = (ROOT / rel_path).read_text(encoding="utf-8")
            for token in forbidden_substrings:
                self.assertNotIn(token, content, f"{rel_path} still contains: {token!r}")


if __name__ == "__main__":
    unittest.main()
