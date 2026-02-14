# UX_TTS_POLICY.md

## Cel
Okresla, kiedy Renata mowi, a kiedy milczy.

## Zasada nadrzedna
Jesli informacja nie zmienia swiadomosci pilota, Renata milczy.

## Priorytety komunikatow
`ALERT > ACK > RESULT > STATUS > LORE`

## Combat Silence
- W walce TTS jest wyciszony.
- Wyjatek: alerty krytyczne (bezpieczenstwo statku/pilota).

## Dwie warstwy polityki mowy
### 1) Semantyka (czy mowic)
Silnik polityki ocenia, czy komunikat wnosi nowa wartosc i czy nie jest spamem.

### 2) Styl (jakim zdaniem mowic)
Gdy komunikat ma zostac wypowiedziany, Renata moze wybrac wariant zdania, aby unikac monotonii.
Styl nie moze wymusic emisji, jesli semantyka wskazuje cisze.

## Polityka cooldown
- `NORMAL`: standardowe komunikaty, pelna ochrona anti-spam.
- `BYPASS_GLOBAL`: omija globalny cooldown, ale nadal dziala deduplikacja.
- `ALWAYS_SAY`: tylko dla zdarzen progowych lub potwierdzen akcji gracza.

## Ustalone wyjatki od global cooldown
### Exobiology
- Pobranie probki (z nazwa obiektu) musi byc slyszalne za kazdym razem.
- Komunikat READY ("osiagnieto odleglosc") musi byc slyszalny raz na cykl probki.

### FSS
- Progi postepu (25/50/75), "ostatnia planeta do skanowania" i "system przeskanowany" musza byc slyszalne.
- Komunikat "tu warto wyladowac" dla planety z biologia: raz na planete.

### Paliwo
- Ostrzezenia progowe niskiego paliwa (szczegolnie krytyczne progi) nie sa blokowane globalnym cooldown.

## Zasada koncowa
Renata mowi tylko wtedy, gdy cisza bylaby gorsza.
