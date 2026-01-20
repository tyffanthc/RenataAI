# Current Task Snapshot

Date: 2026-01-20

## Latest UX decision
Trade "Market Age" UI was implemented with cutoff datetime + slider + presets
behind `features.trade.market_age_slider`. It is accepted for now, but the UX is
not final and should be aligned with Spansh later (calendar widget, better layout
and formatting).

## Follow-up UX task (planned)
Add a backlog item for: "Trade Market Age UX zgodny ze Spansh (kalendarz, format, layout)".

## How to verify the feature
- Settings -> Handel -> enable "Market Age: suwak + data/czas (beta)"
- Restart app
- Trade tab: preset changes cutoff datetime; manual datetime updates slider

## Do not forget
- No auto-run on value change (only changes parameters).
- Keep `user_settings.json` untracked.
