import tkinter as tk
from tkinter import ttk, simpledialog
from gui.dialogs.add_entry import AddEntryDialog

# optional clipboard support
try:
    import pyperclip
except ImportError:
    pyperclip = None

COLOR_BG     = '#0b0c10'
COLOR_FG     = '#ff7100'
COLOR_SEC    = '#c5c6c7'
COLOR_ACCENT = '#1f2833'

class LogbookTab(tk.Frame):
    def __init__(self, parent, app=None, manager=None, *args, **kwargs):
        self.app = app
        self.manager = manager
        super().__init__(parent, bg=COLOR_BG, *args, **kwargs)
        self.node_map = {}
        self._configure_style()
        self._create_widgets()
        # bind right-click for context menu
        self.tree.bind('<Button-3>', self._show_context_menu)
        self.refresh_tree()

    def _configure_style(self):
        style = ttk.Style()
        style.configure(
            'Custom.Treeview',
            background=COLOR_ACCENT,
            fieldbackground=COLOR_ACCENT,
            foreground=COLOR_FG,
            rowheight=24
        )
        style.configure(
            'Custom.Treeview.Heading',
            background=COLOR_ACCENT,
            foreground=COLOR_SEC,
            relief='flat'
        )
        style.map(
            'Custom.Treeview.Heading',
            background=[('active', COLOR_ACCENT)]
        )

    def _create_widgets(self):
        # Treeview
        self.tree = ttk.Treeview(
            self,
            columns=('created_at', 'title'),
            show='tree headings',
            style='Custom.Treeview'
        )
        self.tree.heading('#0', text='Tytuł')
        self.tree.heading('created_at', text='Data')
        self.tree.heading('title', text='Opis')
        self.tree.pack(fill='both', expand=True, padx=10, pady=10)

        # Buttons frame
        btn_frame = tk.Frame(self, bg=COLOR_BG)
        btn_frame.pack(pady=(0,10))

        btn_entry = tk.Button(
            btn_frame, text='[+ Dodaj Wpis]',
            bg=COLOR_ACCENT, fg=COLOR_FG,
            activebackground=COLOR_BG, activeforeground=COLOR_FG,
            relief='flat', command=self._add_entry
        )
        btn_entry.pack(side='left', padx=5)

        btn_folder = tk.Button(
            btn_frame, text='[+ Dodaj Folder]',
            bg=COLOR_ACCENT, fg=COLOR_FG,
            activebackground=COLOR_BG, activeforeground=COLOR_FG,
            relief='flat', command=self._add_folder
        )
        btn_folder.pack(side='left', padx=5)

    def refresh_tree(self):
        # Clear
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.node_map.clear()
        # Populate
        for node in self.manager.data:
            self._insert_node('', node)

    def _insert_node(self, parent, node):
        # Insert node and map id
        text = node.get('title', '')
        content = node.get('content') or ''
        if len(content) > 60:
            snippet = content[:57] + '…'
        else:
            snippet = content
        values = (node.get('created_at', ''), snippet)
        item = self.tree.insert(parent, 'end', text=text, values=values)
        self.node_map[item] = node['id']
        # If folder, recurse
        if node.get('type') == 'folder':
            for child in node.get('children', []):
                self._insert_node(item, child)

    def _get_selected_uuid(self):
        sel = self.tree.selection()
        if not sel:
            return None
        sel_id = sel[0]
        uuid = self.node_map.get(sel_id)
        # ensure folder for entry, or use parent
        node = self.manager._index.get(uuid)
        if node.get('type') != 'folder':
            return node.get('parent_id')
        return uuid

    def _add_entry(self):
        parent_uuid = self._get_selected_uuid()
        # Smart context for defaults
        system, body, coords = self._get_smart_context()
        dialog = AddEntryDialog(self, system=system, body=body, coords=coords)
        self.wait_window(dialog)
        data = getattr(dialog, 'result_data', None)
        if data:
            self.manager.add_entry(
                parent_uuid,
                data['title'], data['content'],
                data['system'], data['body'], data['coords']
            )
            self.refresh_tree()

    def _add_folder(self):
        parent_uuid = self._get_selected_uuid()
        name = simpledialog.askstring("Nowy folder", "Nazwa folderu:", parent=self)
        if name:
            self.manager.add_folder(parent_uuid, name)
            self.refresh_tree()

    def _show_context_menu(self, event):
        # helper to copy to clipboard
        def _copy_to_clipboard(text):
            if not text:
                return
            if pyperclip:
                pyperclip.copy(text)
            else:
                try:
                    self.clipboard_clear()
                    self.clipboard_append(text)
                except Exception:
                    pass

        # identify item
        item = self.tree.identify_row(event.y)
        if not item:
            return
        self.tree.selection_set(item)
        uuid = self.node_map.get(item)
        node = self.manager._index.get(uuid, {})
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label='[+ Dodaj wpis]', command=self._add_entry)
        menu.add_separator()
        # Copy system
        def copy_system():
            val = node.get('system') or ''
            if pyperclip:
                pyperclip.copy(val)
        menu.add_command(label='Kopiuj nazwę Systemu', command=copy_system)
        # Copy object
        obj = node.get('station') or node.get('body')
        if obj:
            menu.add_command(label='Kopiuj Obiekt', command=lambda: pyperclip.copy(obj) if pyperclip else None)
        # Copy coords
        coord = node.get('coords')
        if coord:
            menu.add_command(label='Kopiuj Współrzędne', command=lambda: pyperclip.copy(coord) if pyperclip else None)
        menu.add_separator()
        # Prowadź do (kopiuj automatycznie)
        def set_travel_target():
            target = node.get("system")
            try:
                setattr(self.app.state, "next_travel_target", target)
            except Exception:
                pass
            _copy_to_clipboard(target)
            try:
                powiedz("Cel podróży ustawiony", self.app)
            except Exception:
                pass
        menu.add_command(label='Prowadź do (kopiuj automatycznie)', command=set_travel_target)
        menu.add_separator()
        # Fast jump
        menu.add_command(label='🚀 PROWADŹ DO (Spansh/Schowek)', command=copy_system)
        # Edit entry
        def edit_entry():
            dlg = AddEntryDialog(self,
                system=node.get('system'), body=node.get('body'), coords=node.get('coords')
            )
            dlg.entry_title.insert(0, node.get('title',''))
            dlg.text_content.insert('1.0', node.get('content',''))
            self.wait_window(dlg)
            res = getattr(dlg, 'result_data', None)
            if res:
                node.update({
                    'title': res['title'],
                    'content': res['content'],
                    'system': res['system'],
                    'body': res['body'],
                    'coords': res['coords']
                })
                self.manager.save()
                self.refresh_tree()
        menu.add_command(label='Edytuj wpis', command=edit_entry)
        # Delete entry
        def delete_entry():
            self.manager.delete_node(uuid)
            self.refresh_tree()
        menu.add_command(label='Usuń wpis', command=delete_entry)
        menu.tk_popup(event.x_root, event.y_root)

    def _get_smart_context(self):
        state = getattr(self.app, 'state', None)
        system = getattr(state, 'current_system', None) or '-'
        if getattr(state, 'current_station', None):
            body = state.current_station
        elif getattr(state, 'current_body', None):
            body = state.current_body
        else:
            body = '-'
        lat = getattr(state, 'latitude', None)
        lon = getattr(state, 'longitude', None)
        if lat is not None and lon is not None:
            coords = f'Lat: {lat}, Lon: {lon}'
        else:
            coords = '-'
        return system, body, coords
