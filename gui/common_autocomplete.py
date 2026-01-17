import tkinter as tk
import threading
from weakref import WeakKeyDictionary
from logic import utils

AUTOCOMPLETE_DEBUG = True

def _dbg(msg):
    if AUTOCOMPLETE_DEBUG:
        print(f"[ACDBG] {msg}")


USE_SINGLETON_LISTBOX = True

def _hide_all_autocomplete_listboxes(root):
    if root is None:
        return 0
    count = 0
    try:
        children = root.winfo_children()
    except tk.TclError:
        return 0
    for widget in children:
        try:
            if isinstance(widget, tk.Listbox) and getattr(widget, "_renata_autocomplete", False):
                widget.place_forget()
                widget.delete(0, tk.END)
                count += 1
        except tk.TclError:
            continue
    return count

class AutocompleteController:
    _instances = []
    _shared_listbox = None
    _active_owner = None
    _entry_map = WeakKeyDictionary()
    _shared_binds_installed = False
    def __init__(self, root_window, entry_widget, min_chars=3, suggest_func=None):
        self.root = root_window
        self.entry = entry_widget
        self.min_chars = min_chars
        self.suggest_func = suggest_func
        self._req_gen = 0
        AutocompleteController._instances.append(self)
        AutocompleteController._entry_map[self.entry] = self
        if USE_SINGLETON_LISTBOX:
            if AutocompleteController._shared_listbox is None:
                AutocompleteController._shared_listbox = tk.Listbox(
                    self.root, width=30, height=6,
                    bg="#1f2833", relief="solid", borderwidth=1
                )
                AutocompleteController._shared_listbox._renata_autocomplete = True
            if not AutocompleteController._shared_binds_installed:
                AutocompleteController._shared_listbox.bind(
                    "<Button-1>",
                    AutocompleteController._on_shared_list_click,
                    add="+"
                )
                AutocompleteController._shared_listbox.bind(
                    "<Return>",
                    AutocompleteController._on_shared_list_enter,
                    add="+"
                )
                AutocompleteController._shared_listbox.bind(
                    "<Button-1>",
                    AutocompleteController._on_shared_list_event,
                    add="+"
                )
                AutocompleteController._shared_listbox.bind(
                    "<ButtonRelease-1>",
                    AutocompleteController._on_shared_list_event,
                    add="+"
                )
                AutocompleteController._shared_binds_installed = True
            self.sug_list = AutocompleteController._shared_listbox
        else:
            self.sug_list = tk.Listbox(
                self.root, width=30, height=6,
                bg="#1f2833", relief="solid", borderwidth=1
            )
            self.sug_list._renata_autocomplete = True
            self.sug_list.bind("<Button-1>", self._on_list_click, add="+")
            self.sug_list.bind("<Return>", self._on_list_return)

        self.entry.bind("<KeyRelease>", self._on_type)
        self.entry.bind("<Down>", self._on_arrow_down)
        self.entry.bind("<Up>", self._on_arrow_up)
        self.entry.bind("<Return>", self._on_enter_key)
        self.entry.bind("<FocusOut>", self._on_focus_out)
        self.entry.bind("<Unmap>", self._on_unmap)
        self.root.bind_all("<ButtonRelease-1>", self._on_global_click, add="+")
        self.root.bind_all("<<NotebookTabChanged>>", self._on_tab_changed, add="+")

    @classmethod
    def hide_all(cls):
        if USE_SINGLETON_LISTBOX:
            cls._hide_shared_listbox()
            return
        for inst in list(cls._instances):
            inst.hide()

    @classmethod
    def _hide_shared_listbox(cls):
        if cls._shared_listbox is not None:
            cls._shared_listbox.place_forget()
        cls._active_owner = None

    @classmethod
    def _on_shared_list_click(cls, e):
        owner = cls._active_owner
        if owner is None:
            try:
                focus_widget = e.widget.focus_get()
            except tk.TclError:
                focus_widget = None
            owner = cls._entry_map.get(focus_widget)
        _dbg(
            f"SHARED_CLICK start widget={repr(e.widget)} "
            f"y={e.y} nearest={cls._shared_listbox.nearest(e.y) if cls._shared_listbox is not None else None} "
            f"size={cls._shared_listbox.size() if cls._shared_listbox is not None else None} "
            f"active_owner={hex(id(owner)) if owner else None}"
        )
        if owner is None:
            cls._hide_shared_listbox()
            return "break"
        listbox = cls._shared_listbox
        if listbox is None:
            return "break"
        idx = listbox.nearest(e.y)
        if idx is None or idx < 0:
            return "break"
        owner._choose(idx)
        return "break"

    @classmethod
    def _on_shared_list_event(cls, e):
        _dbg(
            f"LISTBOX_EVENT type={e.type} y={e.y} x={e.x} "
            f"size={cls._shared_listbox.size() if cls._shared_listbox is not None else None}"
        )

    @classmethod
    def _on_shared_list_enter(cls, e):
        owner = cls._active_owner
        if owner is None:
            cls._hide_shared_listbox()
            return "break"
        listbox = cls._shared_listbox
        if listbox is None:
            return "break"
        idx = listbox.index("active")
        if idx is None:
            size = listbox.size()
            if size == 1:
                idx = 0
        if idx is None or idx < 0:
            return "break"
        owner._choose(idx)
        return "break"

    def hide(self, reason=""):
        _dbg(f"HIDE reason={reason} owner={hex(id(self))} active={hex(id(AutocompleteController._active_owner)) if AutocompleteController._active_owner else None} mapped={self.sug_list.winfo_ismapped()}")
        self._req_gen += 1
        if USE_SINGLETON_LISTBOX:
            if AutocompleteController._shared_listbox is not None:
                AutocompleteController._shared_listbox.place_forget()
            if AutocompleteController._active_owner is self:
                AutocompleteController._active_owner = None
            return
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
        _dbg(f"SHOW size={len(items)} mapped_before={self.sug_list.winfo_ismapped()} owner={hex(id(self))}")
        # brak wynik+-w -> chowamy list|T
        if not items:
            self.hide()
            return

        # je+?li entry zosta+,o ju+- fizycznie ukryte (np. zamkni|Tte okno dialogowe),
        # nie ma sensu pokazywa|? listy
        if not self.entry.winfo_ismapped():
            self.hide()
            return
        if not self.entry.winfo_viewable():
            self.hide()
            return
        if str(self.root.focus_get()) not in (str(self.entry), str(self.sug_list)):
            self.hide()
            return

        if USE_SINGLETON_LISTBOX:
            AutocompleteController._active_owner = self
            if AutocompleteController._shared_listbox is not None:
                AutocompleteController._shared_listbox.place_forget()
        else:
            AutocompleteController.hide_all()

        # UWAGA: nie blokujemy ju+- wy+?wietlania na podstawie focus_get()
        # (wcze+?niej mog+,o to powodowa|?, +-e lista by+,a pusta, gdy fokus
        # na chwil|T uciek+, zanim wr+-ci+,a odpowied+| z API)

        self.sug_list.delete(0, tk.END)
        for x in items:
            self.sug_list.insert(tk.END, x)

        x = self.entry.winfo_rootx() - self.root.winfo_rootx()
        y = self.entry.winfo_rooty() - self.root.winfo_rooty() + self.entry.winfo_height()
        w = self.entry.winfo_width()

        self.sug_list.place(x=x, y=y, width=w)
        self.sug_list.lift()
        _dbg(
            "LISTBOX_GEOM "
            f"ismapped={self.sug_list.winfo_ismapped()} "
            f"viewable={self.sug_list.winfo_viewable()} "
            f"rootx={self.sug_list.winfo_rootx()} "
            f"rooty={self.sug_list.winfo_rooty()} "
            f"width={self.sug_list.winfo_width()} "
            f"height={self.sug_list.winfo_height()} "
            f"active_owner={hex(id(AutocompleteController._active_owner)) if AutocompleteController._active_owner else None}"
        )
        _dbg(
            "LISTBOX_BINDS "
            f"button1={self.sug_list.bind('<Button-1>')} "
            f"button1_release={self.sug_list.bind('<ButtonRelease-1>')} "
            f"button1_double={self.sug_list.bind('<Double-Button-1>')} "
            f"bindtags={self.sug_list.bindtags()}"
        )

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
        _dbg(
            "LIST_CLICK start widget=" + repr(e.widget) +
            f" y={e.y} nearest={self.sug_list.nearest(e.y)} size={self.sug_list.size()} active={self.sug_list.index('active')} cur={self.sug_list.curselection()}"
        )
        if not self.entry.winfo_viewable():
            self.hide(reason="list_click_entry_hidden")
            return
        idx = self.sug_list.nearest(e.y)
        if idx is None or idx < 0:
            return
        self.sug_list.selection_clear(0, tk.END)
        self.sug_list.selection_set(idx)
        self.sug_list.activate(idx)
        self._choose(idx)
        _dbg("LIST_CLICK end hide_called=True")

    def _on_list_return(self, e):
        if self.sug_list.curselection():
            self._choose(self.sug_list.curselection()[0])
            return
        idx = self.sug_list.index('active')
        if idx is None:
            size = self.sug_list.size()
            if size == 1:
                idx = 0
        if idx is not None:
            self.sug_list.selection_clear(0, tk.END)
            self.sug_list.selection_set(idx)
            self.sug_list.activate(idx)
            self._choose(idx)

    def _on_focus_out(self, _e):
        self.root.after(1, self._maybe_hide_on_focus_out)

    def _maybe_hide_on_focus_out(self):
        if str(self.root.focus_get()) == str(self.sug_list):
            return
        self.hide()

    def _on_unmap(self, _e):
        self.hide()

    def _on_tab_changed(self, _e):
        if USE_SINGLETON_LISTBOX:
            AutocompleteController._hide_shared_listbox()
            return
        self.hide()
        _hide_all_autocomplete_listboxes(self.root)

    def _on_global_click(self, e):
        if USE_SINGLETON_LISTBOX and AutocompleteController._active_owner not in (None, self):
            return
        is_list = (
            e.widget is AutocompleteController._shared_listbox
            or getattr(e.widget, "_renata_autocomplete", False)
        )
        is_entry = e.widget in AutocompleteController._entry_map
        x_root = getattr(e, "x_root", None)
        y_root = getattr(e, "y_root", None)
        hit_widget = None
        try:
            if x_root is not None and y_root is not None:
                hit_widget = self.root.winfo_containing(x_root, y_root)
        except tk.TclError:
            hit_widget = None
        _dbg(f"HITTEST x_root={x_root} y_root={y_root} widget={repr(e.widget)}")
        _dbg(
            f"HITTEST under_cursor={repr(hit_widget)} "
            f"class={hit_widget.winfo_class() if hit_widget is not None else None}"
        )
        print(f"[ACDBG] GLOBAL_CLICK_ENTRY widget={repr(e.widget)} is_entry={is_entry}")
        _dbg(
            "GLOBAL_CLICK widget=" + repr(e.widget) +
            f" is_list={is_list} is_entry={is_entry} active={hex(id(AutocompleteController._active_owner)) if AutocompleteController._active_owner else None} mapped={self.sug_list.winfo_ismapped()}"
        )
        if is_list:
            _dbg("GLOBAL_CLICK action=ignore_listbox")
            return
        if is_entry:
            _dbg("GLOBAL_CLICK action=ignore_entry")
            return
        if USE_SINGLETON_LISTBOX:
            self.root.after_idle(AutocompleteController._hide_shared_listbox)
            _dbg("GLOBAL_CLICK action=hide_shared")
        else:
            self.root.after_idle(self.hide, "global_click_outside")
            _dbg("GLOBAL_CLICK action=hide")
            _hide_all_autocomplete_listboxes(self.root)

    def _choose(self, idx):
        chosen = None
        if self.sug_list.curselection():
            chosen = self.sug_list.curselection()[0]
        elif idx is not None:
            chosen = idx
        else:
            chosen = self.sug_list.index('active')
            if chosen is None:
                size = self.sug_list.size()
                if size == 1:
                    chosen = 0
        if chosen is None or chosen < 0:
            return
        t = self.sug_list.get(chosen)
        self.entry.delete(0, tk.END)
        self.entry.insert(0, t)
        self.hide(reason="choose")
        self.entry.focus_set()
        self.entry.icursor(tk.END)
