import os
import json
import glob
import config
from logic.utils import powiedz
from logic.utils.renata_log import log_event_throttled

def sprawdz_magazyn(nazwa_receptury, gui_ref):
    rec = config.RECEPTURY.get(nazwa_receptury)
    if not rec: return
    
    # KORZYSTAMY Z PAMIĘCI RAM (config.STATE['inventory'])
    pos = config.STATE.get("inventory", {})
    
    if not pos:
        powiedz("Magazyn pusty lub niezaładowany.", gui_ref)
        return

    brak = []
    for sk, req in rec.items():
        ma = pos.get(sk.lower(), 0)
        if ma < req: brak.append(f"{sk} ({ma}/{req})")
            
    if not brak: powiedz("Masz komplet!", gui_ref)
    else: powiedz(f"Braki: {', '.join(brak)}", gui_ref)

def znajdz_ostatni_system():
    try:
        log_dir = config.get("log_dir")
        pliki = glob.glob(os.path.join(log_dir, '*.log'))
        if not pliki: return "Nieznany"
        naj = max(pliki, key=os.path.getmtime)
        with open(naj, 'r', encoding='utf-8') as f:
            for line in reversed(f.readlines()):
                if "StarSystem" in line: return json.loads(line)["StarSystem"]
    except Exception as exc:
        log_event_throttled(
            "ENGINEER:last_system",
            15000,
            "ENGINEER",
            "failed to resolve last system from log",
            error=f"{type(exc).__name__}: {exc}",
        )
    return "Nieznany"
