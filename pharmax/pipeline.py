"""End-to-end pipeline: export dir -> standard tables (restricted + public tiers)."""
import csv
import gzip
import hashlib
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone

from . import SCHEMA_VERSION, __version__, rules_fa
from .aggregate import monthly_summary
from .lexicon import DEFAULT_PATH, Lexicon
from .parse import load_export
from .schema import TABLES, columns
from .text import pseudonym, scrub, text_hash

LANGS = {'fa': rules_fa}
MIN_TEXT = 3  # messages with fewer characters are treated as having no text


def write_csv(path, table, rows):
    cols = columns(table)
    opener = (lambda p: gzip.open(p, 'wt', encoding='utf-8', newline='')) if path.endswith('.gz') \
        else (lambda p: open(p, 'w', encoding='utf-8', newline=''))
    with opener(path) as f:
        w = csv.writer(f)
        w.writerow(cols)
        for r in rows:
            w.writerow(['' if r.get(c) is None else r.get(c) for c in cols])


def _sha1_file(path):
    with open(path, 'rb') as f:
        return hashlib.sha1(f.read()).hexdigest()[:12]


def read_salt(path):
    if not os.path.exists(path):
        raise SystemExit(f'Salt file {path} not found. Create one with: python -m pharmax init-salt {path}')
    with open(path, 'rb') as f:
        return f.read().strip()


class _DrugAcc:
    """Accumulates drug_month_counts from the *full* mention stream (before sender-month de-dup)."""

    def __init__(self, channel_id):
        self.cid = channel_id
        self.s, self.m, self.d, self.r = (defaultdict(set) for _ in range(4))

    def add(self, month, role, drug_id, pid, msg_id, thash, replied):
        k = (month, role, drug_id)
        self.s[k].add(pid)
        self.m[k].add(msg_id)
        self.d[k].add((pid, thash))
        if replied:
            self.r[k].add(msg_id)

    def rows(self):
        return [{'channel_id': self.cid, 'month': k[0], 'role': k[1], 'drug_id': k[2], 'n_senders': len(self.s[k]),
                 'n_messages': len(self.m[k]), 'n_messages_dedup': len(self.d[k]), 'n_replied': len(self.r[k])}
                for k in sorted(self.s)]


