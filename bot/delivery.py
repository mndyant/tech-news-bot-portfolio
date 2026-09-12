"""Select a small digest and acknowledge only items actually delivered.

Network clients are injected. This module can be exercised entirely offline.
"""
from __future__ import annotations

import copy
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

JAPANESE = re.compile(r'[\u3040-\u30ff\u4e00-\u9fff]')
DEFAULT_PRIORITY = {'openai': 10, 'anthropic': 10, 'github_trending': 7,
                    'arxiv': 6, 'hn': 5, 'reddit': 4}


def canonical_url(value: str) -> str:
    """Remove tracking parameters while preserving article identity."""
    try:
        parts = urlsplit(value)
        if parts.scheme not in ('http', 'https') or not parts.hostname or parts.username:
            return ''
        query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
                 if not k.lower().startswith('utm_') and k.lower() not in ('fbclid', 'gclid')]
        return urlunsplit((parts.scheme.lower(), parts.netloc.lower(),
                          parts.path.rstrip('/') or '/', urlencode(sorted(query)), ''))
    except (TypeError, ValueError):
        return ''


def japanese_text(value: object) -> bool:
    """Reject blank/non-Japanese model output; this is not a factuality check."""
    return isinstance(value, str) and bool(JAPANESE.search(value.strip()))


def collect_pending(sources: dict, seen: dict, state: dict) -> tuple[list, int]:
    """Keep failed/deferred items, merging the same URL across sources."""
    pending = state.setdefault('pending', {})
    delivered = set(state.setdefault('delivered_urls', []))
    rejected = 0
    for source, entries in sources.items():
        seen_ids = set(seen.get(source, []))
        for entry in entries:
            item_id = entry.get('id')
            if not item_id or item_id in seen_ids:
                continue
            link = entry.get('link') or entry.get('url')
            if not link and source == 'github_trending':
                link = 'https://github.com/' + item_id
            url = canonical_url(link)
            title = entry.get('title') or entry.get('name')
            if not url or not title or len(url) > 1000:
                rejected += 1
                continue
            if url in delivered:
                # The canonical article was delivered previously through another source.
                seen.setdefault(source, []).append(item_id)
                seen_ids.add(item_id)
                continue
            record = pending.setdefault(url, {
                'id': source + ':' + str(item_id), 'title': title, 'link': url,
                'text': (entry.get('abstract') or entry.get('description') or '')[:2400],
                'members': [], 'status': 'pending',
            })
            member = [source, item_id]
            if member not in record['members']:
                record['members'].append(member)
            if not record['text']:
                record['text'] = (entry.get('abstract') or entry.get('description') or '')[:2400]
    return list(pending.values()), rejected


def select_items(records: list, config: dict) -> list:
    """Select a configurable global cap, then enforce source diversity."""
    limit = int(config.get('max_items', 5))
    per_source = int(config.get('max_per_source', 2))
    if not 1 <= limit <= 20 or not 1 <= per_source <= limit:
        raise ValueError('max_items must be 1..20 and max_per_source must be 1..max_items')
    priority = {**DEFAULT_PRIORITY, **config.get('source_priority', {})}
    counts, selected = {}, []
    def members(record):
        # collect_pending() supplies members; accepting a raw source record keeps
        # this selector independently testable and safe for future collectors.
        return record.get('members') or [(record.get('source', ''), record.get('id', ''))]

    for record in sorted(records, key=lambda r: -max(priority.get(s, 3) for s, _ in members(r))):
        sources = members(record)
        source = max((s for s, _ in sources), key=lambda s: priority.get(s, 3))
        if counts.get(source, 0) >= per_source:
            continue
        selected.append(record)
        counts[source] = counts.get(source, 0) + 1
        if len(selected) >= limit:
            break
    return selected


def accept_brief(record: dict, brief: object) -> bool:
    """Validate exact fields and make title-only coverage explicit."""
    text = record.get('text')
    if text is None:
        text = record.get('abstract') or record.get('description') or ''
    if not isinstance(brief, dict) or not japanese_text(brief.get('title_ja')):
        record['status'] = 'translation_pending'
        return False
    if text and not japanese_text(brief.get('summary_ja')):
        record['status'] = 'summary_pending'
        return False
    record['brief'] = {'title_ja': brief['title_ja'].strip(),
                       'summary_ja': brief.get('summary_ja', '').strip() if text else ''}
    record['text'] = text
    record['status'] = 'ready' if text else 'title_only'
    return True


def plain(value: str, limit: int) -> str:
    """Keep previews compact and prevent source text from creating mentions/markup."""
    value = ' '.join(value.split()).replace('@', '＠')
    return re.sub(r'[*_`<>]', '', value)[:limit]


def render_batches(records: list) -> list[tuple[str, list]]:
    """Pack complete articles without cutting their source links."""
    header = '**今日の注目ニュース**\n'
    text, members, batches = header, [], []
    for record in records:
        brief = record['brief']
        body = (plain(brief['summary_ja'], 160) if record['text'] else
                '本文未取得：見出しの翻訳のみです。内容は原文で確認してください。')
        block = f"\n・{plain(brief['title_ja'], 70)}\n{body}\n<{record['link']}>\n"
        if len(text + block) > 1900 and members:
            batches.append((text, members))
            text, members = header, []
        text += block
        members.append(record)
    if members:
        batches.append((text, members))
    return batches


def deliver_digest(sources: dict, seen: dict, state: dict, config: dict,
                   summarize, send, checkpoint, *, dry_run: bool = False) -> dict:
    """Generate once, send a bounded digest, and checkpoint each confirmed batch.

    Failed summaries and failed sends stay pending. Dry runs never send or save.
    A timeout after remote acceptance can still cause a duplicate on retry.
    """
    if dry_run:
        seen, state = copy.deepcopy(seen), copy.deepcopy(state)
    records, rejected = collect_pending(sources, seen, state)
    selected = select_items(records, config)
    needing = [r for r in selected if r.get('status') not in ('ready', 'title_only')]
    error = None
    try:
        briefs = summarize(needing) if needing else {}
    except Exception as exc:
        briefs, error = {}, type(exc).__name__
    if not isinstance(briefs, dict):
        briefs, error = {}, 'InvalidSummaryResponse'
    for record in needing:
        accept_brief(record, briefs.get(record['id']))
    ready = [r for r in selected if r.get('status') in ('ready', 'title_only')]
    batches = render_batches(ready)
    report = {'selected': len(selected), 'ready': len(ready), 'sent': 0,
              'deferred': len(records) - len(selected), 'quality_pending': len(selected) - len(ready),
              'rejected': rejected, 'errors': [error] if error else [],
              'preview': [text for text, _ in batches]}
    if dry_run:
        return report
    checkpoint(seen, state)
    for text, articles in batches:
        try:
            if send(text) is not True:
                report['errors'].append('DeliveryNotConfirmed')
                break
        except Exception as exc:
            report['errors'].append(type(exc).__name__)
            break
        for record in articles:
            for source, item_id in record['members']:
                ids = seen.setdefault(source, [])
                if item_id not in ids:
                    ids.append(item_id)
            state['delivered_urls'].append(record['link'])
            del state['pending'][record['link']]
        state['delivered_urls'] = state['delivered_urls'][-5000:]
        report['sent'] += len(articles)
        checkpoint(seen, state)
    return report
