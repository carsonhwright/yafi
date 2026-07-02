import json
import tkinter as tk
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


class AutocompleteCombobox(ttk.Combobox):
    def __init__(self, master=None, values=(), **kwargs):
        super().__init__(master, **kwargs)
        self._all_values = list(values)
        self['values'] = self._all_values
        self.bind('<KeyRelease>', self._on_keyrelease)

    def set_values(self, values):
        self._all_values = list(values)
        self['values'] = self._all_values

    def _on_keyrelease(self, event):
        if event.keysym in ('Up', 'Down', 'Left', 'Right', 'Return', 'Escape', 'Tab'):
            return
        typed = self.get().lower()
        if not typed:
            self['values'] = self._all_values
            return
        filtered = [v for v in self._all_values if typed in v.lower()]
        self['values'] = filtered or self._all_values


class ConfigBuilderApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('yafi query config builder')
        self.geometry('900x800')

        self.conditions = []
        self.output_fields = []
        self.query_fields = []
        self.valid_values = {}
        self._value_widgets = {}

        self.quote_type = tk.StringVar(value='equity')
        self.combinator = tk.StringVar(value='and')
        self.sort_asc = tk.BooleanVar(value=False)
        self.output_format = tk.StringVar(value='json')

        self._build_widgets()
        self._on_quote_type_change()

    def _build_widgets(self):
        pad = {'padx': 6, 'pady': 4}

        top = ttk.Frame(self)
        top.pack(fill='x', **pad)
        ttk.Label(top, text='quote_type:').pack(side='left')
        quote_type_box = ttk.Combobox(top, textvariable=self.quote_type, values=list(QUOTE_TYPE_MAP),
                                       state='readonly', width=10)
        quote_type_box.pack(side='left', padx=(4, 20))
        quote_type_box.bind('<<ComboboxSelected>>', lambda e: self._on_quote_type_change())

        ttk.Label(top, text='combine conditions with:').pack(side='left')
        ttk.Radiobutton(top, text='AND', variable=self.combinator, value='and').pack(side='left')
        ttk.Radiobutton(top, text='OR', variable=self.combinator, value='or').pack(side='left')

        cond_frame = ttk.LabelFrame(self, text='Conditions (query)')
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

        self.cond_tree = ttk.Treeview(cond_frame, columns=('operator', 'field', 'values'),
                                       show='headings', height=6)
        for col, width in (('operator', 70), ('field', 260), ('values', 380)):
            self.cond_tree.heading(col, text=col)
            self.cond_tree.column(col, width=width)
        self.cond_tree.pack(fill='x', padx=6, pady=(4, 0))
        ttk.Button(cond_frame, text='Remove selected', command=self._remove_condition).pack(anchor='e', padx=6, pady=4)

        settings_frame = ttk.LabelFrame(self, text='Sort / pagination')
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
            self, text='Output fields (response keys kept in results.json - different from query fields above)')
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

        output_frame = ttk.LabelFrame(self, text='Output')
        output_frame.pack(fill='x', **pad)
        ttk.Label(output_frame, text='format:').grid(row=0, column=0, sticky='w')
        ttk.Combobox(output_frame, textvariable=self.output_format, values=['json', 'csv', 'both'],
                     state='readonly', width=8).grid(row=0, column=1, sticky='w', padx=4)
        ttk.Label(output_frame, text='path:').grid(row=0, column=2, sticky='w')
        self.output_path_entry = ttk.Entry(output_frame, width=40)
        self.output_path_entry.insert(0, 'output/results.json')
        self.output_path_entry.grid(row=0, column=3, sticky='w', padx=4)

        file_frame = ttk.LabelFrame(self, text=f'Save to {CONFIGS_DIR}')
        file_frame.pack(fill='x', **pad)
        ttk.Label(file_frame, text='filename:').pack(side='left', padx=(6, 4))
        self.filename_entry = ttk.Entry(file_frame, width=30)
        self.filename_entry.insert(0, 'my_query.json')
        self.filename_entry.pack(side='left')
        ttk.Button(file_frame, text='Load', command=self._load_config).pack(side='left', padx=6)
        ttk.Button(file_frame, text='Preview', command=self._refresh_preview).pack(side='left', padx=6)
        ttk.Button(file_frame, text='Save', command=self._save_config).pack(side='left', padx=6)

        preview_frame = ttk.LabelFrame(self, text='Preview')
        preview_frame.pack(fill='both', expand=True, **pad)
        self.preview_text = scrolledtext.ScrolledText(preview_frame, height=10, wrap='none')
        self.preview_text.pack(fill='both', expand=True)

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

        operands = [field] + values
        self.conditions.append({'operator': operator, 'operands': operands})
        self.cond_tree.insert('', 'end', values=(operator, field, ', '.join(str(v) for v in values)))

    def _remove_condition(self):
        for item in self.cond_tree.selection():
            index = self.cond_tree.index(item)
            del self.conditions[index]
            self.cond_tree.delete(item)

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
        if len(self.conditions) == 1:
            return self.conditions[0]
        return {'operator': self.combinator.get(), 'operands': list(self.conditions)}

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

    def _save_config(self):
        config = self._refresh_preview()
        if config is None:
            return
        filename = self.filename_entry.get().strip()
        if not filename:
            messagebox.showerror('Missing filename', 'Enter a filename to save to.')
            return
        if not filename.endswith('.json'):
            filename += '.json'

        CONFIGS_DIR.mkdir(parents=True, exist_ok=True)
        path = CONFIGS_DIR / filename
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2)
        messagebox.showinfo('Saved', f'Wrote {path}')

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
            combinator, leaves = _parse_query_tree(config['query'])
        except ValueError as exc:
            messagebox.showerror('Cannot load query', str(exc))
            return

        self.quote_type.set(config.get('quote_type', 'equity'))
        self._on_quote_type_change()

        self.combinator.set(combinator)
        self.conditions = []
        self.cond_tree.delete(*self.cond_tree.get_children())
        for operator, field, values in leaves:
            self.conditions.append({'operator': operator, 'operands': [field] + values})
            self.cond_tree.insert('', 'end', values=(operator, field, ', '.join(str(v) for v in values)))

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

        self._refresh_preview()


def _to_number(text):
    try:
        return int(text)
    except ValueError:
        return float(text)


def _parse_query_tree(node):
    operator = node['operator'].lower()
    operands = node['operands']
    if operator in ('and', 'or'):
        leaves = []
        for sub in operands:
            if not isinstance(sub, dict):
                raise ValueError('Malformed query tree.')
            sub_op = sub['operator'].lower()
            if sub_op in ('and', 'or'):
                raise ValueError('This query has nested and/or groups; edit the JSON file directly.')
            leaves.append((sub_op, sub['operands'][0], sub['operands'][1:]))
        return operator, leaves
    return 'and', [(operator, operands[0], operands[1:])]


def main():
    app = ConfigBuilderApp()
    app.mainloop()


if __name__ == '__main__':
    main()
