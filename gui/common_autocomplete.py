import tkinter as tk
import threading
from logic import utils


class AutocompleteController:
    def __init__(self, root_window, entry_widget, min_chars=3, suggest_func=None):
        self.root = root_window
        self.entry = entry_widget
        self.min_chars = min_chars
        self.suggest_func = suggest_func
        self._req_gen = 0

        self.sug_list = tk.Listbox(
            self.root, width=30, height=6,
            bg="#1f2833", relief="solid", borderwidth=1
        )
        self.sug_list.bind("<ButtonRelease-1>", self._on_list_click)
        self.sug_list.bind("<Return>", self._on_list_return)

        self.entry.bind("<KeyRelease>", self._on_type)
        self.entry.bind("<Down>", self._on_arrow_down)
        self.entry.bind("<Up>", self._on_arrow_up)
        self.entry.bind("<Return>", self._on_enter_key)
        self.entry.bind("<FocusOut>", self._on_focus_out)
        self.entry.bind("<Unmap>", self._on_unmap)
        self.root.bind_all("<ButtonRelease-1>", self._on_global_click, add="+")

    def hide(self):
        self._req_gen += 1
        self.sug_list.place_forget()

    def _on_type(self, e):
        if e.keysym in ["Up", "Down", "Return", "Enter", "Left", "Right"]:
            return
        t = self.entry.get()
        if len(t) >= self.min_chars:
            self._req_gen += 1
            req_gen = self._req_gen
            query = t
            threading.Thread(
                target=self._th_suggest,
                args=(t, req_gen, query),
                daemon=True,
            ).start()
        else:
            self.hide()

    def _th_suggest(self, t, req_gen, query):
        if self.suggest_func is not None:
            s = self.suggest_func(t)
        else:
            s = utils.pobierz_sugestie(t)

        def apply():
            if req_gen != self._req_gen:
                return
            if (self.entry.get() or "").strip() != query:
                return
            self._show_list(s)

        self.root.after(0, apply)

    def _show_list(self, items):
        # brak wyników -> chowamy listę
        if not items:
            self.hide()
            return

        # jeśli entry zostało już fizycznie ukryte (np. zamknięte okno dialogowe),
        # nie ma sensu pokazywać listy
        if not self.entry.winfo_ismapped():
            self.hide()
            return
        if not self.entry.winfo_viewable():
            self.hide()
            return
        if str(self.root.focus_get()) not in (str(self.entry), str(self.sug_list)):
            self.hide()
            return

        # UWAGA: nie blokujemy już wyświetlania na podstawie focus_get()
        # (wcześniej mogło to powodować, że lista była pusta, gdy fokus
        # na chwilę uciekł zanim wróciła odpowiedź z API)

        self.sug_list.delete(0, tk.END)
        for x in items:
            self.sug_list.insert(tk.END, x)

        x = self.entry.winfo_rootx() - self.root.winfo_rootx()
        y = self.entry.winfo_rooty() - self.root.winfo_rooty() + self.entry.winfo_height()
        w = self.entry.winfo_width()

        self.sug_list.place(x=x, y=y, width=w)
        self.sug_list.lift()

    def _on_arrow_down(self, e):
        if self.sug_list.winfo_ismapped() and str(self.root.focus_get()) == str(self.entry):
            self.sug_list.focus_set()
            self.sug_list.selection_clear(0, tk.END)
            self.sug_list.selection_set(0)
            self.sug_list.activate(0)
            return "break"

    def _on_arrow_up(self, e):
        return "break"

    def _on_enter_key(self, e):
        if str(self.root.focus_get()) != str(self.entry):
            return
        if self.sug_list.winfo_ismapped():
            idx = self.sug_list.curselection()[0] if self.sug_list.curselection() else 0
            self._choose(idx)
        return "break"

    def _on_list_click(self, e):
        idx = self.sug_list.nearest(e.y)
        if idx is not None:
            self.sug_list.selection_clear(0, tk.END)
            self.sug_list.selection_set(idx)
            self.sug_list.activate(idx)
            self._choose(idx)

    def _on_list_return(self, e):
        if self.sug_list.curselection():
            self._choose(self.sug_list.curselection()[0])
            return
        idx = self.sug_list.index("active")
        if idx is not None:
            self._choose(idx)

    def _on_focus_out(self, _e):
        self.root.after(1, self._maybe_hide_on_focus_out)

    def _maybe_hide_on_focus_out(self):
        if str(self.root.focus_get()) == str(self.sug_list):
            return
        self.hide()

    def _on_unmap(self, _e):
        self.hide()

    def _on_global_click(self, e):
        if str(e.widget) in (str(self.entry), str(self.sug_list)):
            return
        self.hide()

    def _choose(self, idx):
        t = self.sug_list.get(idx)
        self.entry.delete(0, tk.END)
        self.entry.insert(0, t)
        self.hide()
        self.entry.focus_set()
        self.entry.icursor(tk.END)
