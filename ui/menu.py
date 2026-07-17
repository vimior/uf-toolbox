# -*- coding: utf-8 -*-
"""Navbar-style menu bar with theme-aware colors."""
import os
import sys
import tkinter as tk
from common.state import AppState
from common.common import FONT_FAMILY, logger
from plugins.manager import PluginManager
from tools.manager import ToolManager

MENU_ACTIVEBORDERWIDTH = 3

_icon_cache = {}

def _load_icon(filename, size=44):
    """Load a PNG icon from icons/. Results are cached."""
    if filename in _icon_cache:
        return _icon_cache[filename]
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(base, 'icons', filename)
    if not os.path.exists(path):
        return None
    try:
        img = tk.PhotoImage(file=path)
        img = img.subsample(img.width() // size, img.height() // size)
    except Exception:
        try:
            from PIL import Image, ImageTk
            img = ImageTk.PhotoImage(Image.open(path).resize((size, size), Image.LANCZOS))
        except ImportError:
            return None
    _icon_cache[filename] = img
    return img


class MenuUI(AppState, tk.Tk):
    """Navbar with tab-style buttons."""

    def init(self):
        self._pm = PluginManager(logger)
        self._tm = ToolManager(logger)
        super().init()
        # Listen for one-shot auto-start signal (emitted once by UFToolBox
        # after the main window is fully ready).
        def _on_auto_start():
            self._load_plugins()
            for h in self._pm.plugins.values():
                if h.auto_start and not h.alive:
                    self._show_plugin_window(h)
            self.off('auto-start-plugins', _on_auto_start)
        self.on('auto-start-plugins', _on_auto_start)

    # ---- helpers ----

    @staticmethod
    def _destroy_submenus(menu):
        """Recursively destroy all cascade submenus of *menu*."""
        for child in list(menu.winfo_children()):
            if isinstance(child, tk.Menu):
                MenuUI._destroy_submenus(child)
                child.destroy()

    # ---- build ----

    def _build_menu(self):
        t, l = self.theme, self.lang
        self._theme_var = tk.StringVar(value=getattr(self, '_current_theme_name', 'dark'))
        self._lang_var = tk.StringVar(value=getattr(self, '_current_lang_name', ''))
        self._topmost_var = tk.BooleanVar(value=self.always_on_top)
        self._auto_hide_var = tk.BooleanVar(value=self.auto_hide_enabled)

        self._navbar = bar = tk.Frame(self, bg=t['navbar_bg'], height=48)
        bar.pack(fill=tk.X, side=tk.TOP)
        bar.pack_propagate(False)

        self._nav_items = {}
        self._nav_menus = {}

        # Brand icon — fixed width
        icon_img = _load_icon('uf_toolbox.ico', size=32) or _load_icon('uf_toolbox.png', size=44)
        if icon_img is not None:
            self._brand_icon = icon_img
            brand_frame = tk.Frame(bar, bg=t['navbar_bg'], width=52, height=48)
            brand_frame.pack(side=tk.LEFT, fill=tk.Y)
            brand_frame.pack_propagate(False)
            self._brand_icon_lbl = tk.Label(brand_frame, image=icon_img, bg=t['navbar_bg'])
            self._brand_icon_lbl.place(relx=0.5, rely=0.5, anchor=tk.CENTER)
            self._brand_lbl = brand_frame
        else:
            brand = tk.Label(bar, text='  UF Toolbox', bg=t['navbar_bg'], fg=t['fg'],
                             font=(FONT_FAMILY, 10, 'bold'), padx=16)
            brand.pack(side=tk.LEFT, fill=tk.Y)
            self._brand_lbl = brand
        tk.Frame(bar, bg=t['nav_sep'], width=1).pack(side=tk.LEFT, fill=tk.Y)

        self._add_nav_item(bar, 'settings', l['menu_settings'],
                           self._build_settings_menu, t, first=True)
        self._add_nav_item(bar, 'system', l['menu_system'],
                           lambda m: self._build_tools_menu(m, 'system'), t,
                           on_click=lambda e: self._on_tools_menu_open(e, 'system'))
        self._add_nav_item(bar, 'tools', l['menu_tools'],
                           lambda m: self._build_tools_menu(m, 'tools'), t,
                           on_click=lambda e: self._on_tools_menu_open(e, 'tools'))
        self._add_nav_item(bar, 'plugins', l['menu_plugins'],
                           self._build_plugins_menu, t,
                           on_click=self._on_plugins_menu_open)

        # Separator right after plugins, packed LEFT so it hugs the button
        self._exit_sep = tk.Frame(bar, bg=t['nav_sep'], width=1)
        self._exit_sep.pack(side=tk.LEFT, fill=tk.Y)

        # Exit icon — swaps image on hover
        x_img = _load_icon('uf_toolbox_close.png')
        x_hover = _load_icon('uf_toolbox_close_hover.png')
        if x_img is not None:
            self._exit_icon = x_img
            self._exit_icon_hover = x_hover
            btn = tk.Label(bar, image=x_img, bg=t['navbar_bg'], padx=10,
                           cursor='hand2', borderwidth=0, highlightthickness=0)
            btn.bind('<Enter>', lambda e, b=btn: b.config(image=x_hover))
            btn.bind('<Leave>', lambda e, b=btn: b.config(image=x_img))
        else:
            btn = tk.Label(bar, text='  ✕  ', bg=t['navbar_bg'], fg=t['fg'],
                           font=(FONT_FAMILY, 10, 'bold'), padx=16,
                           cursor='hand2', borderwidth=0, highlightthickness=0)
        btn.pack(side=tk.RIGHT, fill=tk.Y)
        btn.bind('<Button-1>', lambda e: self.destroy())
        self._exit_btn = btn

        # Make the navbar (and its non-clickable children) a drag handle.
        self._enable_drag(bar)

        self._nav_sep = tk.Frame(self, height=2, bg=t['separator2'])
        self._nav_sep.pack(fill=tk.X, side=tk.TOP)
        self._first_focus_out = True
        self.bind('<FocusOut>', self._on_focus_out)
        self._fit_window()

    def apply_theme(self, t):
        self.configure(bg=t['bg'])
        self._navbar.config(bg=t['navbar_bg'])
        self._nav_sep.config(bg=t['separator2'])
        self._exit_sep.config(bg=t['nav_sep'])
        self._brand_lbl.config(bg=t['navbar_bg'])
        if hasattr(self, '_brand_icon_lbl'):
            self._brand_icon_lbl.config(bg=t['navbar_bg'])
        if isinstance(self._brand_lbl, tk.Label):
            self._brand_lbl.config(fg=t['fg'])
        if hasattr(self, '_exit_icon_hover'):
            self._exit_btn.config(image=self._exit_icon, bg=t['navbar_bg'])
            self._exit_btn.unbind('<Enter>')
            self._exit_btn.unbind('<Leave>')
            self._exit_btn.bind('<Enter>', lambda e, b=self._exit_btn: b.config(image=self._exit_icon_hover))
            self._exit_btn.bind('<Leave>', lambda e, b=self._exit_btn: b.config(image=self._exit_icon))
        for key, widget in self._nav_items.items():
            if key.endswith('_sep'):
                widget.config(bg=t['nav_sep'])
            else:
                widget.config(bg=t['navbar_bg'], fg=t['fg'])
                widget.unbind('<Enter>')
                widget.unbind('<Leave>')
                widget.bind('<Enter>', lambda e, b=widget, h=t['nav_hover_bg']: b.config(bg=h))
                widget.bind('<Leave>', lambda e, b=widget, bg=t['navbar_bg'], c=t['fg']: b.config(bg=bg, fg=c))
        for menu in self._nav_menus.values():
            menu.config(bg=t['menu_bg'], fg=t['fg'],
                        activebackground=t['menu_hover_bg'], activeforeground=t['menu_hover_fg'])

    def _add_nav_item(self, bar, key, text, menu_builder, t,
                       on_click=None, first=False):
        if not first:
            frm = tk.Frame(bar, bg=t['nav_sep'], width=1)
            frm.pack(side=tk.LEFT, fill=tk.Y)
            self._nav_items[f'{key}_sep'] = frm

        btn = tk.Label(bar, text=f'  {text}  ', bg=t['navbar_bg'], fg=t['fg'],
                       font=(FONT_FAMILY, 12), padx=16,
                       cursor='hand2', borderwidth=0, highlightthickness=0)
        btn.pack(side=tk.LEFT, fill=tk.Y)

        btn.bind('<Enter>', lambda e, b=btn, h=t['nav_hover_bg']: b.config(bg=h))
        btn.bind('<Leave>', lambda e, b=btn, bg=t['navbar_bg'], c=t['fg']:
                 b.config(bg=bg, fg=c))

        self._nav_items[key] = btn

        menu = tk.Menu(self, tearoff=0, font=(FONT_FAMILY, 12),
                       bg=t['menu_bg'], fg=t['fg'],
                       activebackground=t['menu_hover_bg'],
                       activeforeground=t['menu_hover_fg'],
                       borderwidth=1, relief=tk.FLAT,
                       activeborderwidth=MENU_ACTIVEBORDERWIDTH)
        menu.configure(postcommand=lambda m=menu, k=key: self._on_menu_open(m, k))
        menu_builder(menu)
        self._nav_menus[key] = menu

        if on_click:
            btn.bind('<Button-1>',
                     lambda e, cb=on_click, m=menu, b=btn:
                     (cb(e), self._show_menu(m, b)))
        else:
            btn.bind('<Button-1>',
                     lambda e, m=menu, b=btn: self._show_menu(m, b))

    def _add_nav_action(self, bar, key, text, action, t):
        """Create a navbar button that fires *action* directly (no dropdown)."""
        frm = tk.Frame(bar, bg=t['nav_sep'], width=1)
        frm.pack(side=tk.LEFT, fill=tk.Y)
        self._nav_items[f'{key}_sep'] = frm
        btn = tk.Label(bar, text=f'  {text}  ', bg=t['navbar_bg'], fg=t['fg'],
                       font=(FONT_FAMILY, 12), padx=16,
                       cursor='hand2', borderwidth=0, highlightthickness=0)
        btn.pack(side=tk.LEFT, fill=tk.Y)
        btn.bind('<Enter>', lambda e, b=btn, h=t['nav_hover_bg']: b.config(bg=h))
        btn.bind('<Leave>', lambda e, b=btn, bg=t['navbar_bg'], c=t['fg']:
                 b.config(bg=bg, fg=c))
        btn.bind('<Button-1>', lambda e, a=action: a())
        self._nav_items[key] = btn

    def _show_menu(self, menu, btn):
        x = btn.winfo_rootx()
        y = btn.winfo_rooty() + btn.winfo_height()
        menu.tk_popup(x, y)

    # ---- menu open/close detection via grab ----

    def _on_menu_open(self, menu, key):
        if self._menu_open:
            return
        self._menu_open = True
        # Cancel any pending collapse timer (don't use _cancel_auto_hide — it resets _menu_open)
        if self._auto_hide_job is not None:
            self.after_cancel(self._auto_hide_job)
            self._auto_hide_job = None

    def _on_focus_out(self, event):
        if self._first_focus_out:
            self._first_focus_out = False
            return
        if self._collapsed and not self._menu_open:
            return
        self._menu_open = False
        if not self._collapsed and self._is_docked_at_top():
            self._auto_hide_job = self.after(1000, self._collapse_bar)

    # ---- topmost ----

    def _toggle_topmost(self, value):
        self.set_topmost(value)
        self._apply_topmost(value)

    def _apply_topmost(self, value):
        """Set -topmost on main window and known child windows."""
        self.wm_attributes('-topmost', value)
        self.lift()
        self.focus_force()

    def _toggle_auto_hide(self):
        enabled = self._auto_hide_var.get()
        self.set_auto_hide(enabled)
        if not enabled:
            # Cancelled: stop any pending collapse, expand if collapsed
            self._cancel_auto_hide()
            if self._collapsed:
                self._expand_bar()
            else:
                self.geometry(f'+{self.winfo_x()}+{self._dock_y+1}')
        else:
            # Enabled: trigger check after 3s
            self._cancel_auto_hide()
            self._auto_hide_job = self.after(3000, self._collapse_bar)

    # ---- menu builders ----

    def _build_settings_menu(self, menu):
        l = self.lang
        menu.add_cascade(label=l['menu_appearance'],
                         menu=self._build_appearance_submenu(menu))
        menu.add_cascade(label=l['menu_language'],
                         menu=self._build_language_submenu(menu))
        menu.add_checkbutton(label=l['menu_topmost'],
                             variable=self._topmost_var,
                             command=lambda: self._toggle_topmost(
                                 self._topmost_var.get()))
        menu.add_checkbutton(label=l['menu_auto_hide'],
                             variable=self._auto_hide_var,
                             command=self._toggle_auto_hide)
        menu.add_command(label=l['menu_config'],
                         command=lambda: self.emit('show-settings'))
        menu.add_separator()
        menu.add_command(label=l['menu_log'],
                         command=lambda: self.emit('show-log'))
        menu.add_command(label=l['menu_about'],
                         command=lambda: self.emit('show-about'))

    def _build_appearance_submenu(self, parent):
        l = self.lang
        t = self.theme
        sub = tk.Menu(parent, tearoff=0, font=(FONT_FAMILY, 11),
                      bg=t['menu_bg'], fg=t['fg'],
                      activebackground=t['menu_hover_bg'],
                      activeforeground=t['menu_hover_fg'],
                      activeborderwidth=MENU_ACTIVEBORDERWIDTH)
        sub.add_radiobutton(label=l['menu_theme_light'],
                            variable=self._theme_var, value='light',
                            command=lambda: self.set_theme('light'))
        sub.add_radiobutton(label=l['menu_theme_dark'],
                            variable=self._theme_var, value='dark',
                            command=lambda: self.set_theme('dark'))
        return sub

    def _build_language_submenu(self, parent):
        l = self.lang
        t = self.theme
        sub = tk.Menu(parent, tearoff=0, font=(FONT_FAMILY, 11),
                      bg=t['menu_bg'], fg=t['fg'],
                      activebackground=t['menu_hover_bg'],
                      activeforeground=t['menu_hover_fg'],
                      activeborderwidth=MENU_ACTIVEBORDERWIDTH)
        sub.add_radiobutton(label=l['menu_lang_zh'],
                            variable=self._lang_var, value='zh',
                            command=lambda: self.set_lang('zh'))
        sub.add_radiobutton(label=l['menu_lang_en'],
                            variable=self._lang_var, value='en',
                            command=lambda: self.set_lang('en'))
        sub.add_radiobutton(label=l['menu_lang_auto'],
                            variable=self._lang_var, value='auto',
                            command=lambda: self.set_lang('auto'))
        return sub

    def _build_tools_menu(self, menu, filter_key='tools'):
        if filter_key == 'system':
            self._system_menu = menu
        else:
            self._tools_menu = menu
        self._refresh_tools_menu(menu, filter_key)

    def _on_tools_menu_open(self, event, filter_key='tools'):
        self._refresh_tools_menu(
            self._system_menu if filter_key == 'system' else self._tools_menu,
            filter_key)

    def _refresh_tools_menu(self, menu=None, filter_key='tools'):
        if menu is None:
            menu = getattr(self, '_tools_menu', None) or getattr(self, '_system_menu', None)
        self._destroy_submenus(menu)
        menu.delete(0, tk.END)
        empty_key = 'menu_no_system' if filter_key == 'system' else 'menu_no_tools'
        result = self._tm.scan(self.resolved_lang, tab=filter_key, path=self.tool_path)
        if not result['tools'] and not result['groups']:
            menu.add_command(
                label=self.lang.get(empty_key, '(No Tools)'),
                state=tk.DISABLED)
            return

        def _cmd(t):
            return lambda: (self._tm.launch(t),
                            self.after(200, lambda: self.lift() or self.focus_force()))

        def _build_group(parent_menu, groups):
            t = self.theme
            for g in groups:
                sub = tk.Menu(parent_menu, tearoff=0, font=(FONT_FAMILY, 11),
                      bg=t['menu_bg'], fg=t['fg'],
                              activebackground=t['menu_hover_bg'],
                              activeforeground=t['menu_hover_fg'],
                              activeborderwidth=MENU_ACTIVEBORDERWIDTH)
                for tool in g.get('tools', []):
                    sub.add_command(label=tool['name'], command=_cmd(tool))
                _build_group(sub, g.get('groups', []))
                label = g.get('name', '')
                if sub.index(tk.END) is not None:
                    parent_menu.add_cascade(label=label, menu=sub)
                else:
                    sub.destroy()  # don't leak empty submenu

        for t in result['tools']:
            menu.add_command(label=t['name'], command=_cmd(t))
        _build_group(menu, result['groups'])

    def _build_plugins_menu(self, menu):
        self._plugins_menu = menu

    # ---- plugins ----

    def _refresh_plugins_menu(self):
        self._destroy_submenus(self._plugins_menu)
        self._plugins_menu.delete(0, tk.END)
        if not self._pm.plugins:
            self._plugins_menu.add_command(
                label=self.lang.get('menu_no_plugins', '(No Plugins)'))
            return
        l, t = self.lang, self.theme
        for p in sorted(self._pm.plugins.values(),
                        key=lambda x: x.priority, reverse=True):
            is_open = p.alive
            is_service = p.is_service
            dot = '● ' if is_open else '  '
            name = p.get_name(self.current_lang_name)

            if not is_open:
                # Plain command — click to start/open
                self._plugins_menu.add_command(
                    label=f'{dot}{name}',
                    command=lambda plugin=p: self._show_plugin_window(plugin))
            elif is_service:
                # ServicePlugin running: submenu with Stop
                sub = tk.Menu(self._plugins_menu, tearoff=0, font=(FONT_FAMILY, 11),
                              bg=t['menu_bg'], fg=t['fg'],
                              activebackground=t['menu_hover_bg'],
                              activeforeground=t['menu_hover_fg'],
                              activeborderwidth=MENU_ACTIVEBORDERWIDTH)
                sub.add_command(
                    label=l.get('menu_service_stop', 'Stop'),
                    command=lambda plugin=p: self._close_plugin_window(plugin))
                self._plugins_menu.add_cascade(label=f'{dot}{name}', menu=sub)
            elif p.reload:
                # GUI reload=True: plain command — click to focus
                self._plugins_menu.add_command(
                    label=f'{dot}{name}',
                    command=lambda plugin=p: self._show_plugin_window(plugin))
            else:
                # GUI reload=False: submenu with Open / Close
                sub = tk.Menu(self._plugins_menu, tearoff=0, font=(FONT_FAMILY, 11),
                              bg=t['menu_bg'], fg=t['fg'],
                              activebackground=t['menu_hover_bg'],
                              activeforeground=t['menu_hover_fg'],
                              activeborderwidth=MENU_ACTIVEBORDERWIDTH)
                sub.add_command(
                    label=l.get('menu_plugin_open', 'Open / Restore'),
                    command=lambda plugin=p: self._show_plugin_window(plugin))
                sub.add_command(
                    label=l.get('menu_plugin_close', 'Close Window'),
                    command=lambda plugin=p: self._close_plugin_window(plugin))
                self._plugins_menu.add_cascade(label=f'{dot}{name}', menu=sub)

    def _on_plugins_menu_open(self, event):
        self._load_plugins()
        self._refresh_plugins_menu()

    def _load_plugins(self):
        """Resolve plugin directories and delegate to PluginManager."""
        if getattr(sys, 'frozen', False):
            plugin_dirs = [os.path.join(sys._MEIPASS, 'plugins')]
            base = os.path.dirname(sys.executable)
            plugin_path = os.path.join(base, 'plugins')
            if os.path.isdir(plugin_path):
                if base not in sys.path:
                    sys.path.insert(0, base)
                if plugin_path not in plugin_dirs:
                    plugin_dirs.append(plugin_path)
            if self.plugin_path and self.plugin_path != 'plugins':
                plugin_path = os.path.join(base, self.plugin_path)
                if os.path.isdir(plugin_path):
                    root = os.path.dirname(plugin_path)
                    if root not in sys.path:
                        sys.path.insert(0, root)
                    if plugin_path not in plugin_dirs:
                        plugin_dirs.append(plugin_path)
        else:
            base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            plugin_dirs = [
                os.path.join(base, 'plugins'),
                os.path.join(base, 'dist', 'plugins'),
            ]
            if self.plugin_path and self.plugin_path != 'plugins':
                other_plugin_path = os.path.join(base, 'dist', self.plugin_path)
                if other_plugin_path != plugin_dirs[1]:
                    plugin_dirs.append(other_plugin_path)
        self._pm.load(self, plugin_dirs)

    # ---- plugin window ----

    def _show_plugin_window(self, plugin):
        try:
            was_loaded = plugin.loaded
            was_open = plugin.alive
            win = plugin.start(self)
            if win is not None:
                if not was_open:
                    # New window — set up position, icon, transient once
                    if self.always_on_top:
                        win.tk.call('wm', 'transient', str(win), '')
                    if plugin.fixed_position or plugin.fixed_size:
                        self.emit('set-win-position', win,
                            x=(self.winfo_x() + self.winfo_width() + 4
                               if plugin.fixed_position else None),
                            y=(self.winfo_y() if plugin.fixed_position else None),
                            w=(420 if plugin.fixed_size else None),
                            h=(self.main_height if plugin.fixed_size else None),
                            fixed_size=plugin.fixed_size,
                            fixed_position=plugin.fixed_position)
                    if plugin.use_app_icon:
                        self.emit('set-win-icon', win)
            # If plugin was just lazy-loaded, refresh menu to show real name/priority
            if not was_loaded and plugin.loaded:
                self._refresh_plugins_menu()
        except Exception as e:
            logger.error(f'[Plugin:{plugin.get_name(self.current_lang_name)}] show error, {str(e)}')

    def _close_plugin_window(self, plugin):
        """Explicitly destroy a plugin window from the menu."""
        try:
            plugin.stop()
        except Exception as e:
            logger.error(f'[Plugin:{plugin.get_name(self.current_lang_name)}] close error, {str(e)}')
        finally:
            self._refresh_plugins_menu()

    # ---- theme / lang ----

    def _apply_lang(self, l, t=None):
        self.title(l['window_title'])
        if isinstance(self._brand_lbl, tk.Label):
            self._brand_lbl.config(text=f'  {l["window_title"]}')
        self._nav_items['settings'].config(
            text=f'  {l["menu_settings"]}  ')
        self._nav_items['system'].config(
            text=f'  {l["menu_system"]}  ')
        self._nav_items['tools'].config(
            text=f'  {l["menu_tools"]}  ')
        self._nav_items['plugins'].config(
            text=f'  {l["menu_plugins"]}  ')
        # Rebuild settings submenus (theme + language labels)
        if 'settings' in self._nav_menus:
            m = self._nav_menus['settings']
            self._destroy_submenus(m)
            m.delete(0, tk.END)
            self._build_settings_menu(m)
        self._theme_var.set(getattr(self, '_current_theme_name', 'dark'))
        self._lang_var.set(getattr(self, '_current_lang_name', 'en'))
        self._refresh_plugins_menu()
        if hasattr(self, '_system_menu'):
            self._refresh_tools_menu(self._system_menu, 'system')
        if hasattr(self, '_tools_menu'):
            self._refresh_tools_menu(self._tools_menu, 'tools')
        self._fit_window()

    def _enable_drag(self, widget):
        """Make the borderless window draggable by grabbing *widget* and any
        descendant that has no click handler of its own (the brand icon,
        separators and empty navbar space). Menu buttons and the exit button
        keep their own <Button-1> bindings and are skipped."""
        self._collapsed = False
        self._normal_height = None
        self._auto_hide_job = None
        self._color_job = None
        self._menu_open = False

        def _start(event):
            self._cancel_auto_hide()
            self._drag_x = event.x_root - self.winfo_x()
            self._drag_y = event.y_root - self.winfo_y()
            self._was_dragged = False

        def _move(event):
            # Expand if collapsed and user starts dragging
            if self._collapsed:
                self._expand_bar()
            x = event.x_root - self._drag_x
            y = event.y_root - self._drag_y
            self.geometry(f'+{x}+{y}')
            self._was_dragged = True

        def _release(event):
            if self._was_dragged:
                self._check_auto_hide()

        def _bind(w):
            if not w.bind('<Button-1>'):
                w.bind('<Button-1>', _start)
                w.bind('<B1-Motion>', _move)
                w.bind('<ButtonRelease-1>', _release)
            for child in w.winfo_children():
                _bind(child)

        _bind(widget)

    def _fit_window(self):
        self._navbar.update_idletasks()
        w = sum(c.winfo_reqwidth() for c in self._navbar.winfo_children()) + 4
        h = self._navbar.winfo_reqheight() + 2
        x = (self.winfo_screenwidth() - w) // 2
        # On Linux DEs (GNOME, KDE) the top panel takes ~28px; y=1 hides the window behind it
        y = 1 if sys.platform == 'win32' else 28
        self._dock_y = y - 1
        self.geometry(f'{w}x{h}+{x}+{y}')
        self.set_main_width(w)
        self._normal_height = h

    # ---- auto-hide at screen top ----

    @property
    def _auto_hide_threshold(self):
        """y threshold for auto-hide: dock_y (panel-aware) + 2px tolerance."""
        return getattr(self, '_dock_y', 1) + 2

    def _is_docked_at_top(self):
        return self.winfo_y() <= self._auto_hide_threshold

    def _check_auto_hide(self):
        """If window is docked at screen top, auto-collapse after a short delay."""
        if not self.auto_hide_enabled:
            return
        if self._auto_hide_job is not None:
            self.after_cancel(self._auto_hide_job)
            self._auto_hide_job = None
        if self._collapsed:
            return
        if self._is_docked_at_top() and not self._menu_open:
            self._auto_hide_job = self.after(500, self._collapse_bar)

    def _collapse_bar(self):
        """Shrink to a thin line at screen top."""
        if not self.auto_hide_enabled or self._collapsed or not self._is_docked_at_top():
            return
        self._collapsed = True
        self._normal_height = self.winfo_height()
        w = self.winfo_width()
        y = getattr(self, '_dock_y', 0)
        self.geometry(f'{w}x3+{self.winfo_x()}+{y}')
        # Hide navbar, show a glowing accent line
        self._navbar.pack_forget()
        self._nav_sep.pack_forget()
        self.configure(bg='#ff6600')
        self.bind('<Enter>', self._on_collapsed_enter)

    def _on_collapsed_enter(self, event):
        """Mouse entered the collapsed bar — expand back."""
        self._expand_bar()

    def _expand_bar(self):
        """Restore full height."""
        if not self._collapsed:
            return
        self._collapsed = False
        self.unbind('<Enter>')
        self.unbind('<Leave>')
        # Restore navbar
        self._navbar.pack(fill=tk.X, side=tk.TOP)
        self._nav_sep.pack(fill=tk.X, side=tk.TOP)
        h = self._normal_height or self._navbar.winfo_reqheight() + 2
        w = self.winfo_width()
        x = self.winfo_x()
        y = getattr(self, '_dock_y', 0)
        if not self.auto_hide_enabled:
            y += 1
        self.geometry(f'{w}x{h}+{x}+{y}')
        self.set_main_width(w)
        self.configure(bg=self.theme['bg'])
        # Cancel pending re-collapse on re-entry; re-collapse on leave
        self.bind('<Enter>', self._cancel_auto_hide)  # FIXME: triggers on inter-child moves
        self.bind('<Leave>', self._on_expanded_leave)

    def _cancel_auto_hide(self, event=None):
        """Cancel any pending collapse timer."""
        if self._menu_open and not event:
            self._menu_open = False
        if self._auto_hide_job is not None:
            self.after_cancel(self._auto_hide_job)
            self._auto_hide_job = None

    def _on_expanded_leave(self, event):
        """Mouse left the expanded bar — collapse after delay, with pointer check."""
        if self._collapsed or not self._is_docked_at_top() or self._menu_open:
            return
        # Delay the check to avoid flicker from rapid enter/leave at screen edge
        self._auto_hide_job = self.after(500, self._collapse_if_pointer_gone)

    def _collapse_if_pointer_gone(self):
        """Only collapse if the mouse is actually outside the bar."""
        if self._collapsed:
            return
        py = self.winfo_pointery()
        bar_top = self.winfo_y()
        bar_bottom = bar_top + self.winfo_height() + 2  # small grace margin
        if bar_top <= py <= bar_bottom:
            self.bind('<Leave>', self._on_expanded_leave)
            return
        self._collapse_bar()

    @staticmethod
    def _dispatch(method_name, self, *args):
        for cls in type(self).__mro__:
            if method_name in cls.__dict__:
                cls.__dict__[method_name](self, *args)

    def set_theme(self, name=None):
        if name is not None:
            AppState.set_theme(self, name)
        self._dispatch('apply_theme', self, self.theme)

    def set_lang(self, name=None):
        if name is not None:
            AppState.set_lang(self, name)
        self._apply_lang(self.lang, self.theme)
        self.after(50, lambda: self._dispatch('apply_lang', self, self.lang, self.theme))
        # self._dispatch('apply_lang', self, self.lang, self.theme)