def run(input_dir, channel_id, out_root, salt, lang='fa', tz='+00:00', include_text=False,
        workers=8, lexicon_path=None, log=print):
    L = LANGS[lang]
    lex = Lexicon(lexicon_path or DEFAULT_PATH, L.normalize)
    log(f'[1/5] reading {input_dir}')
    raw, key_type = load_export(input_dir, tz, workers)
    raw.sort(key=lambda m: m['msg_id'])
    replied_ids = {m['reply_to_id'] for m in raw if m['reply_to_id']}
    log(f'      {len(raw):,} messages')

    log('[2/5] classifying and extracting items')
    msgs, texts = [], []
    acc = _DrugAcc(channel_id)
    ment = {}  # (pid, month, role, item) -> [first_msg_id, n_posts, drug_id, variant]
    seen_rep, last = set(), None
    for m in raw:
        if m['sender_key'] is None:
            m['sender_key'] = last
        else:
            last = m['sender_key']
        key = m['sender_key']
        deleted = key == 'Deleted Account'
        pid = 'DELETED' if deleted else (pseudonym(salt, key) if key else 'UNKNOWN')
        text, month = m['text'], m['ts_local'][:7]
        has_text = len(text) >= MIN_TEXT
        if has_text:
            norm = L.normalize(text)
            thash = text_hash(norm)
            role, rule = L.classify(text)
            items = L.clean_items(text)
            if role == 'other' and len(items) >= 4 and '?' not in text and '؟' not in text:
                role, rule = 'supply', 'item_list'
            rk = (pid, thash, month)
            is_rep = 1 if rk in seen_rep else 0
            seen_rep.add(rk)
        else:
            thash, role, rule, items, is_rep = '', 'other', 'no_text', [], 0
        msgs.append({
            'channel_id': channel_id, 'msg_id': m['msg_id'], 'ts_local': m['ts_local'], 'ts_utc': m['ts_utc'], 'month': month,
            'sender_pid': pid, 'sender_is_deleted': int(deleted), 'is_forwarded': m['is_forwarded'],
            'reply_to_id': m['reply_to_id'], 'media_type': m['media_type'], 'text_len': len(text), 'role': role,
            'role_rule': rule, 'n_items': len(items), 'text_hash': thash, 'is_repeat': is_rep})
        if include_text and has_text:
            texts.append({'channel_id': channel_id, 'msg_id': m['msg_id'], 'text_scrubbed': scrub(text)})
        if role != 'jobs':
            for it in items:
                drug_id, variant = lex.lookup(it)
                if drug_id:
                    acc.add(month, role, drug_id, pid, m['msg_id'], thash, m['msg_id'] in replied_ids)
                mk = (pid, month, role, it)
                if mk in ment:
                    ment[mk][1] += 1
                else:
                    ment[mk] = [m['msg_id'], 1, drug_id, variant]

    log('[3/5] aggregating')
    summary = monthly_summary(channel_id, msgs)
    dmc_full = acc.rows()
    unmatched = defaultdict(lambda: [set(), 0])
    mention_rows = []
    for (pid, month, role, it), (mid, n, drug_id, variant) in ment.items():
        mention_rows.append({'channel_id': channel_id, 'msg_id': mid, 'month': month, 'sender_pid': pid, 'role': role,
                             'item_norm': it, 'drug_id': drug_id or '', 'variant': variant or '', 'n_posts': n})
        if not drug_id:
            unmatched[it][0].add(pid)
            unmatched[it][1] += n
    unmatched_rows = [{'channel_id': channel_id, 'item_norm': it, 'n_senders': len(v[0]), 'n_messages': v[1]}
                      for it, v in unmatched.items() if len(v[0]) >= 3]
    unmatched_rows.sort(key=lambda r: -r['n_senders'])

    log('[4/5] writing')
    rdir = os.path.join(out_root, 'restricted', channel_id)
    os.makedirs(rdir, exist_ok=True)
    write_csv(os.path.join(rdir, 'messages.csv.gz'), 'messages', msgs)
    write_csv(os.path.join(rdir, 'mentions.csv.gz'), 'mentions', mention_rows)
    write_csv(os.path.join(rdir, 'unmatched_items.csv'), 'unmatched_items', unmatched_rows)
    write_csv(os.path.join(rdir, 'drug_month_counts.csv'), 'drug_month_counts', dmc_full)
    if include_text:
        write_csv(os.path.join(rdir, 'texts_scrubbed.csv.gz'), 'texts_scrubbed', texts)
    write_csv(os.path.join(rdir, 'monthly_summary.csv'), 'monthly_summary', summary)

    roles = defaultdict(int)
    for r in msgs:
        roles[r['role']] += 1
    meta = {
        'channel_id': channel_id, 'schema_version': SCHEMA_VERSION, 'pipeline_version': __version__,
        'rules_version': L.RULES_VERSION, 'language': lang,
        'lexicon_sha1': _sha1_file(lex.path), 'lexicon_n_drugs': len(lex.rows),
        'export_format': 'html' if key_type == 'display_name' else 'json', 'sender_key_type': key_type, 'tz': tz,
        'n_messages': len(msgs), 'first_message': msgs[0]['ts_local'] if msgs else None,
        'last_message': msgs[-1]['ts_local'] if msgs else None, 'roles': dict(roles),
        'n_distinct_senders': len({r['sender_pid'] for r in msgs}), 'text_included': bool(include_text),
        'generated_at': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
    }
    with open(os.path.join(rdir, 'channel_meta.json'), 'w', encoding='utf-8') as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)
    log('[5/5] done: ' + json.dumps({'messages': len(msgs), 'roles': dict(roles), 'drug_month_rows': len(dmc_full)}))
    return meta


def _read_rows(path):
    f = gzip.open(path, 'rt', encoding='utf-8', newline='') if path.endswith('.gz') else open(path, encoding='utf-8', newline='')
    with f:
        yield from csv.DictReader(f)


