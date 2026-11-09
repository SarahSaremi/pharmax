"""Aggregation into the public tables. The counting unit is the *sender-month*: distinct senders
per (month, role, drug). This is deliberately robust to bulk re-posting."""
from collections import defaultdict


def monthly_summary(channel_id, msgs):
    by = defaultdict(list)
    for m in msgs:
        by[m['month']].append(m)
    rows = []
    for month in sorted(by):
        ms = by[month]
        txt = [m for m in ms if m['text_len'] >= 3]
        cnt = {r: sum(1 for m in txt if m['role'] == r) for r in ('supply', 'demand', 'mixed', 'other', 'jobs')}
        sup_counts = defaultdict(int)
        for m in txt:
            if m['role'] == 'supply':
                sup_counts[m['sender_pid']] += 1
        top5 = sum(sorted(sup_counts.values(), reverse=True)[:5])
        rows.append({
            'channel_id': channel_id, 'month': month, 'n_messages': len(ms), 'n_with_text': len(txt),
            'n_supply': cnt['supply'], 'n_demand': cnt['demand'], 'n_mixed': cnt['mixed'], 'n_other': cnt['other'], 'n_jobs': cnt['jobs'],
            'n_media_only': sum(1 for m in ms if m['text_len'] < 3 and m['media_type'] != 'none'),
            'n_deleted_msgs': sum(1 for m in ms if m['sender_is_deleted']),
            'n_senders': len({m['sender_pid'] for m in ms}),
            'n_senders_supply': len({m['sender_pid'] for m in txt if m['role'] == 'supply'}),
            'n_senders_demand': len({m['sender_pid'] for m in txt if m['role'] == 'demand'}),
            'n_distinct_texts': len({m['text_hash'] for m in txt}),
            'repeat_share': round(sum(m['is_repeat'] for m in txt) / len(txt), 4) if txt else 0,
            'top5_sender_share_supply': round(top5 / cnt['supply'], 4) if cnt['supply'] else 0,
        })
    return rows
