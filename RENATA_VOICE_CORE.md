# RENATA_VOICE_CORE.md
**Cel:** zwiększyć „serce Renaty” (udział trafnych, przyjemnych komunikatów) bez spamu, bez nowych providerów i bez nowych zakładek.  
**Zakres:** wykorzystujemy WYŁĄCZNIE istniejące eventy/logikę (exploration_*_events, system_value_engine, route_clipboard, exit_summary, notify).  
**Definicja sukcesu:** po 10–15 minutach lotu użytkownik nie wyłącza TTS i ma poczucie, że Renata „jest z nim”, a nie „gada”.

---

## 0) Zasady głosu (tożsamość)
1. **Jedna myśl = jedno zdanie.** Maks 2 zdania w komunikacie.
2. **Renata nie instruuje „kliknij to”.** Renata podaje wniosek/ryzyko/potwierdzenie.
3. **Cisza jest domyślna.** Mówimy tylko w momentach decyzyjnych lub przy ryzyku.
4. **Bez obietnic 100%.** Używać: „szacuję”, „wygląda na”, „może”.
5. **Nazwy planet mówimy tylko przy topowych obiektach.** (Memory Anchor)

---

## 1) TOP 3 zachowania (wdrażać w tej kolejności)
### 1. Decision Confirmation (najważniejsze)
**Idea:** po fakcie potwierdzić dobrą decyzję gracza (emocja + zaufanie).  
**Warunek:** tylko gdy wynik faktycznie „dobry” wg istniejącej wyceny (exobio/cartography).  
**Limit:** max 2 razy na sesję (lub 1 raz na 30 minut).

### 2. System Triage (po skoku)
**Idea:** jedno zdanie po wejściu do systemu: „warto zostać czy lecieć dalej”.  
**Warunek:** tylko jeśli wniosek jest wyraźny (High/Mid/Low) i nie będzie spamować.  
**Limit:** max 1 komunikat na system.

### 3. Memory Anchors (nazywanie planety + powrót)
**Idea:** gdy obiekt jest topowy, Renata mówi „Planeta 2 A…”, żeby gracz zapamiętał.  
**Warunek:** tylko dla MUST-LAND/top-tier.  
**Limit:** max 2 planety na sesję.

---

## 2) Landing Advisor (FSS → decyzja lądowania) — progi exobio
**Wejście danych (istniejące):**
- `FSSBodySignals` (bio count / types)
- `Scan` (planet class)
- `system_value_engine` (exobio value + FD/FF bonuses)

### 2.1 Klasy planet (heurystyka)
- **GOOD:** ELW, WW, HMC, Ammonia
- **MID:** Icy body, Rocky (z atmosferą)
- **LOW:** Rocky bez atmosfery i inne niskie

### 2.2 Bazowa ocena wg liczby bio-signals
- `bio = 0` → **IGNORE** (cisza)
- `bio = 1` → **SKIP**
- `bio = 2` → **MAYBE**
- `bio >= 3` → **MUST-LAND**

### 2.3 Modyfikatory (upgrade/downgrade o 1 poziom)
**Upgrade o 1:**
- planeta w klasie **GOOD**
- system ma **FD możliwe**
- **FF możliwe** (nie lądowano)
- biosy ocenione jako wysokiej wartości wg istniejącej logiki

**Downgrade o 1:**
- planeta w klasie **LOW**
- brak FD i brak FF
- „fatigue”: wiele lądowań/komunikatów w krótkim czasie (ochrona przed spamem)

### 2.4 Finalna decyzja
- IGNORE: 0 bio → milcz
- SKIP: niski potencjał → krótko odradź
- MAYBE: średni potencjał → „zależy od czasu”
- MUST-LAND: wysoki potencjał → zasugeruj DSS + lądowanie

**Anti-spam:** 1 raz na planetę (body_id/body_name).

---

## 3) System Triage — progi i warunki
**Cel:** po `FSDJump`/`Location` (pierwszy event w systemie) ocenić, czy warto „zatrzymać się” na FSS.

### 3.1 Skala
- **LOW:** „raczej leć dalej”
- **MID:** „może warto, jeśli masz czas”
- **HIGH:** „system obiecujący, warto przeskanować”

### 3.2 Proponowane warunki (bez nowych danych)
HIGH jeśli spełnione >=1:
- system „dziewiczy” (FD/FF możliwe) i/lub
- wystąpiły high-value alerts (ELW/WW/HMC) i/lub
- wykryto bio signals w systemie (po FSS) — jeśli triage wypada później, nie na wejściu

LOW jeśli:
- brak sygnałów/wartości wg heurystyk
- brak FD/FF
- użytkownik ma aktywną trasę „przelotową” (np. Neutron) i triage byłby przeszkodą

