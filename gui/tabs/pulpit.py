from __future__ import annotations

import tkinter as tk
import time
from tkinter import ttk
from typing import Any, Callable

import config
from logic.risk_rebuy_contract import build_risk_rebuy_contract


class PulpitTab(ttk.Frame):
    """
    Main dashboard tab:
    - header + mini status bar
    - compact widget strip
    - compact toolbar
    - console area with single-slot interaction panel + runtime log
    """

    _WIDGET_ORDER = [
        "mode",
        "risk",
        "cash",
        "route",
        "summary",
        "fss",
        "exo",
        "min",
        "trd",
        "xeno",
    ]
    _WIDGET_ALWAYS = {"mode", "risk", "cash", "route"}
    _WIDGET_MAX_VISIBLE = 7
    _PANEL_MAX_RATIO = 0.30
    _PANEL_MIN_HEIGHT = 96
    _PANEL_COLLAPSED_HEIGHT = 44
    _PANEL_MAX_ACTIONS = 6

    _PANEL_TITLES = {
        "mode": "MODE",
        "risk": "SURVIVAL / REBUY",
        "cash": "CASH-IN ASSISTANT",
        "route": "ROUTE",
        "summary": "EXPLORATION SUMMARY",
        "fss": "FSS",
        "exo": "EXOBIO",
        "min": "MINING",
        "trd": "TRADE",
        "xeno": "XENO",
        "tools": "TOOLS",
    }

    def __init__(
        self,
        parent,
        *,
        on_generate_science_excel=None,
        on_generate_modules_data=None,
        on_generate_exploration_summary=None,
        on_generate_cash_in_assistant=None,
        on_skip_cash_in_assistant=None,
        on_cash_in_action=None,
        app_state=None,
        route_manager=None,
    ):
        super().__init__(parent)
        self.pack(fill="both", expand=True)

        self._on_generate_science_excel = on_generate_science_excel
        self._on_generate_modules_data = on_generate_modules_data
        self._on_generate_exploration_summary = on_generate_exploration_summary
        self._on_generate_cash_in_assistant = on_generate_cash_in_assistant
        self._on_skip_cash_in_assistant = on_skip_cash_in_assistant
        self._on_cash_in_action = on_cash_in_action
        self._app_state = app_state
        self._route_manager = route_manager

        self._current_exploration_summary_payload: dict = {}
        self._current_cash_in_payload: dict = {}
        self._current_cash_in_signature: str = ""
        self._cash_selected_option_id: str = ""
        self._current_survival_payload: dict = {}
        self._current_combat_payload: dict = {}
        self._current_risk_payload: dict = {}
        self._current_risk_source: str = ""
        self._mode_label = "NORMAL"
        self._mode_source = "AUTO"
        self._mode_confidence: float = 0.60
        self._mode_since: float = 0.0
        self._mode_ttl: float | None = None
        self._mode_overlay: str | None = None
        self._mode_combat_silence: bool = False

        self._widget_vars: dict[str, tk.StringVar] = {}
        self._widget_buttons: dict[str, ttk.Button] = {}
        self._widget_visible: dict[str, bool] = {}
        self._widget_active: dict[str, bool] = {}

        self._panel_visible = False
        self._panel_domain = ""
        self._panel_mode = ""
        self._panel_collapsed = False
        self._panel_auto_close_job = None
        self._panel_action_buttons: list[ttk.Button] = []

        self._init_ui()
        self._init_widget_defaults()
        self._update_status_from_state()

    # ------------------------------------------------------------
    # UI
    # ------------------------------------------------------------
    def _init_ui(self) -> None:
        header_frame = ttk.Frame(self)
        header_frame.pack(fill="x", padx=5, pady=(8, 4))

        self.lbl_header_title = ttk.Label(
            header_frame,
            text="R.E.N.A.T.A. SYSTEM ONLINE",
            font=("Eurostile", 14, "bold"),
        )
        self.lbl_header_title.pack(anchor="w", pady=(0, 2))

        self.lbl_header_system = ttk.Label(
            header_frame,
            text="Obecny system: [Czekam na dane...]",
            font=("Eurostile", 10),
        )
        self.lbl_header_system.pack(anchor="w")

        self.lbl_header_status = ttk.Label(
            header_frame,
            text="Status: [NORMAL]",
            font=("Eurostile", 10),
        )
        self.lbl_header_status.pack(anchor="w", pady=(0, 4))

        status_frame = ttk.Frame(self)
        status_frame.pack(fill="x", padx=5, pady=(0, 4))

        self.lbl_status_system = ttk.Label(status_frame, text="System: -")
        self.lbl_status_system.pack(side="left", padx=(0, 12))

        self.lbl_status_bodies = ttk.Label(status_frame, text="Ciala: -/-")
        self.lbl_status_bodies.pack(side="left", padx=(0, 12))

        self.lbl_status_route = ttk.Label(status_frame, text="Trasa: -")
        self.lbl_status_route.pack(side="left", padx=(0, 12))

        self.lbl_status_ship = ttk.Label(status_frame, text="Statek: -")
        self.lbl_status_ship.pack(side="left", padx=(0, 12))

        self.lbl_status_mass = ttk.Label(status_frame, text="Masa: - t")
        self.lbl_status_mass.pack(side="left", padx=(0, 12))

        self.lbl_status_cargo = ttk.Label(status_frame, text="Cargo: - t")
        self.lbl_status_cargo.pack(side="left", padx=(0, 12))

        self.lbl_status_fuel = ttk.Label(status_frame, text="Paliwo: -/- t")
        self.lbl_status_fuel.pack(side="left", padx=(0, 12))

        self.lbl_status_jr = ttk.Label(status_frame, text="JR: -")
        self.lbl_status_jr.pack(side="left", padx=(0, 12))

        widgets_outer = ttk.Frame(self)
        widgets_outer.pack(fill="x", padx=5, pady=(0, 4))
        self.widget_strip = ttk.Frame(widgets_outer)
        self.widget_strip.pack(fill="x")

        for domain in self._WIDGET_ORDER:
            var = tk.StringVar(value="")
            btn = ttk.Button(
                self.widget_strip,
                textvariable=var,
                command=lambda d=domain: self._on_widget_click(d),
            )
            self._widget_vars[domain] = var
            self._widget_buttons[domain] = btn
            self._widget_visible[domain] = domain in self._WIDGET_ALWAYS
            self._widget_active[domain] = domain in self._WIDGET_ALWAYS

        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill="x", padx=5, pady=(0, 5))

        ttk.Label(
            btn_frame,
            text="Narzedzia naukowe:",
            font=("Arial", 9, "bold"),
        ).pack(side="left")

        btn_generate_science = ttk.Button(
            btn_frame,
            text="Generuj arkusze naukowe",
            command=self._on_click_generate_science,
        )
        btn_generate_science.pack(side="right")

        btn_generate_modules = ttk.Button(
            btn_frame,
            text="Generuj dane modulow",
            command=self._on_click_generate_modules,
        )
        btn_generate_modules.pack(side="right", padx=(0, 8))
        if not config.get("modules_data_autogen_enabled", True):
            btn_generate_modules.state(["disabled"])

        btn_exploration_summary = ttk.Button(
            btn_frame,
            text="Podsumowanie eksploracji",
            command=self._on_click_exploration_summary,
        )
        btn_exploration_summary.pack(side="right", padx=(0, 8))

        btn_cash_in_assistant = ttk.Button(
            btn_frame,
            text="Asystent cash-in",
            command=self._on_click_cash_in_assistant,
        )
        btn_cash_in_assistant.pack(side="right", padx=(0, 8))

        btn_cash_in_skip = ttk.Button(
            btn_frame,
            text="Pomijam cash-in",
            command=self._on_click_cash_in_skip,
        )
        btn_cash_in_skip.pack(side="right", padx=(0, 8))

        self.console_area = ttk.Frame(self)
        self.console_area.pack(fill="both", expand=True, padx=5, pady=(0, 5))
        self.console_area.bind("<Configure>", self._on_console_area_resize)

        self.panel_wrap = ttk.Frame(self.console_area, relief="solid", borderwidth=1)
        self.panel_wrap.pack_propagate(False)

        panel_header = ttk.Frame(self.panel_wrap)
        panel_header.pack(fill="x", padx=8, pady=(6, 4))

        self.lbl_panel_title = ttk.Label(
            panel_header,
            text="",
            font=("Eurostile", 10, "bold"),
        )
        self.lbl_panel_title.pack(side="left")

        self.lbl_panel_mode = ttk.Label(panel_header, text="")
        self.lbl_panel_mode.pack(side="left", padx=(8, 0))

        self.btn_panel_toggle = ttk.Button(panel_header, text="Zwin", command=self._toggle_panel)
        self.btn_panel_toggle.pack(side="right")

        self.btn_panel_close = ttk.Button(panel_header, text="Zamknij", command=self._close_panel)
        self.btn_panel_close.pack(side="right", padx=(0, 6))

        self.panel_body_wrap = ttk.Frame(self.panel_wrap)
        self.panel_body_wrap.pack(fill="both", expand=True, padx=8, pady=(0, 4))

        panel_scroll = ttk.Scrollbar(self.panel_body_wrap, orient="vertical", style="Vertical.TScrollbar")
        panel_scroll.pack(side="right", fill="y")

        self.panel_text = tk.Text(
            self.panel_body_wrap,
            height=4,
            state="disabled",
            wrap="word",
            yscrollcommand=panel_scroll.set,
            bg="#1f2833",
            fg="#ffffff",
            insertbackground="#ff7100",
            selectbackground="#ff7100",
            selectforeground="#0b0c10",
            highlightthickness=0,
            bd=0,
            relief="flat",
        )
        self.panel_text.pack(side="left", fill="both", expand=True)
        panel_scroll.configure(command=self.panel_text.yview)

        self.panel_actions = ttk.Frame(self.panel_wrap)
        self.panel_actions.pack(fill="x", padx=8, pady=(0, 8))

        self.log_frame = ttk.Frame(self.console_area)
        self.log_frame.pack(fill="both", expand=True)

        log_text_wrap = ttk.Frame(self.log_frame)
        log_text_wrap.pack(fill="both", expand=True)

        log_scroll = ttk.Scrollbar(log_text_wrap, orient="vertical", style="Vertical.TScrollbar")
        log_scroll.pack(side="right", fill="y")

        self.log_area = tk.Text(
            log_text_wrap,
            height=16,
            state="disabled",
            wrap="word",
            yscrollcommand=log_scroll.set,
            bg="#1f2833",
            fg="#ffffff",
            insertbackground="#ff7100",
            selectbackground="#ff7100",
            selectforeground="#0b0c10",
            highlightthickness=0,
            bd=0,
            relief="flat",
        )
        self.log_area.pack(side="left", fill="both", expand=True)
        log_scroll.configure(command=self.log_area.yview)

    def _init_widget_defaults(self) -> None:
        self._set_widget_text("mode", "MODE: NORMAL (AUTO)")
        self._set_widget_text("risk", "RISK: LOW | Rebuy OK")
        self._set_widget_text("cash", "CASH: -")
        self._set_widget_text("route", "ROUTE: -")
        self._set_widget_text("summary", "SUM: -")
        self._set_widget_text("fss", "FSS: -")
        self._set_widget_text("exo", "EXO: -")
        self._set_widget_text("min", "MIN: -")
        self._set_widget_text("trd", "TRD: -")
        self._set_widget_text("xeno", "XENO: -")

        for domain in ("summary", "fss", "exo", "min", "trd", "xeno"):
            self._set_widget_active(domain, False)
        self._refresh_widget_strip()

    # ------------------------------------------------------------
    # Widget strip
    # ------------------------------------------------------------
    def _set_widget_text(self, domain: str, text: str) -> None:
        var = self._widget_vars.get(domain)
        if var is not None:
            var.set(str(text or ""))

    def _set_widget_active(self, domain: str, active: bool) -> None:
        self._widget_active[domain] = bool(active)
        if domain in self._WIDGET_ALWAYS:
            self._widget_visible[domain] = True
        else:
            self._widget_visible[domain] = bool(active)

    def _refresh_widget_strip(self) -> None:
        for domain in self._WIDGET_ORDER:
            btn = self._widget_buttons.get(domain)
            if btn is not None:
                btn.pack_forget()

        visible: list[str] = [d for d in self._WIDGET_ORDER if self._widget_visible.get(d, False)]
        if len(visible) > self._WIDGET_MAX_VISIBLE:
            ordered = [d for d in self._WIDGET_ORDER if d in self._WIDGET_ALWAYS]
            dynamic = [
                d
                for d in self._WIDGET_ORDER
                if d not in self._WIDGET_ALWAYS and self._widget_visible.get(d, False)
            ]
            free_slots = max(0, self._WIDGET_MAX_VISIBLE - len(ordered))
            visible = ordered + dynamic[:free_slots]

        for domain in visible:
            btn = self._widget_buttons.get(domain)
            if btn is not None:
                btn.pack(side="left", padx=(0, 6), pady=(0, 2))

    # ------------------------------------------------------------
    # Panel slot (single slot policy)
    # ------------------------------------------------------------
    def _on_console_area_resize(self, _event) -> None:
        self._sync_panel_height()

    def _sync_panel_height(self) -> None:
        if not self._panel_visible:
            return
        try:
            total_height = int(self.console_area.winfo_height())
        except Exception:
            total_height = 0
        if total_height <= 0:
            return

        if self._panel_collapsed:
            target = self._PANEL_COLLAPSED_HEIGHT
        else:
            target = max(self._PANEL_MIN_HEIGHT, int(total_height * self._PANEL_MAX_RATIO))

        self.panel_wrap.configure(height=target)

        if not self._panel_collapsed:
            lines = max(3, min(10, int((target - 72) / 18)))
            self.panel_text.configure(height=lines)

    def _clear_panel_actions(self) -> None:
        for btn in self._panel_action_buttons:
            try:
                btn.destroy()
            except Exception:
                pass
        self._panel_action_buttons = []

    def _set_panel_lines(self, lines: list[str]) -> None:
        text = "\n".join(str(line or "").strip() for line in lines if str(line or "").strip())
        if not text:
            text = "-"
        self.panel_text.configure(state="normal")
        self.panel_text.delete("1.0", tk.END)
        self.panel_text.insert(tk.END, text)
        self.panel_text.see("1.0")
        self.panel_text.configure(state="disabled")

    def _set_panel_actions(self, actions: list[tuple[str, Callable[[], None]]]) -> None:
        self._clear_panel_actions()
        safe_actions = actions[: self._PANEL_MAX_ACTIONS]
        if not safe_actions:
            self.panel_actions.pack_forget()
            return

        self.panel_actions.pack(fill="x", padx=8, pady=(0, 8))
        for label, callback in safe_actions:
            btn = ttk.Button(self.panel_actions, text=str(label), command=callback)
            btn.pack(side="left", padx=(0, 6))
            self._panel_action_buttons.append(btn)

    def _cancel_panel_autoclose(self) -> None:
        if self._panel_auto_close_job is None:
            return
        try:
            self.after_cancel(self._panel_auto_close_job)
        except Exception:
            pass
        self._panel_auto_close_job = None

    def _open_panel(
        self,
        *,
        domain: str,
        mode: str,
        lines: list[str],
        actions: list[tuple[str, Callable[[], None]]] | None = None,
        title: str | None = None,
        auto_close_ms: int | None = None,
    ) -> None:
        self._cancel_panel_autoclose()
        self._panel_domain = str(domain or "")
        self._panel_mode = str(mode or "")
        self._panel_collapsed = False

        panel_title = str(title or self._PANEL_TITLES.get(domain, domain.upper()) or "PANEL")
        self.lbl_panel_title.config(text=panel_title)
        self.lbl_panel_mode.config(text=f"[{self._panel_mode}]")
        self.btn_panel_toggle.config(text="Zwin")

        if not self._panel_visible:
            self.panel_wrap.pack(fill="x", pady=(0, 4), before=self.log_frame)
            self._panel_visible = True

        self.panel_body_wrap.pack(fill="both", expand=True, padx=8, pady=(0, 4))
        self._set_panel_lines(lines)
        self._set_panel_actions(actions or [])
        self._sync_panel_height()

        if auto_close_ms is not None and auto_close_ms > 0:
            self._panel_auto_close_job = self.after(auto_close_ms, self._close_panel)

    def _show_loading_panel(self, domain: str, title: str | None = None) -> None:
        self._open_panel(
            domain=domain,
            mode="Loading",
            lines=["Przetwarzam..."],
            actions=[],
            title=title,
        )

    def _show_info_panel(self, domain: str, message: str, title: str | None = None) -> None:
        self._open_panel(
            domain=domain,
            mode="Info-only",
            lines=[message],
            actions=[],
            title=title,
        )

    def _show_confirm_panel(self, domain: str, message: str, title: str | None = None) -> None:
        self._open_panel(
            domain=domain,
            mode="Confirm",
            lines=[message],
            actions=[],
            title=title,
            auto_close_ms=2800,
        )

    def _toggle_panel(self) -> None:
        if not self._panel_visible:
            return
        self._panel_collapsed = not self._panel_collapsed
        if self._panel_collapsed:
            self.panel_body_wrap.pack_forget()
            self.panel_actions.pack_forget()
            self.btn_panel_toggle.config(text="Rozwin")
        else:
            self.panel_body_wrap.pack(fill="both", expand=True, padx=8, pady=(0, 4))
            if self._panel_action_buttons:
                self.panel_actions.pack(fill="x", padx=8, pady=(0, 8))
            self.btn_panel_toggle.config(text="Zwin")
        self._sync_panel_height()

    def _close_panel(self) -> None:
        self._cancel_panel_autoclose()
        self._panel_domain = ""
        self._panel_mode = ""
        self._panel_collapsed = False
        self._panel_visible = False
        self._clear_panel_actions()
        try:
            self.panel_wrap.pack_forget()
        except Exception:
            pass

    # ------------------------------------------------------------
    # Render panel by domain
    # ------------------------------------------------------------
    def _render_summary_panel(self, force_open: bool = False) -> None:
        if not force_open and self._panel_domain != "summary":
            return

        payload = dict(self._current_exploration_summary_payload or {})
        if not payload:
            self._show_info_panel("summary", "Brak podsumowania eksploracji.")
            return

        highlights = payload.get("highlights") or []
        if isinstance(highlights, list):
            highlights_text = " | ".join(str(item) for item in highlights[:3]) or "-"
        else:
            highlights_text = "-"

        actions = [
            ("Asystent cash-in", self._on_click_cash_in_assistant),
            ("Odswiez", self._on_click_exploration_summary),
        ]
        self._open_panel(
            domain="summary",
            mode="Data",
            lines=[
                f"System: {payload.get('system') or '-'}",
                f"FSS: {payload.get('scanned_bodies') or '-'} / {payload.get('total_bodies') or '-'}",
                f"Highlights: {highlights_text}",
                f"Co dalej: {payload.get('next_step') or '-'}",
                (
                    f"Cash-in: {self._fmt_cr(payload.get('cash_in_system_estimated'))} Cr (system) | "
                    f"{self._fmt_cr(payload.get('cash_in_session_estimated'))} Cr (sesja)"
                ),
            ],
            actions=actions,
        )

    def _render_cash_panel(self, force_open: bool = False) -> None:
        if not force_open and self._panel_domain != "cash":
            return

        payload = dict(self._current_cash_in_payload or {})
        if not payload:
            self._show_info_panel("cash", "Brak aktywnej sugestii cash-in.")
            return

        options = self._cash_options()
        selected_option = self._get_selected_cash_option()
        selected_id = str((selected_option or {}).get("option_id") or "").strip()
        selected_idx = 0
        for idx, option in enumerate(options[:3], start=1):
            option_id = str(option.get("option_id") or "").strip()
            if selected_id and option_id == selected_id:
                selected_idx = idx
                break
        if selected_idx <= 0 and selected_option:
            selected_idx = 1

        selected_ui = self._cash_ui_contract(selected_option)
        selected_label = str(selected_ui.get("label") or "SAFE").strip().upper() or "SAFE"
        selected_target = str((selected_ui.get("target") or {}).get("display") or "-")

        lines = [
            f"System: {payload.get('system') or '-'} | sygnal: {(payload.get('signal') or '-').upper()}",
            (
                f"Wartosc: {self._fmt_cr(payload.get('system_value_estimated'))} Cr (system) | "
                f"{self._fmt_cr(payload.get('session_value_estimated'))} Cr (sesja)"
            ),
            f"Wybrana: {selected_idx}. {selected_label} -> {selected_target}",
        ]

        option_tokens: list[str] = []
        for idx, option in enumerate(options[:3], start=1):
            if not isinstance(option, dict):
                continue
            option_id = str(option.get("option_id") or "").strip()
            marker = "*" if selected_id and option_id == selected_id else "-"
            ui = self._cash_ui_contract(option)
            profile = str(ui.get("label") or f"OPT{idx}").strip().upper() or f"OPT{idx}"
            target_display = str((ui.get("target") or {}).get("display") or "-")
            option_tokens.append(f"{idx}[{marker}]{profile}:{target_display}")
        if option_tokens:
            lines.append("Opcje: " + " | ".join(option_tokens))

        edge_meta = payload.get("edge_case_meta") if isinstance(payload.get("edge_case_meta"), dict) else {}
        edge_reasons = [str(item).strip().lower() for item in (edge_meta.get("reasons") or []) if str(item).strip()]
        if edge_reasons:
            reasons_text = ",".join(edge_reasons)
            edge_conf = str(edge_meta.get("confidence") or payload.get("confidence") or "-").strip().upper() or "-"
            lines.append(f"Fallback: {reasons_text} | Confidence: {edge_conf}")
            edge_hint = str(edge_meta.get("ui_hint") or "").strip()
            if edge_hint:
                lines.append(f"Uwaga: {edge_hint}")

        if selected_option:
            target = dict(selected_ui.get("target") or {})
            payout = dict(selected_ui.get("payout") or {})
            eta = dict(selected_ui.get("eta") or {})
            risk = dict(selected_ui.get("risk") or {})

            kind = str(target.get("kind") or "-")
            lines.append(
                f"Target: {target.get('display') or '-'} | "
                f"{'carrier' if kind == 'carrier' else 'non-carrier'}"
            )

            if bool(payout.get("unknown")):
                payout_line = "Payout: unknown"
            else:
                payout_line = (
                    f"Payout brutto/fee/netto: "
                    f"{self._fmt_cr(payout.get('brutto'))}/"
                    f"{self._fmt_cr(payout.get('fee'))}/"
                    f"{self._fmt_cr(payout.get('netto'))} Cr"
                )
            status = str(payout.get("status") or "-")
            assumption_label = str(payout.get("assumption_label") or "").strip()
            freshness = str(payout.get("freshness_ts") or "").strip()
            if assumption_label:
                payout_line += f" | {assumption_label}"
            if freshness:
                payout_line += f" | freshness {freshness}"
            lines.append(payout_line)

            tariff_meta = dict(payout.get("tariff_meta") or {})
            if bool(tariff_meta.get("show")) and bool(tariff_meta.get("available")):
                tariff_text = "-"
                if tariff_meta.get("percent") is not None:
                    try:
                        tariff_text = f"{float(tariff_meta.get('percent')):.1f}%"
                    except Exception:
                        tariff_text = str(tariff_meta.get("percent"))
                lines.append(f"Tariff meta: {tariff_text} (informacyjne)")
            elif status:
                lines.append(f"Status payout: {status}")

            eta_text = str(eta.get("text") or "-")
            risk_tier = str(risk.get("tier") or "-").strip().upper() or "-"
            risk_reason = str(risk.get("reason") or "-").strip() or "-"
            lines.append(f"ETA: {eta_text} | Risk: {risk_tier} ({risk_reason})")

            why = str(selected_ui.get("why") or "").strip()
            if why:
                lines.append(f"Dlaczego ta opcja: {why}")

        note = str(payload.get("note") or "").strip()
        if note:
            lines.append(f"Note: {note}")

        actions: list[tuple[str, Callable[[], None]]] = []
        for idx, option in enumerate(options[:3], start=1):
            if not isinstance(option, dict):
                continue
            option_id = str(option.get("option_id") or "").strip()
            ui = self._cash_ui_contract(option)
            profile_label = str(
                ui.get("label")
                or option.get("profile")
                or f"OPT{idx}"
            ).strip().upper() or f"OPT{idx}"
            actions.append((f"{idx}. {profile_label}", lambda oid=option_id: self._on_cash_intent(oid)))
        actions.append(("Ustaw trase", self._on_cash_set_route))
        actions.append(("Copy next hop", self._on_cash_copy_next_hop))
        actions.append(("Pomijam", self._on_click_cash_in_skip))

        self._open_panel(
            domain="cash",
            mode="Data",
            lines=lines,
            actions=actions[: self._PANEL_MAX_ACTIONS],
        )

    def _render_risk_panel(self, force_open: bool = False) -> None:
        if not force_open and self._panel_domain != "risk":
            return

        payload = dict(self._current_risk_payload or {})
        if not payload:
            self._show_info_panel("risk", "Brak aktywnego alertu ryzyka/rebuy.")
            return
        contract = build_risk_rebuy_contract(payload)

        source = self._current_risk_source or "risk"
        risk_short = contract.risk_label
        rebuy_hint = contract.rebuy_label
        var_status = str(payload.get("var_status") or "-")
        system = str(payload.get("system") or "-")
        in_combat = bool(payload.get("in_combat"))
        level = str(payload.get("level") or "-").upper()
        reason = str(payload.get("reason") or payload.get("pattern_id") or "-")
        cargo_floor_cr = payload.get("cargo_floor_cr")
        cargo_expected_cr = payload.get("cargo_expected_cr")
        cargo_confidence = str(payload.get("cargo_value_confidence") or "-").upper()
        cargo_source = str(payload.get("cargo_value_source") or "-").strip().lower() or "-"

        lines = [
            f"Zrodlo: {source} | system: {system}",
            f"Risk: {risk_short} | Rebuy: {rebuy_hint} | VAR: {var_status}",
            (
                f"ValR: source={contract.source_risk_label} / "
                f"value={contract.value_risk_label} | level: {level}"
            ),
            (
                f"Powod: {reason} | Combat: {'tak' if in_combat else 'nie'} | "
                f"Hull: {self._fmt_pct(payload.get('hull_percent'))}"
            ),
            (
                f"Cargo VaR: floor {self._fmt_cr(cargo_floor_cr)} Cr | "
                f"exp {self._fmt_cr(cargo_expected_cr)} Cr"
            ),
            (
                f"Cargo: {self._fmt_num(payload.get('cargo_tons'))} t | "
                f"Conf: {cargo_confidence} | Src: {cargo_source}"
            ),
        ]

        options = payload.get("options") or []
        if isinstance(options, list) and options:
            lines.append("Opcje: " + " || ".join(str(item) for item in options[:3]))

        actions = [("Asystent cash-in", self._on_click_cash_in_assistant)]
        self._open_panel(
            domain="risk",
            mode="Data",
            lines=lines[:6],
            actions=actions,
        )

    def _render_mode_panel(self, force_open: bool = False) -> None:
        if not force_open and self._panel_domain != "mode":
            return
        ttl_text = "-" if self._mode_ttl is None else f"{int(self._mode_ttl)}s"
        since_text = "-"
        if self._mode_since > 0:
            try:
                elapsed = max(0, int(time.time() - float(self._mode_since)))
                since_text = f"{elapsed}s temu"
            except Exception:
                since_text = "-"
        src_short = self._mode_source_short(self._mode_source)
        safety_line = "Safety: -"
        if self._mode_overlay:
            safety_line = (
                f"Safety: {self._mode_overlay} overlay | "
                f"combat-silence={'ON' if self._mode_combat_silence else 'OFF'}"
            )
        elif self._mode_combat_silence:
            safety_line = "Safety: combat-silence=ON"

        actions = [
            ("AUTO", self._on_click_mode_auto),
            ("MAN NORMAL", lambda: self._on_click_mode_manual("NORMAL")),
            ("MAN EXPL", lambda: self._on_click_mode_manual("EXPLORATION")),
            ("MAN MINING", lambda: self._on_click_mode_manual("MINING")),
            ("MAN COMBAT", lambda: self._on_click_mode_manual("COMBAT")),
        ]
        self._open_panel(
            domain="mode",
            mode="Data",
            lines=[
                f"Mode: {self._mode_label} ({src_short})",
                safety_line,
                f"Confidence: {self._mode_confidence:.2f}",
                f"TTL: {ttl_text} | Since: {since_text}",
                "Tryb MANUAL blokuje AUTO switch poza safety COMBAT overlay.",
            ],
            actions=actions,
        )

    def _render_route_panel(self, force_open: bool = False) -> None:
        if not force_open and self._panel_domain != "route":
            return
        self._show_info_panel("route", self.lbl_status_route.cget("text"))

    def _cash_options(self) -> list[dict]:
        payload = dict(self._current_cash_in_payload or {})
        rows = payload.get("options") or []
        if not isinstance(rows, list):
            return []
        return [dict(item) for item in rows if isinstance(item, dict)]

    def _cash_ui_contract(self, option: dict | None) -> dict[str, Any]:
        row = dict(option or {}) if isinstance(option, dict) else {}
        ui = row.get("ui_contract")
        if isinstance(ui, dict):
            return dict(ui)

        profile = str(row.get("profile") or "SAFE").strip().upper() or "SAFE"
        target = row.get("target") if isinstance(row.get("target"), dict) else {}
        target_name = str(target.get("name") or row.get("target_station") or "").strip()
        target_system = str(target.get("system_name") or row.get("target_system") or row.get("system") or "").strip()
        target_display = target_system or "-"
        if target_name and target_system:
            target_display = f"{target_name} ({target_system})"
        elif target_name:
            target_display = target_name
        target_type = str(target.get("type") or "station").strip().lower()
        target_kind = "carrier" if "carrier" in target_type else "non-carrier"
        payout = row.get("payout") if isinstance(row.get("payout"), dict) else {}
        return {
            "label": profile,
            "target": {
                "display": target_display,
                "kind": target_kind,
            },
            "payout": {
                "brutto": payout.get("brutto"),
                "fee": payout.get("fee"),
                "netto": payout.get("netto") if payout.get("netto") is not None else row.get("estimated_value"),
                "unknown": False,
                "status": payout.get("status"),
                "assumption_label": "assumption" if payout.get("assumption") else "",
                "freshness_ts": payout.get("freshness_ts"),
                "tariff_meta": {
                    "show": bool(config.get("cash_in.show_tariff_meta", True)),
                    "available": bool((payout.get("tariff_meta") or {}).get("available")),
                    "percent": (payout.get("tariff_meta") or {}).get("tariff_percent"),
                },
            },
            "eta": {
                "text": "-" if row.get("eta_minutes") is None else f"{row.get('eta_minutes')} min",
            },
            "risk": {
                "tier": str(row.get("risk_label") or "-").upper(),
                "reason": str((row.get("reasoning") or {}).get("risk_text") or "-"),
            },
            "why": "",
        }

    def _get_selected_cash_option(self) -> dict | None:
        options = self._cash_options()
        if not options:
            return None

        selected = str(self._cash_selected_option_id or "").strip()
        if selected:
            for option in options:
                option_id = str(option.get("option_id") or "").strip()
                if option_id and option_id == selected:
                    return option

        first = dict(options[0])
        self._cash_selected_option_id = str(first.get("option_id") or "").strip()
        return first

    def _on_cash_intent(self, option_id: str) -> None:
        options = self._cash_options()
        picked = None
        oid = str(option_id or "").strip()
        for option in options:
            if str(option.get("option_id") or "").strip() == oid:
                picked = option
                break

        if picked is None:
            self._show_info_panel("cash", "Cash-in: brak opcji do ustawienia intentu.")
            return

        self._cash_selected_option_id = str(picked.get("option_id") or "").strip()
        if callable(self._on_cash_in_action):
            try:
                self._on_cash_in_action("set_intent", dict(picked))
            except Exception as exc:
                self.log(f"[CASH_IN] Blad ustawienia profilu intent: {exc}")
        label = str(picked.get("label") or "Opcja").strip() or "Opcja"
        self._show_confirm_panel("cash", f"Intent aktywny: {label}")
        self._render_cash_panel(force_open=True)

    def _on_cash_set_route(self) -> None:
        option = self._get_selected_cash_option()
        if option is None:
            self._show_info_panel("cash", "Cash-in: brak wybranej opcji trasy.")
            return
        if not callable(self._on_cash_in_action):
            self.log("[CASH_IN] Brak podpietego callbacku on_cash_in_action.")
            self._show_info_panel("cash", "Cash-in: akcja route handoff niedostępna.")
            return
        try:
            self._on_cash_in_action("set_route", dict(option))
        except Exception as exc:
            self.log(f"[CASH_IN] Blad handoff route intent: {exc}")
            self._show_info_panel("cash", "Cash-in: nie udalo sie ustawic intentu trasy.")

    def _on_cash_copy_next_hop(self) -> None:
        option = self._get_selected_cash_option()
        if option is None:
            self._show_info_panel("cash", "Cash-in: brak wybranej opcji next hop.")
            return
        if not callable(self._on_cash_in_action):
            self.log("[CASH_IN] Brak podpietego callbacku on_cash_in_action.")
            self._show_info_panel("cash", "Cash-in: akcja Copy next hop niedostępna.")
            return
        try:
            self._on_cash_in_action("copy_next_hop", dict(option))
        except Exception as exc:
            self.log(f"[CASH_IN] Blad copy next hop: {exc}")
            self._show_info_panel("cash", "Cash-in: nie udalo sie skopiowac next hop.")

    def _apply_mode_selection(self, mode_id: str | None) -> None:
        if self._app_state is None:
            self.log("[MODE] Brak app_state - zmiana trybu niedostępna.")
            return
        try:
            if mode_id is None:
                snapshot = self._app_state.set_mode_auto(source="ui.mode_panel.auto")
            else:
                snapshot = self._app_state.set_mode_manual(str(mode_id), source="ui.mode_panel.manual")
            self.apply_mode_state(snapshot)
            self._render_mode_panel(force_open=True)
        except Exception as exc:
            self.log(f"[MODE] Blad zmiany trybu: {exc}")

    def _on_click_mode_auto(self) -> None:
        self._apply_mode_selection(None)

    def _on_click_mode_manual(self, mode_id: str) -> None:
        self._apply_mode_selection(mode_id)

    # ------------------------------------------------------------
    # STATUS
    # ------------------------------------------------------------
    def _update_status_from_state(self) -> None:
        system = "-"
        live_ready = False
        if self._app_state is not None:
            try:
                system = getattr(self._app_state, "current_system", None) or "-"
                live_ready = bool(getattr(self._app_state, "has_live_system_event", False))
            except Exception:
                pass
        self.set_system_runtime_state(system, live_ready=live_ready)

        self.lbl_status_bodies.config(text="Ciala: -/-")

        route_text = "-"
        route_widget = "ROUTE: -"
        if self._app_state is not None and hasattr(self._app_state, "get_route_awareness_snapshot"):
            try:
                snap = self._app_state.get_route_awareness_snapshot()
                mode = str(snap.get("route_mode") or "idle")
                target = str(snap.get("route_target") or "").strip()
                progress = int(snap.get("route_progress_percent") or 0)
                off_route = bool(snap.get("is_off_route"))
                if mode == "awareness":
                    if off_route:
                        route_text = f"off-route ({progress}%)"
                        route_widget = f"ROUTE: ON | off-route {progress}%"
                    elif target:
                        route_text = f"on-route {progress}% -> {target}"
                        route_widget = f"ROUTE: ON | {progress}%"
                    else:
                        route_text = f"on-route {progress}%"
                        route_widget = f"ROUTE: ON | {progress}%"
                elif mode == "intent":
                    route_text = f"intent-only -> {target or '-'}"
                    route_widget = "ROUTE: OFF | intent"
                else:
                    route_text = "-"
                    route_widget = "ROUTE: OFF | -"
            except Exception:
                route_text = "-"
                route_widget = "ROUTE: -"
        elif self._route_manager is not None:
            try:
                if self._route_manager.route:
                    count = len(self._route_manager.route)
                    route_text = f"{count} punktow"
                    route_widget = f"ROUTE: ON | {count}"
            except Exception:
                pass

        self.lbl_status_route.config(text=f"Trasa: {route_text}")
        self._set_widget_text("route", route_widget)

        if self._app_state is not None and hasattr(self._app_state, "ship_state"):
            try:
                ship_state = self._app_state.ship_state
                payload = {
                    "ship_id": ship_state.ship_id,
                    "ship_type": ship_state.ship_type,
                    "unladen_mass_t": ship_state.unladen_mass_t,
                    "cargo_mass_t": ship_state.cargo_mass_t,
                    "fuel_main_t": ship_state.fuel_main_t,
                    "fuel_reservoir_t": ship_state.fuel_reservoir_t,
                }
                self.update_ship_state(payload)
            except Exception:
                pass

    def set_mode_state(
        self,
        mode_id: str,
        source: str = "AUTO",
        *,
        confidence: float | None = None,
        since: float | None = None,
        ttl: float | None = None,
        overlay: str | None = None,
        combat_silence: bool | None = None,
    ) -> None:
        norm = str(mode_id or "NORMAL").strip().upper() or "NORMAL"
        src = str(source or "AUTO").strip().upper() or "AUTO"
        self._mode_label = norm
        self._mode_source = src
        if confidence is not None:
            try:
                self._mode_confidence = max(0.0, min(1.0, float(confidence)))
            except Exception:
                pass
        if since is not None:
            try:
                self._mode_since = float(since)
            except Exception:
                pass
        if ttl is not None:
            try:
                ttl_val = float(ttl)
                self._mode_ttl = ttl_val if ttl_val > 0 else None
            except Exception:
                self._mode_ttl = None
        elif ttl is None:
            self._mode_ttl = None
        self._mode_overlay = str(overlay or "").strip().upper() or None
        if combat_silence is not None:
            self._mode_combat_silence = bool(combat_silence)
        else:
            self._mode_combat_silence = bool(norm == "COMBAT" or self._mode_overlay == "COMBAT")

        src_short = self._mode_source_short(src)
        widget_text = f"MODE: {norm} ({src_short})"
        status_text = f"Status: [{norm}] ({src_short})"
        if self._mode_overlay:
            widget_text += f" | SAFE {self._mode_overlay}"
            status_text += f" [SAFE {self._mode_overlay}]"
        self._set_widget_text("mode", widget_text)
        self.lbl_header_status.config(text=status_text)
        if self._panel_domain == "mode":
            self._render_mode_panel(force_open=True)

    def apply_mode_state(self, state: dict | None) -> None:
        snapshot = dict(state or {})
        self.set_mode_state(
            str(snapshot.get("mode_id") or "NORMAL"),
            str(snapshot.get("mode_source") or "AUTO"),
            confidence=snapshot.get("mode_confidence"),
            since=snapshot.get("mode_since"),
            ttl=snapshot.get("mode_ttl"),
            overlay=snapshot.get("mode_overlay"),
            combat_silence=snapshot.get("mode_combat_silence"),
        )

    def update_ship_state(self, data: dict) -> None:
        ship_type = data.get("ship_type") or "-"
        ship_id = data.get("ship_id")
        if ship_id is not None:
            ship_text = f"{ship_type} (#{ship_id})"
        else:
            ship_text = f"{ship_type}"
        self.lbl_status_ship.config(text=f"Statek: {ship_text}")

        unladen = data.get("unladen_mass_t")
        if unladen is None:
            self.lbl_status_mass.config(text="Masa: - t")
        else:
            self.lbl_status_mass.config(text=f"Masa: {float(unladen):.1f} t")

        cargo = data.get("cargo_mass_t")
        if cargo is None:
            self.lbl_status_cargo.config(text="Cargo: - t")
        else:
            self.lbl_status_cargo.config(text=f"Cargo: {float(cargo):.1f} t")

        fuel_main = data.get("fuel_main_t")
        fuel_res = data.get("fuel_reservoir_t")
        if fuel_main is None and fuel_res is None:
            self.lbl_status_fuel.config(text="Paliwo: -/- t")
        else:
            fm = "-" if fuel_main is None else f"{float(fuel_main):.2f}"
            fr = "-" if fuel_res is None else f"{float(fuel_res):.2f}"
            self.lbl_status_fuel.config(text=f"Paliwo: {fm}/{fr} t")

        if not config.get("ui_show_jump_range", True):
            self.lbl_status_jr.config(text="JR: -")
            return

        location = str(config.get("ui_jump_range_location", "overlay")).strip().lower()
        if location not in ("statusbar", "both"):
            self.lbl_status_jr.config(text="JR: -")
            return

        jr = data.get("jump_range_current_ly")
        if jr is None:
            self.lbl_status_jr.config(text="JR: -")
            return

        try:
            jr_val = float(jr)
        except Exception:
            self.lbl_status_jr.config(text="JR: -")
            return

        txt = f"JR: {jr_val:.2f} LY"
        if config.get("ui_jump_range_show_limit", True):
            limit = data.get("jump_range_limited_by")
            if limit in ("fuel", "mass"):
                txt += f" ({limit})"
        if config.get("ui_jump_range_debug_details", False):
            fuel_needed = data.get("jump_range_fuel_needed_t")
            if fuel_needed is not None:
                try:
                    txt += f" fuel:{float(fuel_needed):.2f}t"
                except Exception:
                    pass
        self.lbl_status_jr.config(text=txt)

    def set_system_runtime_state(self, system_name: str, live_ready: bool) -> None:
        system = (system_name or "").strip()
        if system in ("", "-", "Unknown", "Nieznany"):
            system = "-"

        if live_ready and system != "-":
            self.lbl_status_system.config(text=f"System: {system}")
            self.lbl_header_system.config(text=f"Obecny system: {system}")
        else:
            self.lbl_status_system.config(text="System: [Czekam na dane...]")
            self.lbl_header_system.config(text="Obecny system: [Czekam na dane...]")

    # ------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------
    def _safe_callback(self, callback, error_prefix: str, missing_message: str) -> bool:
        if callback is None:
            self.log(missing_message)
            return False
        try:
            callback()
            return True
        except Exception as exc:
            self.log(f"{error_prefix}: {exc}")
            return False

    def _on_widget_click(self, domain: str) -> None:
        if domain == "summary":
            if self._current_exploration_summary_payload:
                self._render_summary_panel(force_open=True)
            else:
                self._show_loading_panel("summary")
                self._safe_callback(
                    self._on_generate_exploration_summary,
                    "[EXPLORATION_SUMMARY] Blad triggera podsumowania",
                    "[EXPLORATION_SUMMARY] Brak podpietego callbacku on_generate_exploration_summary.",
                )
        elif domain == "cash":
            if self._current_cash_in_payload:
                self._render_cash_panel(force_open=True)
            else:
                self._show_loading_panel("cash")
                self._safe_callback(
                    self._on_generate_cash_in_assistant,
                    "[CASH_IN] Blad triggera asystenta cash-in",
                    "[CASH_IN] Brak podpietego callbacku on_generate_cash_in_assistant.",
                )
        elif domain == "risk":
            self._render_risk_panel(force_open=True)
        elif domain == "mode":
            self._render_mode_panel(force_open=True)
        elif domain == "route":
            self._render_route_panel(force_open=True)
        else:
            self._show_info_panel(domain, "Brak szczegolow dla tego widgetu.")

    def _on_click_generate_science(self) -> None:
        self._show_loading_panel("tools", title="SCIENCE SHEETS")
        ok = self._safe_callback(
            self._on_generate_science_excel,
            "[SCIENCE_DATA] Blad przy uruchamianiu generatora",
            "[SCIENCE_DATA] Brak podpietego callbacku on_generate_science_excel.",
        )
        if ok:
            self._show_confirm_panel("tools", "Uruchomiono generowanie arkuszy naukowych.")
        else:
            self._show_info_panel("tools", "Nie udalo sie uruchomic generatora arkuszy naukowych.")

    def _on_click_generate_modules(self) -> None:
        self._show_loading_panel("tools", title="MODULES DATA")
        ok = self._safe_callback(
            self._on_generate_modules_data,
            "[MODULES_DATA] Blad przy uruchamianiu generatora",
            "[MODULES_DATA] Brak podpietego callbacku on_generate_modules_data.",
        )
        if ok:
            self._show_confirm_panel("tools", "Uruchomiono generowanie danych modulow.")
        else:
            self._show_info_panel("tools", "Nie udalo sie uruchomic generatora danych modulow.")

    def _on_click_exploration_summary(self) -> None:
        self._show_loading_panel("summary")
        self._safe_callback(
            self._on_generate_exploration_summary,
            "[EXPLORATION_SUMMARY] Blad triggera podsumowania",
            "[EXPLORATION_SUMMARY] Brak podpietego callbacku on_generate_exploration_summary.",
        )

    def _on_click_cash_in_assistant(self) -> None:
        self._show_loading_panel("cash")
        self._safe_callback(
            self._on_generate_cash_in_assistant,
            "[CASH_IN] Blad triggera asystenta cash-in",
            "[CASH_IN] Brak podpietego callbacku on_generate_cash_in_assistant.",
        )

    def _on_click_cash_in_skip(self) -> None:
        ok = self._safe_callback(
            self._on_skip_cash_in_assistant,
            "[CASH_IN] Blad akcji Pomijam",
            "[CASH_IN] Brak podpietego callbacku on_skip_cash_in_assistant.",
        )
        if ok:
            self._set_widget_text("cash", "CASH: SKIP | sig")
            self._show_confirm_panel("cash", "Cash-in pomijam: aktywne dla biezacego kontekstu.")

    # ------------------------------------------------------------
    # Log and external API
    # ------------------------------------------------------------
    def log(self, text: str) -> None:
        self.log_area.config(state="normal")
        self.log_area.insert(tk.END, str(text or "") + "\n")
        self.log_area.see(tk.END)
        self.log_area.config(state="disabled")

    def get_current_exploration_summary_payload(self) -> dict:
        return dict(self._current_exploration_summary_payload or {})

    def get_current_cash_in_signature(self) -> str:
        return str(self._current_cash_in_signature or "").strip()

    def update_exploration_summary(self, payload: dict) -> None:
        if not isinstance(payload, dict):
            return
        self._current_exploration_summary_payload = dict(payload)

        scanned = payload.get("scanned_bodies")
        total = payload.get("total_bodies")
        if scanned is not None and total is not None:
            self.lbl_status_bodies.config(text=f"Ciala: {scanned}/{total}")

        next_step = str(payload.get("next_step") or "-").strip() or "-"
        signal = str(payload.get("cash_in_signal") or "-").strip().upper() or "-"
        self._set_widget_text("summary", f"SUM: READY | next: {next_step.lower()[:20]}")
        self._set_widget_active("summary", True)

        if not self._current_cash_in_payload:
            value_hint = self._fmt_m(payload.get("cash_in_session_estimated"))
            self._set_widget_text("cash", f"CASH: {self._signal_to_bucket(signal)} | {value_hint} | -")

        self._refresh_widget_strip()

        if self._panel_domain == "summary":
            self._render_summary_panel(force_open=True)

    def update_cash_in_assistant(self, payload: dict) -> None:
        if not isinstance(payload, dict):
            return
        self._current_cash_in_payload = dict(payload)
        self._current_cash_in_signature = str(payload.get("signature") or "").strip()
        options = self._cash_options()
        selected = str(self._cash_selected_option_id or "").strip()
        selected_exists = False
        if selected:
            selected_exists = any(str(row.get("option_id") or "").strip() == selected for row in options)
        if not selected_exists:
            self._cash_selected_option_id = str((options[0].get("option_id") if options else "") or "").strip()

        signal = str(payload.get("signal") or "-").strip().upper() or "-"
        option_count = len(options) if isinstance(options, list) else 0
        value_hint = self._fmt_m(payload.get("session_value_estimated"))
        self._set_widget_text(
            "cash",
            f"CASH: {self._signal_to_bucket(signal)} | {value_hint} | {option_count} opt",
        )
        self._refresh_widget_strip()

        if self._panel_domain == "cash":
            self._render_cash_panel(force_open=True)

    def update_survival_rebuy(self, payload: dict) -> None:
        if not isinstance(payload, dict):
            return
        self._current_survival_payload = dict(payload)
        self._current_risk_payload = dict(payload)
        self._current_risk_source = "survival_rebuy"

        contract = build_risk_rebuy_contract(payload)
        self._set_widget_text("risk", f"RISK: {contract.risk_label} | {contract.rebuy_label}")
        self._refresh_widget_strip()

        is_p0 = self._is_p0_risk(payload)
        if is_p0:
            self._render_risk_panel(force_open=True)
            return
        if self._panel_domain == "risk":
            self._render_risk_panel(force_open=True)

    def update_combat_awareness(self, payload: dict) -> None:
        if not isinstance(payload, dict):
            return
        self._current_combat_payload = dict(payload)
        self._current_risk_payload = dict(payload)
        self._current_risk_source = "combat_awareness"

        contract = build_risk_rebuy_contract(payload)
        self._set_widget_text("risk", f"RISK: {contract.risk_label} | {contract.rebuy_label}")
        self._refresh_widget_strip()

        is_p0 = self._is_p0_risk(payload)
        if is_p0:
            self._render_risk_panel(force_open=True)
            return
        if self._panel_domain == "risk":
            self._render_risk_panel(force_open=True)

    # ------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------
    @staticmethod
    def _fmt_num(value) -> str:
        try:
            return f"{int(round(float(value))):,}".replace(",", " ")
        except Exception:
            return "-"

    @staticmethod
    def _fmt_cr(value) -> str:
        return PulpitTab._fmt_num(value)

    @staticmethod
    def _fmt_m(value) -> str:
        try:
            amount = float(value or 0.0)
        except Exception:
            return "-"
        if amount <= 0:
            return "0.0M"
        return f"{amount / 1_000_000.0:.1f}M"

    @staticmethod
    def _fmt_pct(value) -> str:
        try:
            return f"{float(value):.0f}%"
        except Exception:
            return "-"

    @staticmethod
    def _risk_short(risk_status) -> str:
        text = str(risk_status or "").strip().upper()
        if "CRIT" in text:
            return "CRIT"
        if "HIGH" in text:
            return "HIGH"
        if "MED" in text:
            return "MED"
        if "LOW" in text:
            return "LOW"
        return "-"

    @staticmethod
    def _signal_to_bucket(signal: str) -> str:
        s = str(signal or "").strip().upper()
        if s in {"WYSOKI", "HIGH"}:
            return "HIGH"
        if s in {"SREDNI", "SREDNI", "MEDIUM", "MED"}:
            return "MED"
        if s in {"NISKI", "LOW"}:
            return "LOW"
        return s or "-"

    @staticmethod
    def _mode_source_short(source: str) -> str:
        src = str(source or "").strip().upper()
        if src == "MANUAL":
            return "MAN"
        if src == "RESTORED":
            return "REST"
        return src or "AUTO"

    @staticmethod
    def _is_p0_risk(payload: dict) -> bool:
        contract = build_risk_rebuy_contract(payload)
        if contract.rebuy_label == "NO REBUY":
            return True
        if contract.risk_label == "CRIT":
            return True

        risk = str(payload.get("risk_status") or "").strip().upper()
        level = str(payload.get("level") or "").strip().lower()
        return "CRIT" in risk or level == "critical"

    @staticmethod
    def _rebuy_hint(payload: dict) -> str:
        credits = payload.get("credits")
        rebuy = payload.get("rebuy_cost")
        try:
            credits_f = float(credits)
            rebuy_f = float(rebuy)
        except Exception:
            return "Rebuy ?"
        if rebuy_f <= 0:
            return "Rebuy ?"
        if credits_f < rebuy_f:
            return "NO REBUY"
        if credits_f < (rebuy_f * 1.2):
            return "REBUY LOW"
        return "Rebuy OK"

