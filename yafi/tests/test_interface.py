import json
import sys
import time
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

        query_machine.build_query(config['query'], query_machine.QUOTE_TYPE_MAP[config['quote_type']])

        app2 = interface.ConfigBuilderApp()
        app2.withdraw()
        app2.filename_entry.delete(0, 'end')
        app2.filename_entry.insert(0, '_gui_smoke_test.json')
        app2._load_config()
        assert len(app2.conditions) == 3
        assert app2.output_fields == ['symbol', 'marketCap']
        app2.destroy()
    finally:
        saved_path.unlink(missing_ok=True)

    app.destroy()


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


def _wait_for_button(app, button, timeout=30):
    for _ in range(int(timeout / 0.1)):
        app.update()
        if str(button['state']) == 'normal':
            return
        time.sleep(0.1)
    raise AssertionError('subprocess did not finish in time')


def test_plot_button_runs_ticker_time_and_opens_browser():
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
    app.filename_entry.insert(0, '_gui_plot_test.json')
    app.output_path_entry.delete(0, 'end')
    app.output_path_entry.insert(0, 'output/_gui_plot_test_output.json')

    yafi_dir = Path(__file__).resolve().parent.parent
    config_path = interface.CONFIGS_DIR / '_gui_plot_test.json'
    results_path = yafi_dir / 'output' / '_gui_plot_test_output.json'
    dashboard_path = yafi_dir / 'output' / '_gui_plot_test_output_dashboard.html'

    opened_urls = []
    original_open = interface.webbrowser.open
    interface.webbrowser.open = opened_urls.append

    try:
        app._run_query_machine()
        _wait_for_button(app, app.run_button)
        assert results_path.exists()

        app._plot_with_ticker_time()
        _wait_for_button(app, app.plot_button)

        log = app.run_output.get('1.0', 'end')
        assert 'exited with code 0' in log, log
        assert dashboard_path.exists(), log
        assert dashboard_path.stat().st_size > 0

        assert len(opened_urls) == 1, opened_urls
        assert opened_urls[0] == dashboard_path.resolve().as_uri()
    finally:
        interface.webbrowser.open = original_open
        config_path.unlink(missing_ok=True)
        results_path.unlink(missing_ok=True)
        dashboard_path.unlink(missing_ok=True)
        app.destroy()


if __name__ == '__main__':
    test_config_builder_round_trip()
    test_run_query_machine_button()
    test_plot_button_runs_ticker_time_and_opens_browser()
    print('ALL GOOD')
