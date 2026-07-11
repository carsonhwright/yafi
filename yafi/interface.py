import json
import queue
import subprocess
import sys
import threading
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import messagebox, scrolledtext, ttk

import yfinance as yf

QUOTE_TYPE_MAP = {
    'equity': yf.EquityQuery,
    'fund': yf.FundQuery,
    'etf': yf.ETFQuery,
}

PROBE_OPERAND = {
    'equity': ('intradaymarketcap', 1),
    'fund': ('initialinvestment', 1),
    'etf': ('initialinvestment', 1),
}

COMPARISON_OPERATORS = ['eq', 'gt', 'lt', 'gte', 'lte', 'btwn', 'is-in']

VALUE_FIELDS = ['Open', 'High', 'Low', 'Close', 'Volume']

COMMON_OUTPUT_FIELDS = [
    'symbol', 'shortName', 'longName', 'exchange', 'fullExchangeName', 'currency',
    'quoteType', 'marketState', 'regularMarketPrice', 'regularMarketChange',
    'regularMarketChangePercent', 'regularMarketVolume', 'marketCap', 'trailingPE',
    'forwardPE', 'epsTrailingTwelveMonths', 'epsForward', 'dividendRate', 'dividendYield',
    'fiftyTwoWeekHigh', 'fiftyTwoWeekLow', 'fiftyDayAverage', 'twoHundredDayAverage',
    'averageAnalystRating', 'bookValue', 'priceToBook', 'sharesOutstanding',
]

CONFIGS_DIR = Path(__file__).parent / 'configs'


def flatten_valid_values(vv):
    if isinstance(vv, dict):
        return sorted(set().union(*vv.values()))
    return sorted(vv)


def query_metadata(quote_type):
    cls = QUOTE_TYPE_MAP[quote_type]
    field, value = PROBE_OPERAND[quote_type]
    probe = cls('gt', [field, value])
    fields = set()
    for names in probe.valid_fields.values():
        fields.update(names)
    valid_values = {field: flatten_valid_values(vv) for field, vv in probe.valid_values.items()}
    return sorted(fields), valid_values


def list_config_filenames():
    if not CONFIGS_DIR.exists():
        return []
    return sorted(p.name for p in CONFIGS_DIR.glob('*.json'))


class AutocompleteCombobox(ttk.Combobox):
    def __init__(self, master=None, values=(), match='contains', **kwargs):
        super().__init__(master, **kwargs)
        self._all_values = list(values)
        self._match = match
        self['values'] = self._all_values
        self.bind('<KeyRelease>', self._on_keyrelease)
        self._slow_down_dropdown_scroll()

    def set_values(self, values):
        self._all_values = list(values)
        self['values'] = self._all_values

    def _slow_down_dropdown_scroll(self):
        # ttk's default popdown listbox binding scrolls 3-4 lines per wheel notch; force 1.
        listbox = self.tk.eval(f'ttk::combobox::PopdownWindow {self}') + '.f.l'
        callback = self.register(lambda delta: self.tk.call(
            listbox, 'yview', 'scroll', -1 if int(delta) >= 0 else 1, 'units'))
        self.tk.call('bind', listbox, '<MouseWheel>', f'{callback} %D; break')

    def _on_keyrelease(self, event):
        if event.keysym in ('Up', 'Down', 'Left', 'Right', 'Return', 'Escape', 'Tab'):
            return
        typed = self.get().lower()
        if not typed:
            self['values'] = self._all_values
            return
        if self._match == 'startswith':
            filtered = [v for v in self._all_values if v.lower().startswith(typed)]
        else:
            filtered = [v for v in self._all_values if typed in v.lower()]
        self['values'] = filtered or self._all_values


class ConfigBuilderApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('yafi query config builder')
        self.geometry('900x700')

        self.conditions = []
        self.current_group = None
        self.output_fields = []
        self.query_fields = []
        self.valid_values = {}
        self._value_widgets = {}

        self.quote_type = tk.StringVar(value='equity')
        self.combinator = tk.StringVar(value='and')
        self.group_combinator = tk.StringVar(value='or')
        self.sort_asc = tk.BooleanVar(value=False)
        self.output_format = tk.StringVar(value='json')
        self.plot_value_field_vars = {field: tk.BooleanVar(value=(field == 'Close')) for field in VALUE_FIELDS}
        self._dash_process = None

        self._build_widgets()
        self._on_quote_type_change()
        self._refresh_filename_choices()
        self.protocol('WM_DELETE_WINDOW', self._on_close)

    def _on_close(self):
        if self._dash_process is not None:
            self._dash_process.terminate()
        self.destroy()

    def _refresh_filename_choices(self):
        self.filename_entry.set_values(list_config_filenames())

    def _build_widgets(self):
        pad = {'padx': 6, 'pady': 4}

        canvas = tk.Canvas(self, highlightthickness=0)
        scrollbar = ttk.Scrollbar(self, orient='vertical', command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side='right', fill='y')
        canvas.pack(side='left', fill='both', expand=True)

        content = ttk.Frame(canvas)
        content_window = canvas.create_window((0, 0), window=content, anchor='nw')
        content.bind('<Configure>', lambda e: canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.bind('<Configure>', lambda e: canvas.itemconfig(content_window, width=e.width))

        def _on_mousewheel(event):
            canvas.yview_scroll(-1 if event.delta > 0 else 1, 'units')
        canvas.bind('<Enter>', lambda e: canvas.bind_all('<MouseWheel>', _on_mousewheel))
        canvas.bind('<Leave>', lambda e: canvas.unbind_all('<MouseWheel>'))

        top = ttk.Frame(content)
        top.pack(fill='x', **pad)
        ttk.Label(top, text='quote_type:').pack(side='left')
        quote_type_box = ttk.Combobox(top, textvariable=self.quote_type, values=list(QUOTE_TYPE_MAP),
                                       state='readonly', width=10)
        quote_type_box.pack(side='left', padx=(4, 20))
        quote_type_box.bind('<<ComboboxSelected>>', lambda e: self._on_quote_type_change())

        ttk.Label(top, text='combine conditions with:').pack(side='left')
        ttk.Radiobutton(top, text='AND', variable=self.combinator, value='and').pack(side='left')
        ttk.Radiobutton(top, text='OR', variable=self.combinator, value='or').pack(side='left')

        cond_frame = ttk.LabelFrame(content, text='Conditions (query)')
        cond_frame.pack(fill='x', **pad)

        add_row = ttk.Frame(cond_frame)
        add_row.pack(fill='x', **pad)

        ttk.Label(add_row, text='Field:').grid(row=0, column=0, sticky='w')
        self.field_box = AutocompleteCombobox(add_row, width=38)
        self.field_box.grid(row=0, column=1, padx=4)
        self.field_box.bind('<<ComboboxSelected>>', lambda e: self._on_field_or_operator_change())
        self.field_box.bind('<KeyRelease>', self._on_field_keyrelease)

        ttk.Label(add_row, text='Operator:').grid(row=0, column=2, sticky='w')
        self.operator_box = ttk.Combobox(add_row, values=COMPARISON_OPERATORS, state='readonly', width=8)
        self.operator_box.current(1)
        self.operator_box.grid(row=0, column=3, padx=4)
        self.operator_box.bind('<<ComboboxSelected>>', lambda e: self._on_field_or_operator_change())

        ttk.Label(add_row, text='Value(s):').grid(row=1, column=0, sticky='nw', pady=(6, 0))
        self.value_container = ttk.Frame(add_row)
        self.value_container.grid(row=1, column=1, columnspan=3, sticky='w', pady=(6, 0))

        ttk.Button(cond_frame, text='Add condition', command=self._add_condition).pack(anchor='e', padx=6)

        group_row = ttk.Frame(cond_frame)
        group_row.pack(fill='x', padx=6, pady=(4, 0))
        ttk.Label(group_row, text='New group logic:').pack(side='left')
        ttk.Radiobutton(group_row, text='AND', variable=self.group_combinator, value='and').pack(side='left')
        ttk.Radiobutton(group_row, text='OR', variable=self.group_combinator, value='or').pack(side='left')
        ttk.Button(group_row, text='Start group', command=self._start_group).pack(side='left', padx=(10, 4))
        ttk.Button(group_row, text='End group', command=self._end_group).pack(side='left')
        self.group_status_label = ttk.Label(group_row, text='Adding to: top level', foreground='#666')
        self.group_status_label.pack(side='left', padx=(10, 0))
        ttk.Label(cond_frame, text='A group is a nested (AND) or (OR) of conditions, e.g. exchange=NYQ AND '
                                    '(industry=Advertising OR industry=Aerospace). Groups hold plain conditions '
                                    'only, not further nested groups.', foreground='#666', wraplength=760,
                  justify='left').pack(anchor='w', padx=6, pady=(2, 0))

        self.cond_tree = ttk.Treeview(cond_frame, columns=('operator', 'field', 'values'),
                                       show='tree headings', height=8)
        self.cond_tree.heading('#0', text='')
        self.cond_tree.column('#0', width=90)
        for col, width in (('operator', 70), ('field', 230), ('values', 340)):
            self.cond_tree.heading(col, text=col)
            self.cond_tree.column(col, width=width)
        self.cond_tree.pack(fill='x', padx=6, pady=(4, 0))
        ttk.Button(cond_frame, text='Remove selected', command=self._remove_condition).pack(anchor='e', padx=6, pady=4)

        settings_frame = ttk.LabelFrame(content, text='Sort / pagination')
        settings_frame.pack(fill='x', **pad)

        ttk.Label(settings_frame, text='sort_field:').grid(row=0, column=0, sticky='w')
        self.sort_field_box = AutocompleteCombobox(settings_frame, width=38)
        self.sort_field_box.grid(row=0, column=1, padx=4)
        ttk.Checkbutton(settings_frame, text='sort_asc', variable=self.sort_asc).grid(row=0, column=2, padx=10)

        ttk.Label(settings_frame, text='page_size:').grid(row=1, column=0, sticky='w', pady=(6, 0))
        self.page_size_entry = ttk.Spinbox(settings_frame, from_=1, to=250, width=8)
        self.page_size_entry.set(250)
        self.page_size_entry.grid(row=1, column=1, sticky='w', padx=4, pady=(6, 0))

        ttk.Label(settings_frame, text='max_results (blank = all):').grid(row=1, column=2, sticky='w', pady=(6, 0))
        self.max_results_entry = ttk.Entry(settings_frame, width=10)
        self.max_results_entry.grid(row=1, column=3, sticky='w', padx=4, pady=(6, 0))

        ttk.Label(settings_frame, text='request_delay_seconds:').grid(row=2, column=0, sticky='w', pady=(6, 0))
        self.delay_entry = ttk.Entry(settings_frame, width=10)
        self.delay_entry.insert(0, '0.5')
        self.delay_entry.grid(row=2, column=1, sticky='w', padx=4, pady=(6, 0))

        fields_frame = ttk.LabelFrame(
            content, text='Output fields (response keys kept in results.json - different from query fields above)')
        fields_frame.pack(fill='x', **pad)

        fields_add_row = ttk.Frame(fields_frame)
        fields_add_row.pack(fill='x', padx=6, pady=4)
        self.output_field_box = AutocompleteCombobox(fields_add_row, values=COMMON_OUTPUT_FIELDS, width=38)
        self.output_field_box.pack(side='left')
        ttk.Button(fields_add_row, text='Add field', command=self._add_output_field).pack(side='left', padx=6)
        ttk.Label(fields_add_row, text='(leave empty to keep every field Yahoo returns)').pack(side='left', padx=6)

        self.fields_listbox = tk.Listbox(fields_frame, height=5)
        self.fields_listbox.pack(fill='x', padx=6)
        ttk.Button(fields_frame, text='Remove selected', command=self._remove_output_field).pack(anchor='e', padx=6, pady=4)

        output_frame = ttk.LabelFrame(content, text='Output')
        output_frame.pack(fill='x', **pad)
        ttk.Label(output_frame, text='format:').grid(row=0, column=0, sticky='w')
        ttk.Combobox(output_frame, textvariable=self.output_format, values=['json', 'csv', 'both'],
                     state='readonly', width=8).grid(row=0, column=1, sticky='w', padx=4)
        ttk.Label(output_frame, text='path:').grid(row=0, column=2, sticky='w')
        self.output_path_entry = ttk.Entry(output_frame, width=40)
        self.output_path_entry.insert(0, 'output/results.json')
        self.output_path_entry.grid(row=0, column=3, sticky='w', padx=4)

        ttk.Label(output_frame, text='plot value_field(s):').grid(row=1, column=0, sticky='w', pady=(6, 0))
        plot_fields_row = ttk.Frame(output_frame)
        plot_fields_row.grid(row=1, column=1, columnspan=3, sticky='w', pady=(6, 0))
        for field in VALUE_FIELDS:
            ttk.Checkbutton(plot_fields_row, text=field, variable=self.plot_value_field_vars[field]
                             ).pack(side='left', padx=(0, 10))
        ttk.Label(output_frame, text='(what ticker_time.py/the live dashboard plots; check 2+ to plot them '
                                      'together on one chart, each with its own color-matched axis)').grid(
            row=2, column=0, columnspan=4, sticky='w', pady=(2, 0))

        file_frame = ttk.LabelFrame(content, text=f'Save to {CONFIGS_DIR}')
        file_frame.pack(fill='x', **pad)
        ttk.Label(file_frame, text='filename:').pack(side='left', padx=(6, 4))
        self.filename_entry = AutocompleteCombobox(file_frame, width=28, match='startswith')
        self.filename_entry.insert(0, 'my_query.json')
        self.filename_entry.bind('<Button-1>', lambda e: self._refresh_filename_choices())
        self.filename_entry.pack(side='left')
        ttk.Button(file_frame, text='Load', command=self._load_config).pack(side='left', padx=6)
        ttk.Button(file_frame, text='Preview', command=self._refresh_preview).pack(side='left', padx=6)
        ttk.Button(file_frame, text='Save', command=self._save_config).pack(side='left', padx=6)

        preview_frame = ttk.LabelFrame(content, text='Preview')
        preview_frame.pack(fill='both', expand=True, **pad)
        self.preview_text = scrolledtext.ScrolledText(preview_frame, height=10, wrap='none')
        self.preview_text.pack(fill='both', expand=True)

        run_frame = ttk.LabelFrame(content, text='Run')
        run_frame.pack(fill='both', **pad)
        run_buttons_row = ttk.Frame(run_frame)
        run_buttons_row.pack(fill='x', padx=6, pady=4)
        self.run_button = ttk.Button(run_buttons_row, text='Save & run query_machine.py', command=self._run_query_machine)
        self.run_button.pack(side='left')
        self.plot_button = ttk.Button(run_buttons_row, text='Launch live dashboard (ticker_time.py, dash)',
                                       command=self._plot_with_ticker_time)
        self.plot_button.pack(side='left', padx=(8, 0))
        self.run_output = scrolledtext.ScrolledText(run_frame, height=8, wrap='word', state='disabled')
        self.run_output.pack(fill='both', expand=True, padx=6, pady=(0, 6))

    def _on_field_keyrelease(self, event):
        AutocompleteCombobox._on_keyrelease(self.field_box, event)
        self._on_field_or_operator_change()

    def _on_quote_type_change(self):
        quote_type = self.quote_type.get()
        try:
            self.query_fields, self.valid_values = query_metadata(quote_type)
        except Exception as exc:
            messagebox.showerror('Failed to load field metadata', str(exc))
            self.query_fields, self.valid_values = [], {}
        self.field_box.set_values(self.query_fields)
        self.sort_field_box.set_values(self.query_fields)
        self._on_field_or_operator_change()

    def _on_field_or_operator_change(self):
        for widget in self.value_container.winfo_children():
            widget.destroy()

        field = self.field_box.get().strip()
        operator = self.operator_box.get()
        constrained_values = self.valid_values.get(field)

        if operator == 'btwn':
            ttk.Label(self.value_container, text='low:').pack(side='left')
            low = ttk.Entry(self.value_container, width=12)
            low.pack(side='left', padx=(2, 8))
            ttk.Label(self.value_container, text='high:').pack(side='left')
            high = ttk.Entry(self.value_container, width=12)
            high.pack(side='left', padx=2)
            self._value_widgets = {'kind': 'btwn', 'low': low, 'high': high}
        elif operator == 'is-in':
            if constrained_values:
                box = tk.Listbox(self.value_container, selectmode='extended', height=6, width=45,
                                  exportselection=False)
                for v in constrained_values:
                    box.insert('end', v)
                box.pack(side='left')
                self._value_widgets = {'kind': 'is-in-list', 'listbox': box}
            else:
                entry = ttk.Entry(self.value_container, width=50)
                entry.pack(side='left')
                ttk.Label(self.value_container, text='(comma-separated)').pack(side='left', padx=4)
                self._value_widgets = {'kind': 'is-in-text', 'entry': entry}
        elif operator == 'eq' and constrained_values:
            box = AutocompleteCombobox(self.value_container, values=constrained_values, width=45)
            box.pack(side='left')
            self._value_widgets = {'kind': 'single', 'entry': box}
        else:
            entry = ttk.Entry(self.value_container, width=50)
            entry.pack(side='left')
            self._value_widgets = {'kind': 'single', 'entry': entry}

    def _read_condition_value(self, operator):
        w = self._value_widgets
        if w['kind'] == 'btwn':
            low, high = w['low'].get().strip(), w['high'].get().strip()
            if not low or not high:
                raise ValueError('btwn requires both a low and a high value.')
            return [_to_number(low), _to_number(high)]
        if w['kind'] == 'is-in-list':
            selected = [w['listbox'].get(i) for i in w['listbox'].curselection()]
            if not selected:
                raise ValueError('Select at least one value for is-in.')
            return selected
        if w['kind'] == 'is-in-text':
            values = [v.strip() for v in w['entry'].get().split(',') if v.strip()]
            if not values:
                raise ValueError('Enter at least one comma-separated value for is-in.')
            return values
        value = w['entry'].get().strip()
        if not value:
            raise ValueError('Enter a value.')
        if operator in ('gt', 'lt', 'gte', 'lte'):
            return [_to_number(value)]
        return [value]

    def _add_condition(self):
        field = self.field_box.get().strip()
        operator = self.operator_box.get()
        if not field:
            messagebox.showerror('Missing field', 'Enter or choose a field name.')
            return
        try:
            values = self._read_condition_value(operator)
        except ValueError as exc:
            messagebox.showerror('Invalid value', str(exc))
            return

        leaf = {'kind': 'leaf', 'operator': operator, 'operands': [field] + values}
        if self.current_group is not None:
            self.current_group['children'].append(leaf)
        else:
            self.conditions.append(leaf)
        self._update_group_status()
        self._rebuild_condition_tree()

    def _start_group(self):
        if self.current_group is not None:
            messagebox.showerror('Already in a group', 'End the current group before starting a new one.')
            return
        self.current_group = {'kind': 'group', 'combinator': self.group_combinator.get(), 'children': []}
        self.conditions.append(self.current_group)
        self._update_group_status()
        self._rebuild_condition_tree()

    def _end_group(self):
        if self.current_group is None:
            return
        if len(self.current_group['children']) < 2:
            messagebox.showerror('Group too small', 'A group needs at least 2 conditions before you can close it.')
            return
        self.current_group = None
        self._update_group_status()

    def _update_group_status(self):
        if self.current_group is None:
            self.group_status_label.config(text='Adding to: top level')
        else:
            combinator = self.current_group['combinator'].upper()
            count = len(self.current_group['children'])
            self.group_status_label.config(text=f'Adding to: group ({combinator}) - {count} condition(s)')

    def _rebuild_condition_tree(self):
        self.cond_tree.delete(*self.cond_tree.get_children())
        for item in self.conditions:
            if item['kind'] == 'leaf':
                operator, field, values = item['operator'], item['operands'][0], item['operands'][1:]
                self.cond_tree.insert('', 'end', text='condition',
                                       values=(operator, field, ', '.join(str(v) for v in values)))
            else:
                group_id = self.cond_tree.insert(
                    '', 'end', text=f"GROUP ({item['combinator'].upper()})",
                    values=('', '', f"{len(item['children'])} condition(s)"), open=True)
                for leaf in item['children']:
                    operator, field, values = leaf['operator'], leaf['operands'][0], leaf['operands'][1:]
                    self.cond_tree.insert(group_id, 'end', text='condition',
                                           values=(operator, field, ', '.join(str(v) for v in values)))

    def _remove_condition(self):
        top_level_indices = set()
        leaf_locations = []  # (top_level_group_index, leaf_index)

        for item in self.cond_tree.selection():
            parent = self.cond_tree.parent(item)
            if parent:
                leaf_locations.append((self.cond_tree.index(parent), self.cond_tree.index(item)))
            else:
                top_level_indices.add(self.cond_tree.index(item))

        # a leaf whose whole group is also being removed doesn't need separate handling
        leaf_locations = [(g, l) for g, l in leaf_locations if g not in top_level_indices]

        for group_index, leaf_index in sorted(leaf_locations, key=lambda t: (t[0], -t[1])):
            del self.conditions[group_index]['children'][leaf_index]

        for index in sorted(top_level_indices, reverse=True):
            if self.conditions[index] is self.current_group:
                self.current_group = None
            del self.conditions[index]

        self._update_group_status()
        self._rebuild_condition_tree()

    def _add_output_field(self):
        field = self.output_field_box.get().strip()
        if not field:
            return
        if field not in self.output_fields:
            self.output_fields.append(field)
            self.fields_listbox.insert('end', field)
        self.output_field_box.set('')

    def _remove_output_field(self):
        for index in reversed(self.fields_listbox.curselection()):
            self.fields_listbox.delete(index)
            del self.output_fields[index]

    def _build_query_dict(self):
        if not self.conditions:
            raise ValueError('Add at least one condition.')

        nodes = []
        for item in self.conditions:
            if item['kind'] == 'leaf':
                nodes.append({'operator': item['operator'], 'operands': item['operands']})
            else:
                if len(item['children']) < 2:
                    raise ValueError(
                        f"A group needs at least 2 conditions (has {len(item['children'])}).")
                nodes.append({
                    'operator': item['combinator'],
                    'operands': [{'operator': leaf['operator'], 'operands': leaf['operands']}
                                 for leaf in item['children']],
                })

        if len(nodes) == 1:
            return nodes[0]
        return {'operator': self.combinator.get(), 'operands': nodes}

    def _selected_value_fields(self):
        selected = [field for field in VALUE_FIELDS if self.plot_value_field_vars[field].get()]
        if not selected:
            raise ValueError('Check at least one plot value_field.')
        return selected

    def _build_config(self):
        max_results_raw = self.max_results_entry.get().strip()
        config = {
            'quote_type': self.quote_type.get(),
            'query': self._build_query_dict(),
            'sort_field': self.sort_field_box.get().strip() or None,
            'sort_asc': bool(self.sort_asc.get()),
            'page_size': int(self.page_size_entry.get()),
            'max_results': int(max_results_raw) if max_results_raw else None,
            'request_delay_seconds': float(self.delay_entry.get()),
            'fields': list(self.output_fields) or None,
            'output': {
                'format': self.output_format.get(),
                'path': self.output_path_entry.get().strip() or 'output/results.json',
            },
            'value_fields': self._selected_value_fields(),
        }
        return config

    def _refresh_preview(self):
        try:
            config = self._build_config()
        except ValueError as exc:
            messagebox.showerror('Cannot build config', str(exc))
            return None
        text = json.dumps(config, indent=2)
        self.preview_text.delete('1.0', 'end')
        self.preview_text.insert('1.0', text)
        return config

    def _resolve_filename(self):
        filename = self.filename_entry.get().strip()
        if not filename:
            return None
        if not filename.endswith('.json'):
            filename += '.json'
        return filename

    def _write_config(self, config, filename):
        CONFIGS_DIR.mkdir(parents=True, exist_ok=True)
        path = CONFIGS_DIR / filename
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2)
        self._refresh_filename_choices()
        return path

    def _save_config(self):
        config = self._refresh_preview()
        if config is None:
            return
        filename = self._resolve_filename()
        if not filename:
            messagebox.showerror('Missing filename', 'Enter a filename to save to.')
            return
        path = self._write_config(config, filename)
        messagebox.showinfo('Saved', f'Wrote {path}')

    def _run_query_machine(self):
        config = self._refresh_preview()
        if config is None:
            return
        filename = self._resolve_filename()
        if not filename:
            messagebox.showerror('Missing filename', 'Enter a filename to save to.')
            return
        self._write_config(config, filename)

        script = Path(__file__).resolve().parent / 'query_machine.py'
        self._run_subprocess_streaming(
            [sys.executable, str(script), filename], self.run_button,
            header=f'python query_machine.py {filename}')

    def _resolve_results_json_path(self):
        fmt = self.output_format.get()
        if fmt == 'csv':
            return None
        path = Path(self.output_path_entry.get().strip() or 'output/results.json')
        if fmt == 'both':
            path = path.with_suffix('.json')
        script_dir = Path(__file__).resolve().parent
        return path if path.is_absolute() else script_dir / path

    def _plot_with_ticker_time(self):
        if self._dash_process is not None:
            self._dash_process.terminate()
            return

        results_path = self._resolve_results_json_path()
        if results_path is None:
            messagebox.showerror(
                'No JSON results',
                "output.format is 'csv' - ticker_time.py needs a JSON results file. "
                "Set format to 'json' or 'both' and run query_machine.py first.")
            return
        if not results_path.exists():
            messagebox.showerror('Results not found',
                                  f'{results_path} does not exist yet. Run query_machine.py first.')
            return

        try:
            value_fields = self._selected_value_fields()
        except ValueError as exc:
            messagebox.showerror('Cannot launch dashboard', str(exc))
            return

        script = Path(__file__).resolve().parent / 'ticker_time.py'
        args = [sys.executable, str(script), str(results_path), '--engine', 'dash',
                '--value-field', *value_fields]
        output_queue = queue.Queue()

        self.plot_button.config(text='Stop live dashboard')
        self.run_output.config(state='normal')
        self.run_output.insert(
            'end', f'\n$ python ticker_time.py {results_path.name} --engine dash '
                   f'--value-field {" ".join(value_fields)}\n')
        self.run_output.config(state='disabled')
        self.run_output.see('end')

        def worker():
            process = subprocess.Popen(
                args,
                cwd=str(script.parent),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            self._dash_process = process
            for line in process.stdout:
                output_queue.put(line)
            process.wait()
            output_queue.put(f'\n[dashboard server exited with code {process.returncode}]\n')
            output_queue.put(None)

        opened_browser = {'done': False}

        def poll():
            finished = False
            try:
                while True:
                    line = output_queue.get_nowait()
                    if line is None:
                        finished = True
                        break
                    self.run_output.config(state='normal')
                    self.run_output.insert('end', line)
                    self.run_output.see('end')
                    self.run_output.config(state='disabled')
                    if not opened_browser['done'] and 'DASHBOARD READY at' in line:
                        opened_browser['done'] = True
                        url = line.split('DASHBOARD READY at', 1)[1].strip()
                        webbrowser.open(url)
            except queue.Empty:
                pass

            if finished:
                self._dash_process = None
                self.plot_button.config(text='Launch live dashboard (ticker_time.py, dash)')
            else:
                self.after(100, poll)

        threading.Thread(target=worker, daemon=True).start()
        self.after(100, poll)

    def _run_subprocess_streaming(self, args, button, header, on_success=None):
        output_queue = queue.Queue()
        result = {}

        button.config(state='disabled')
        self.run_output.config(state='normal')
        self.run_output.insert('end', f'\n$ {header}\n')
        self.run_output.config(state='disabled')
        self.run_output.see('end')

        def worker():
            try:
                process = subprocess.Popen(
                    args,
                    cwd=str(Path(__file__).resolve().parent),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                )
                for line in process.stdout:
                    output_queue.put(line)
                process.wait()
                result['returncode'] = process.returncode
                output_queue.put(f'\n[exited with code {process.returncode}]\n')
            except Exception as exc:
                result['returncode'] = None
                output_queue.put(f'\n[failed to launch: {exc}]\n')
            finally:
                output_queue.put(None)

        def poll():
            finished = False
            try:
                while True:
                    line = output_queue.get_nowait()
                    if line is None:
                        finished = True
                        break
                    self.run_output.config(state='normal')
                    self.run_output.insert('end', line)
                    self.run_output.see('end')
                    self.run_output.config(state='disabled')
            except queue.Empty:
                pass

            if finished:
                button.config(state='normal')
                if on_success and result.get('returncode') == 0:
                    on_success()
            else:
                self.after(100, poll)

        threading.Thread(target=worker, daemon=True).start()
        self.after(100, poll)

    def _load_config(self):
        filename = self.filename_entry.get().strip()
        if filename and not filename.endswith('.json'):
            filename += '.json'
        path = CONFIGS_DIR / filename
        if not path.exists():
            messagebox.showerror('Not found', f'{path} does not exist.')
            return

        with open(path, 'r', encoding='utf-8') as f:
            config = json.load(f)

        try:
            combinator, items = _parse_query_tree(config['query'])
        except ValueError as exc:
            messagebox.showerror('Cannot load query', str(exc))
            return

        self.quote_type.set(config.get('quote_type', 'equity'))
        self._on_quote_type_change()

        self.combinator.set(combinator)
        self.conditions = items
        self.current_group = None
        self._update_group_status()
        self._rebuild_condition_tree()

        self.sort_field_box.set(config.get('sort_field') or '')
        self.sort_asc.set(bool(config.get('sort_asc', False)))
        self.page_size_entry.set(config.get('page_size', 250))
        self.max_results_entry.delete(0, 'end')
        if config.get('max_results') is not None:
            self.max_results_entry.insert(0, str(config['max_results']))
        self.delay_entry.delete(0, 'end')
        self.delay_entry.insert(0, str(config.get('request_delay_seconds', 0.5)))

        self.output_fields = list(config.get('fields') or [])
        self.fields_listbox.delete(0, 'end')
        for field in self.output_fields:
            self.fields_listbox.insert('end', field)

        output = config.get('output', {})
        self.output_format.set(output.get('format', 'json'))
        self.output_path_entry.delete(0, 'end')
        self.output_path_entry.insert(0, output.get('path', 'output/results.json'))

        if 'value_fields' in config:
            loaded_value_fields = config['value_fields']
        elif 'value_field' in config:
            loaded_value_fields = [config['value_field']]  # older single-field configs
        else:
            loaded_value_fields = ['Close']
        for field in VALUE_FIELDS:
            self.plot_value_field_vars[field].set(field in loaded_value_fields)

        self._refresh_preview()


def _to_number(text):
    try:
        return int(text)
    except ValueError:
        return float(text)


def _parse_leaf(node):
    return {'kind': 'leaf', 'operator': node['operator'].lower(), 'operands': node['operands']}


def _parse_query_tree(node):
    """Returns (top_level_combinator, items) where each item is either a leaf condition or a
    one-level-deep and/or group of leaves. Anything nested more than 2 levels isn't supported
    by this editor; callers should tell the user to edit the JSON directly for those."""
    operator = node['operator'].lower()
    operands = node['operands']
    if operator not in ('and', 'or'):
        return 'and', [_parse_leaf(node)]

    items = []
    for sub in operands:
        if not isinstance(sub, dict):
            raise ValueError('Malformed query tree.')
        sub_op = sub['operator'].lower()
        if sub_op in ('and', 'or'):
            children = []
            for leaf in sub['operands']:
                if not isinstance(leaf, dict):
                    raise ValueError('Malformed query tree.')
                if leaf['operator'].lower() in ('and', 'or'):
                    raise ValueError('This query nests and/or groups more than 2 levels deep; '
                                      'edit the JSON file directly.')
                children.append(_parse_leaf(leaf))
            items.append({'kind': 'group', 'combinator': sub_op, 'children': children})
        else:
            items.append(_parse_leaf(sub))
    return operator, items


def main():
    app = ConfigBuilderApp()
    app.mainloop()


if __name__ == '__main__':
    main()
