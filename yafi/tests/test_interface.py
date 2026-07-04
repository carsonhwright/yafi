import gc
import json
import sys
import time
import tkinter
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import interface
import query_machine


def test_config_builder_round_trip():
    app = interface.ConfigBuilderApp()
    app.withdraw()

    app.field_box.set('intradaymarketcap')
    app.operator_box.set('gt')
    app._on_field_or_operator_change()
    app._value_widgets['entry'].insert(0, '15000000000')
    app._add_condition()

    app.field_box.set('exchange')
    app.operator_box.set('is-in')
    app._on_field_or_operator_change()
    listbox = app._value_widgets['listbox']
    values = list(listbox.get(0, 'end'))
    assert 'NMS' in values and 'NYQ' in values
    listbox.selection_set(values.index('NMS'))
    listbox.selection_set(values.index('NYQ'))
    app._add_condition()

    app.field_box.set('peratio.lasttwelvemonths')
    app.operator_box.set('btwn')
    app._on_field_or_operator_change()
    app._value_widgets['low'].insert(0, '8')
    app._value_widgets['high'].insert(0, '35')
    app._add_condition()

    assert len(app.conditions) == 3

    app.output_field_box.set('symbol')
    app._add_output_field()
    app.output_field_box.set('marketCap')
    app._add_output_field()

    app.plot_value_field_vars['Close'].set(False)
    app.plot_value_field_vars['Open'].set(True)
    app.plot_value_field_vars['Volume'].set(True)

    app.filename_entry.delete(0, 'end')
    app.filename_entry.insert(0, '_gui_smoke_test.json')
    app._save_config()

    saved_path = interface.CONFIGS_DIR / '_gui_smoke_test.json'
    try:
        config = json.loads(saved_path.read_text())

        assert config['quote_type'] == 'equity'
        assert config['query']['operator'] == 'and'
        assert len(config['query']['operands']) == 3
        assert config['fields'] == ['symbol', 'marketCap']
        assert config['value_fields'] == ['Open', 'Volume'], 'canonical VALUE_FIELDS order, not check order'

        query_machine.build_query(config['query'], query_machine.QUOTE_TYPE_MAP[config['quote_type']])

        app2 = interface.ConfigBuilderApp()
        app2.withdraw()
        app2.filename_entry.delete(0, 'end')
        app2.filename_entry.insert(0, '_gui_smoke_test.json')
        app2._load_config()
        assert len(app2.conditions) == 3
        assert app2.output_fields == ['symbol', 'marketCap']
        assert app2._selected_value_fields() == ['Open', 'Volume']
        app2.destroy()
        gc.collect()  # reclaim app2's tk.Variables now, while its interpreter is still around
    finally:
        saved_path.unlink(missing_ok=True)

    app.destroy()
    gc.collect()


def test_run_query_machine_button():
    app = interface.ConfigBuilderApp()
    app.withdraw()

    app.field_box.set('intradaymarketcap')
    app.operator_box.set('gt')
    app._on_field_or_operator_change()
    app._value_widgets['entry'].insert(0, '500000000000')
    app._add_condition()

    app.max_results_entry.insert(0, '3')
    app.output_field_box.set('symbol')
    app._add_output_field()

    app.filename_entry.delete(0, 'end')
    app.filename_entry.insert(0, '_gui_run_test.json')
    app.output_path_entry.delete(0, 'end')
    app.output_path_entry.insert(0, 'output/_gui_run_test_output.json')

    config_path = interface.CONFIGS_DIR / '_gui_run_test.json'
    output_path = Path(__file__).resolve().parent.parent / 'output' / '_gui_run_test_output.json'
    try:
        app._run_query_machine()

        for _ in range(300):
            app.update()
            if str(app.run_button['state']) == 'normal':
                break
            time.sleep(0.1)
        else:
            raise AssertionError('query_machine.py run did not finish in time')

        log = app.run_output.get('1.0', 'end')
        assert 'exited with code 0' in log, log
        assert output_path.exists(), log
        results = json.loads(output_path.read_text())
        assert len(results) <= 3
        assert all('symbol' in r for r in results)
    finally:
        config_path.unlink(missing_ok=True)
        output_path.unlink(missing_ok=True)
        app.destroy()
        gc.collect()


def _wait_for_button(app, button, timeout=30):
    for _ in range(int(timeout / 0.1)):
        app.update()
        if str(button['state']) == 'normal':
            return
        time.sleep(0.1)
    raise AssertionError('subprocess did not finish in time')


def _wait_until(predicate, timeout=30, tick=0.1):
    for _ in range(int(timeout / tick)):
        if predicate():
            return
        time.sleep(tick)
    raise AssertionError('condition not met in time')


