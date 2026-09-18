"""CLI state recovery tests without feeds, model calls, or notifications."""
import sys
from unittest.mock import patch

import pytest

import main


def test_first_run_without_any_state_file():
    with patch.object(sys, 'argv', ['main.py', '--dry-run']), \
         patch.object(main.Path, 'exists', return_value=False), \
         patch.object(main, 'load_json', return_value={}) as read, \
         patch.object(main, 'run_once', return_value={'preview': [], 'errors': []}) as run:
        main.main()
    read.assert_called_once_with(main.CONFIG_PATH)
    run.assert_called_once_with({}, {}, {}, dry_run=True)


@pytest.mark.parametrize('legacy_error', [FileNotFoundError, ValueError])
def test_canonical_state_recovers_without_legacy_seen_file(legacy_error):
    state = {'seen': {'openai': ['delivered']}, 'pending': {}}

    def read(path):
        if path == main.CONFIG_PATH:
            return {}
        if path == 'delivery_state.json':
            return state
        raise legacy_error('Legacy mirror is missing or corrupt')

    report = {'preview': [], 'errors': []}
    with patch.object(sys, 'argv', ['main.py', '--dry-run']), \
         patch.object(main.Path, 'exists', return_value=True), \
         patch.object(main, 'load_json', side_effect=read), \
         patch.object(main, 'run_once', return_value=report) as run:
        main.main()
    run.assert_called_once_with({}, state['seen'], state, dry_run=True)
