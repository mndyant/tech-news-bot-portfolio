import copy

from bot.delivery import (
    accept_brief,
    canonical_url,
    collect_pending,
    deliver_digest,
    select_items,
)


def record(item_id, source='openai', text='本文です'):
    return {"id": item_id, "title": f"Title {item_id}", "link": f"https://example.com/{item_id}",
            "description": text, "source": source, "members": [[source, item_id]], "text": text}


def test_canonical_url_removes_tracking_query():
    assert canonical_url('HTTPS://Example.com/a/?utm_source=x&b=2') == 'https://example.com/a?b=2'


def test_collect_pending_deduplicates_same_article_across_sources():
    sources = {'openai': [record('one')], 'hn': [record('two', 'hn'), record('one', 'hn')]}
    pending, rejected = collect_pending(sources, {}, {})
    assert rejected == 0
    assert len(pending) == 2
    assert len(next(r for r in pending if r['link'].endswith('/one'))['members']) == 2


def test_select_items_applies_global_and_per_source_caps():
    rows = [record(str(i), 'openai' if i < 4 else 'hn') for i in range(6)]
    selected = select_items(rows, {'max_items': 3, 'max_per_source': 2})
    assert len(selected) == 3
    assert sum(any(source == 'openai' for source, _ in row['members']) for row in selected) == 2


def test_accept_brief_rejects_untranslated_or_empty_summary():
    row = record('one')
    assert not accept_brief(row, {'title_ja': 'English', 'summary_ja': '日本語'})
    assert row['status'] == 'translation_pending'
    assert not accept_brief(row, {'title_ja': '日本語タイトル', 'summary_ja': ''})
    assert row['status'] == 'summary_pending'


def test_failed_delivery_keeps_seen_and_pending():
    seen, state = {}, {}
    checkpoints = []
    report = deliver_digest(
        {'openai': [record('one')]}, seen, state, {'max_items': 5, 'max_per_source': 2},
        lambda rows: {'openai:one': {'id': 'openai:one', 'title_ja': '日本語タイトル', 'summary_ja': '本文の要約です'}},
        lambda text: False, lambda s, st: checkpoints.append((copy.deepcopy(s), copy.deepcopy(st))),
    )
    assert report['sent'] == 0
    assert seen == {}
    assert 'https://example.com/one' in state['pending']


def test_successful_delivery_acknowledges_only_after_send():
    seen, state, checkpoints = {}, {}, []
    report = deliver_digest(
        {'openai': [record('one')]}, seen, state, {'max_items': 5, 'max_per_source': 2},
        lambda rows: {'openai:one': {'id': 'openai:one', 'title_ja': '日本語タイトル', 'summary_ja': '本文の要約です'}},
        lambda text: True, lambda s, st: checkpoints.append((copy.deepcopy(s), copy.deepcopy(st))),
    )
    assert report['sent'] == 1
    assert seen['openai'] == ['one']
    assert state['pending'] == {}
    assert len(checkpoints) == 2


def brief_for(rows):
    return {r['id']: {'title_ja': '日本語見出し', 'summary_ja': '本文に基づく要約です。'}
            for r in rows}


def test_dry_run_never_sends_saves_or_mutates_inputs():
    seen, state = {}, {}
    def forbidden(*args):
        raise AssertionError('dry-run must not send or persist')
    result = deliver_digest({'openai': [record('one')]}, seen, state, {},
                            brief_for, forbidden, forbidden, dry_run=True)
    assert result['ready'] == 1 and result['sent'] == 0 and result['preview']
    assert seen == {} and state == {}


def test_retry_can_deliver_pending_item_missing_from_next_feed():
    seen, state = {}, {}
    deliver_digest({'openai': [record('one')]}, seen, state, {},
                   brief_for, lambda _: False, lambda *args: None)
    result = deliver_digest({}, seen, state, {},
                            lambda _: {}, lambda _: True, lambda *args: None)
    assert result['sent'] == 1
    assert seen == {'openai': ['one']} and not state['pending']


def test_title_only_retry_requires_summary_when_body_becomes_available():
    seen, state = {}, {}
    deliver_digest({'openai': [record('one', text='')]}, seen, state, {},
                   brief_for, lambda _: False, lambda *args: None)
    result = deliver_digest({'openai': [record('one', text='New body')]}, seen, state, {},
                            lambda _: {}, lambda _: True, lambda *args: None)
    assert result['quality_pending'] == 1 and result['sent'] == 0 and not seen
    assert state['pending']['https://example.com/one']['status'] == 'translation_pending'


def test_partial_delivery_marks_only_confirmed_batch_seen():
    # Each long source URL forces a separate Discord batch.
    rows = [record(str(i)) | {'link': 'https://example.com/' + str(i) + 'a' * 950}
            for i in range(3)]
    seen, state, snapshots = {}, {}, []
    outcomes = iter([True, False])
    result = deliver_digest({'openai': rows}, seen, state,
                            {'max_items': 3, 'max_per_source': 3}, brief_for,
                            lambda _: next(outcomes),
                            lambda s, st: snapshots.append((copy.deepcopy(s), copy.deepcopy(st))))
    assert result['sent'] == 1 and result['errors'] == ['DeliveryNotConfirmed']
    assert seen == {'openai': ['0']} and len(state['pending']) == 2
    assert snapshots[-1][0] == {'openai': ['0']}