def test_plot_button_launches_and_stops_live_dashboard():
    app = interface.ConfigBuilderApp()
    app.withdraw()

    app.field_box.set('intradaymarketcap')
    app.operator_box.set('gt')
    app._on_field_or_operator_change()
    app._value_widgets['entry'].insert(0, '500000000000')
    app._add_condition()

    app.max_results_entry.insert(0, '3')
    app.output_field_box.set('symbol')
    app._add_output_field()
    app.plot_value_field_vars['Volume'].set(True)  # + the default Close -> exercises multi-field CLI wiring

    app.filename_entry.delete(0, 'end')
    app.filename_entry.insert(0, '_gui_plot_test.json')
    app.output_path_entry.delete(0, 'end')
    app.output_path_entry.insert(0, 'output/_gui_plot_test_output.json')

    yafi_dir = Path(__file__).resolve().parent.parent
    config_path = interface.CONFIGS_DIR / '_gui_plot_test.json'
    results_path = yafi_dir / 'output' / '_gui_plot_test_output.json'

    opened_urls = []
    original_open = interface.webbrowser.open
    interface.webbrowser.open = opened_urls.append

    try:
        app._run_query_machine()
        _wait_for_button(app, app.run_button)
        assert results_path.exists()
        result_symbols = [r['symbol'] for r in json.loads(results_path.read_text())]
        assert result_symbols

        app._plot_with_ticker_time()

        def ready():
            app.update()
            return len(opened_urls) == 1
        _wait_until(ready, timeout=30)

        assert app._dash_process is not None
        assert str(app.plot_button['text']) == 'Stop live dashboard'

        url = opened_urls[0]
        assert url.startswith('http://127.0.0.1:')
        # the index page is a JS-hydrated shell; the actual layout is served from
        # /_dash-layout, so check that instead to confirm our app (not an empty one) is live
        with urllib.request.urlopen(url.rstrip('/') + '/_dash-layout', timeout=5) as resp:
            layout = json.loads(resp.read().decode('utf-8'))
        assert resp.status == 200
        layout_str = json.dumps(layout)
        assert 'Ticker time series' in layout_str
        assert 'group-checklist' in layout_str
        assert any(symbol in layout_str for symbol in result_symbols), (result_symbols, layout_str)

        log = app.run_output.get('1.0', 'end')
        assert '--value-field Close Volume' in log, log

        app._plot_with_ticker_time()  # second click = stop

        def stopped():
            app.update()
            return app._dash_process is None
        _wait_until(stopped, timeout=15)

        assert str(app.plot_button['text']).startswith('Launch live dashboard')
    finally:
        interface.webbrowser.open = original_open
        if app._dash_process is not None:
            app._dash_process.terminate()
        config_path.unlink(missing_ok=True)
        results_path.unlink(missing_ok=True)
        app.destroy()
        gc.collect()


def test_filename_dropdown_lists_and_prefix_filters_configs():
    file1 = interface.CONFIGS_DIR / '_dropdown_test_alpha.json'
    file2 = interface.CONFIGS_DIR / '_dropdown_test_beta_alpha.json'
    file1.write_text('{}')
    file2.write_text('{}')

    try:
        app = interface.ConfigBuilderApp()
        app.withdraw()

        assert file1.name in app.filename_entry._all_values
        assert file2.name in app.filename_entry._all_values

        app.filename_entry.delete(0, 'end')
        app.filename_entry.insert(0, '_dropdown_test_alpha')
        app.filename_entry._on_keyrelease(type('Event', (), {'keysym': 'a'})())

        filtered = app.filename_entry['values']
        assert file1.name in filtered, filtered
        assert file2.name not in filtered, 'substring match should not qualify, only prefix match'

        app.destroy()
        gc.collect()
    finally:
        file1.unlink(missing_ok=True)
        file2.unlink(missing_ok=True)


def test_config_window_is_scrollable():
    app = interface.ConfigBuilderApp()
    app.update()

    canvas = next(w for w in app.winfo_children() if isinstance(w, tkinter.Canvas))
    bbox = canvas.bbox('all')
    content_height = bbox[3] - bbox[1]
    assert content_height > canvas.winfo_height(), (
        'content should be taller than the visible canvas for this test to be meaningful')

    before = canvas.yview()
    canvas.yview_scroll(5, 'units')
    app.update()
    after = canvas.yview()
    assert after[0] > before[0], 'scrolling did not move the view'

    app.destroy()
    gc.collect()


if __name__ == '__main__':
    test_config_builder_round_trip()
    test_run_query_machine_button()
    test_plot_button_launches_and_stops_live_dashboard()
    test_filename_dropdown_lists_and_prefix_filters_configs()
    test_config_window_is_scrollable()
    print('ALL GOOD')