def pool(restricted_root, public_root, k=1, k_sensitive=5, sensitive_flags='CAX', lexicon_path=None, log=print):
    """Pool all channels in `restricted_root` into the public tier.

    Distinct senders are counted across channels (needs one shared salt), then cells below the threshold are
    removed: `k` for ordinary drugs, `k_sensitive` for drugs whose lexicon flags intersect `sensitive_flags`.
    Per-channel numbers are never published."""
    chans = sorted(d for d in os.listdir(restricted_root)
                   if not d.startswith('_') and os.path.isfile(os.path.join(restricted_root, d, 'channel_meta.json')))
    if not chans:
        raise SystemExit(f'No processed channels found in {restricted_root}. Run `pharmax run` first.')
    metas = {}
    for c in chans:
        with open(os.path.join(restricted_root, c, 'channel_meta.json'), encoding='utf-8') as f:
            metas[c] = json.load(f)
    lex_path = lexicon_path or DEFAULT_PATH
    lex_sha = _sha1_file(lex_path)
    stale = [c for c in chans if metas[c]['lexicon_sha1'] != lex_sha]
    if stale:
        raise SystemExit(f'Channels {stale} were processed with a different lexicon than the current file. '
                         'Re-run them so every channel uses the same lexicon before pooling.')
    if len({m['schema_version'] for m in metas.values()}) > 1:
        raise SystemExit('Channels were produced with different schema versions; re-run them.')
    if len(chans) < 2:
        log('WARNING: only one channel - pooling gives no dilution of small cells; do not publish yet.')
    kinds = {m['sender_key_type'] for m in metas.values()}
    if len(kinds) > 1:
        log(f'WARNING: mixed sender key types {sorted(kinds)}: senders can only be linked across channels of the same type.')
    lex = Lexicon(lex_path)
    sensitive = {d for d, r in lex.rows.items() if set(r['flags']) & set(sensitive_flags)}

    cell_senders, cell_chans = defaultdict(set), defaultdict(set)
    cell_sum = defaultdict(lambda: [0, 0, 0])
    sums = defaultdict(lambda: defaultdict(int))
    mon_senders = defaultdict(set)
    mon_sup, mon_dem, mon_chans = defaultdict(set), defaultdict(set), defaultdict(set)
    all_senders, rows_matched, rows_total = set(), 0, 0
    sum_cols = ['n_messages', 'n_with_text', 'n_supply', 'n_demand', 'n_mixed', 'n_other', 'n_jobs', 'n_media_only', 'n_deleted_msgs']
    for c in chans:
        base = os.path.join(restricted_root, c)
        log(f'pooling {c}')
        for r in _read_rows(os.path.join(base, 'mentions.csv.gz')):
            rows_total += 1
            if r['drug_id']:
                rows_matched += 1
                key = (r['month'], r['role'], r['drug_id'])
                cell_senders[key].add(r['sender_pid'])
                cell_chans[key].add(c)
        for r in _read_rows(os.path.join(base, 'drug_month_counts.csv')):
            v = cell_sum[(r['month'], r['role'], r['drug_id'])]
            v[0] += int(r['n_messages'])
            v[1] += int(r['n_messages_dedup'])
            v[2] += int(r['n_replied'])
        for r in _read_rows(os.path.join(base, 'messages.csv.gz')):
            mon_senders[r['month']].add(r['sender_pid'])
            all_senders.add(r['sender_pid'])
            mon_chans[r['month']].add(c)
            if int(r['text_len'] or 0) >= MIN_TEXT:
                if r['role'] == 'supply':
                    mon_sup[r['month']].add(r['sender_pid'])
                elif r['role'] == 'demand':
                    mon_dem[r['month']].add(r['sender_pid'])
        for r in _read_rows(os.path.join(base, 'monthly_summary.csv')):
            for col in sum_cols:
                sums[r['month']][col] += int(r[col])

    summary = [dict({'month': m, 'n_channels': len(mon_chans[m]), 'n_senders': len(mon_senders[m]),
                     'n_senders_supply': len(mon_sup[m]), 'n_senders_demand': len(mon_dem[m])}, **sums[m]) for m in sorted(sums)]
    cells, dropped, dropped_sensitive = [], 0, 0
    for key in sorted(cell_senders):
        n = len(cell_senders[key])
        is_sens = key[2] in sensitive
        if n < (k_sensitive if is_sens else k):
            dropped += 1
            dropped_sensitive += is_sens
            continue
        v = cell_sum[key]
        cells.append({'month': key[0], 'role': key[1], 'drug_id': key[2], 'n_channels': len(cell_chans[key]), 'n_senders': n,
                      'n_messages': v[0], 'n_messages_dedup': v[1], 'n_replied': v[2]})
    os.makedirs(public_root, exist_ok=True)
    write_csv(os.path.join(public_root, 'pooled_monthly_summary.csv'), 'pooled_monthly_summary', summary)
    write_csv(os.path.join(public_root, 'pooled_drug_month_counts.csv'), 'pooled_drug_month_counts', cells)
    write_csv(os.path.join(public_root, 'lexicon.csv'), 'lexicon', [dict(r) for r in lex.rows.values()])
    meta = {'schema_version': SCHEMA_VERSION, 'pipeline_version': __version__, 'lexicon_sha1': lex_sha,
            'n_channels': len(chans), 'rules_versions': sorted({m['rules_version'] for m in metas.values()}),
            'n_distinct_named_senders': len(all_senders - {'DELETED', 'UNKNOWN'}),
            'item_match_rate': round(rows_matched / rows_total, 4) if rows_total else 0,
            'languages': sorted({m['language'] for m in metas.values()}),
            'sender_key_types': sorted(kinds), 'first_month': summary[0]['month'] if summary else None,
            'last_month': summary[-1]['month'] if summary else None, 'k': k, 'k_sensitive': k_sensitive,
            'sensitive_flags': sensitive_flags, 'n_cells_total': len(cells) + dropped, 'n_cells_suppressed': dropped,
            'n_cells_suppressed_sensitive': dropped_sensitive,
            'generated_at': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}
    with open(os.path.join(public_root, 'pooled_meta.json'), 'w', encoding='utf-8') as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)
    from .card import write_card
    write_card(public_root)
    log(f'pooled {len(chans)} channel(s): {len(cells):,} cells published, {dropped:,} suppressed ({dropped_sensitive:,} sensitive)')
    return meta


