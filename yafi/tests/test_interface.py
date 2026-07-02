import json
import sys
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


if __name__ == '__main__':
    test_config_builder_round_trip()
    print('ALL GOOD')