**Limit:** 1 raz na system. Jeśli niepewne → cisza.

---

## 4) Decision Confirmation — kiedy i jak
**Wejście danych:** istniejące wyceny `system_value_engine` + zdarzenia zakończenia/mapowania/exobio (wg tego co już jest w logice).  
**Reguła:** potwierdzamy tylko, jeśli:
- wynik exobio/cartography przekracza „sensowny próg” (relative threshold),
- albo planeta była klasyfikowana jako MUST-LAND i faktycznie została zmapowana/odwiedzona.

**Limit twardy:** max 2 potwierdzenia / sesja lub cooldown 30 minut.

---

## 5) Memory Anchors — nazwy planet (np. „2 A”)
### 5.1 Kiedy mówić nazwę
- tylko przy **MUST-LAND** (lub top-tier MAYBE)
- tylko jeśli to 1–2 najlepsze obiekty sesji

### 5.2 Jak czytać nazwę (TTS friendly)
- cyfry normalnie
- litery osobno
- pauza przed literą
Przykłady:
- `2 A` → „dwa A”
- `3 B C` → „trzy B C”

### 5.3 Powrót do nazw (na koniec sesji / exit summary)
- „Najlepszy obiekt dzisiaj: {body_short}.”
- „Jeśli wrócisz tu później, pamiętaj o {body_short}.”

---

## 6) Cooldowny i priorytety (żeby nie spamować)
### 6.1 Priorytety (od najwyższego)
1. bezpieczeństwo (fuel / dead end / high-g)
2. route state change (route ready / resync / dead end)
3. Landing Advisor MUST-LAND
4. System Triage HIGH
5. Decision Confirmation / Memory Anchor (rzadko)

### 6.2 Minimalne cooldowny (propozycja)
- global TTS: 8–12 s
- exobio category: 20–30 s
- triage: 1/system
- confirmation: 30 min
- memory anchors: 2/sesja

### 6.3 Dedup
- jeśli tekst/intent identyczny → nie mów drugi raz w tym samym systemie/body

---

## 7) Teksty PL — gotowe szablony (krótkie)
**Wszystkie teksty mają być preprocessowane (pauzy, liczby, nazwy).**

### 7.1 Landing Advisor — SKIP
- „Są sygnały biologiczne, ale potencjał jest niski. Raczej pomiń.”
- „To wygląda na mało opłacalne lądowanie.”

### 7.2 Landing Advisor — MAYBE
- „Sygnały biologiczne są obecne. Decyzja zależy od czasu.”
- „Może być warte uwagi, jeśli chcesz się zatrzymać.”

### 7.3 Landing Advisor — MUST-LAND (z nazwą planety)
- „Planeta {body_short} ma bardzo dobry potencjał pod exobiologię.”
- „Warto zmapować i lądować na {body_short}.”
- „To rzadszy przypadek. {body_short} wygląda naprawdę dobrze.”

### 7.4 System Triage — LOW / MID / HIGH
- LOW: „Tu raczej nic szczególnego. Możesz lecieć dalej.”
- MID: „System wygląda średnio. Jeśli masz czas, możesz go przeskanować.”
- HIGH: „Ten system wygląda obiecująco. Warto zrobić FSS.”

### 7.5 Decision Confirmation
- „Dobra decyzja z tym lądowaniem.”
- „To był opłacalny wybór.”
- „Warto było się tu zatrzymać.”

### 7.6 Memory Anchor (end of session)
- „Najlepszy obiekt tej sesji: {body_short}.”
- „Jeśli wrócisz do tego systemu, pamiętaj o {body_short}.”

---

## 8) Integracja (gdzie to spiąć)
**Bez narzucania struktury kodu — tylko wskazanie istniejących miejsc.**
- Landing Advisor: `exploration_bio_events.py` (+ użycie `system_value_engine.py`)
- System Triage: `exploration_misc_events.py` lub moduł „post-jump summary”
- Confirmation + Memory Anchors: `exit_summary.py` + zdarzenia DSS/exobio/scan

---

## 9) Zakres OUT (żeby nie odpłynąć)
- brak nowych providerów / uploadów (symbioza OUT)
- brak STT wymaganego do wdrożenia
- brak nowych UI zakładek
- brak OCR UI gry
- brak „głosowania” / społeczności

---

## 10) DoD (Definition of Done)
1. Landing Advisor działa: IGNORE/SKIP/MAYBE/MUST-LAND, 1 raz na planetę.
2. System Triage: 1 raz na system, tylko gdy wniosek wyraźny.
3. Memory Anchors: nazwa planety tylko w MUST-LAND/top i max 2/sesję.
4. Decision Confirmation: max 2/sesję lub cooldown 30 min.
5. Test odsłuchowy: 10 minut eksploracji bez irytacji, bez powtórek.