def validate(path):
    """Check CSV headers/types of a channel output directory against the schema. Returns list of problems."""
    problems = []
    names = {'messages': 'messages.csv.gz', 'mentions': 'mentions.csv.gz', 'texts_scrubbed': 'texts_scrubbed.csv.gz',
             'unmatched_items': 'unmatched_items.csv', 'monthly_summary': 'monthly_summary.csv',
             'drug_month_counts': 'drug_month_counts.csv', 'lexicon': 'lexicon.csv',
             'pooled_monthly_summary': 'pooled_monthly_summary.csv', 'pooled_drug_month_counts': 'pooled_drug_month_counts.csv'}
    found = 0
    for table, fn in names.items():
        p = os.path.join(path, fn)
        if not os.path.exists(p):
            continue
        found += 1
        f = gzip.open(p, 'rt', encoding='utf-8', newline='') if p.endswith('.gz') else open(p, encoding='utf-8', newline='')
        with f:
            rd = csv.reader(f)
            head = next(rd, [])
            if head != columns(table):
                problems.append(f'{fn}: header mismatch {head} != {columns(table)}')
                continue
            types = {c[0]: c[1] for c in TABLES[table][1]}
            for i, row in enumerate(rd):
                if i >= 20000:
                    break
                for c, v in zip(head, row):
                    if v == '':
                        continue
                    t = types[c]
                    try:
                        if t == 'int':
                            int(v)
                        elif t == 'float':
                            float(v)
                        elif t == 'month':
                            assert len(v) == 7 and v[4] == '-'
                    except Exception:
                        problems.append(f'{fn} row {i + 2}: column {c} bad {t} value {v!r}')
                        break
    if found == 0:
        problems.append(f'no known tables found in {path}')
    return problems
