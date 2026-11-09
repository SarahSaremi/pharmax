"""Readers for Telegram Desktop exports (HTML `messages*.html` and JSON `result.json`).

Both yield the same plain dicts:
  msg_id, ts_local (ISO), tz ('+03:30'), ts_utc (ISO), sender_key (str|None), is_forwarded,
  reply_to_id (int|None), media_type, text
`sender_key` is None for 'joined' HTML messages (same sender as the previous one); the pipeline
forward-fills those after sorting by msg_id.
"""
import glob
import html
import json
import os
import re
from datetime import datetime, timedelta, timezone
from multiprocessing import Pool

_SPLIT = re.compile(r'<div class="message (default|service)[^"]*" id="message(-?\d+)">')
_DATE = re.compile(r'class="pull_right date details" title="(\d\d)\.(\d\d)\.(\d{4}) (\d\d):(\d\d):(\d\d)(?: UTC([+-]\d\d:\d\d))?')
_FROM = re.compile(r'<div class="from_name">\s*(.*?)\s*(?:<span|</div>)', re.S)
_TEXT = re.compile(r'<div class="text">(.*?)</div>', re.S)
_REPLY = re.compile(r'class="reply_to details">\s*In reply to <a href="#go_to_message(\d+)"')
_MEDIA = re.compile(r'class="media clearfix pull_left (?:block_link )?media_(\w+)"')
_TAG = re.compile(r'<[^>]+>')
_MEDIA_MAP = {"photo": "photo", "video": "video", "video_file": "video", "animation": "video", "file": "file",
              "audio_file": "audio", "voice_message": "voice", "sticker": "sticker", "location": "location",
              "live_location": "location", "contact": "contact"}


def _utc(local_iso, tz):
    try:
        sign = 1 if tz[0] == '+' else -1
        hh, mm = int(tz[1:3]), int(tz[4:6])
        dt = datetime.fromisoformat(local_iso).replace(tzinfo=timezone(sign * timedelta(hours=hh, minutes=mm)))
        return dt.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S')
    except Exception:
        return ''


def _parse_html_file(path):
    with open(path, encoding='utf-8') as f:
        s = f.read()
    parts = _SPLIT.split(s)
    out = []
    for i in range(1, len(parts), 3):
        kind, mid, body = parts[i], int(parts[i + 1]), parts[i + 2]
        if kind == 'service':
            continue
        d = _DATE.search(body)
        if not d:
            continue
        dd, mm, yy, H, M, S, tz = d.groups()
        local = f"{yy}-{mm}-{dd}T{H}:{M}:{S}"
        tz = tz or '+00:00'
        fm = _FROM.search(body)
        rp = _REPLY.search(body)
        md = _MEDIA.search(body)
        texts = _TEXT.findall(body)
        text = ' \n'.join(html.unescape(_TAG.sub('', t.replace('<br>', '\n'))).strip() for t in texts)
        out.append({
            'msg_id': mid, 'ts_local': local, 'tz': tz, 'ts_utc': _utc(local, tz),
            'sender_key': html.unescape(fm.group(1)) if fm else None,
            'is_forwarded': 1 if 'class="forwarded body"' in body else 0,
            'reply_to_id': int(rp.group(1)) if rp else None,
            'media_type': _MEDIA_MAP.get(md.group(1), 'other') if md else 'none',
            'text': text,
        })
    return out


def _flatten_json_text(t):
    if isinstance(t, str):
        return t
    return ''.join(x if isinstance(x, str) else x.get('text', '') for x in t)


def _parse_json_file(path, tz):
    with open(path, encoding='utf-8') as f:
        data = json.load(f)
    out = []
    for m in data.get('messages', []):
        if m.get('type') != 'message':
            continue
        local = m['date'][:19]
        media = 'none'
        if 'photo' in m:
            media = 'photo'
        elif m.get('media_type'):
            media = _MEDIA_MAP.get({'video_file': 'video', 'voice_message': 'voice', 'audio_file': 'audio'}.get(m['media_type'], m['media_type']), 'other')
        elif 'file' in m:
            media = 'file'
        out.append({
            'msg_id': int(m['id']), 'ts_local': local, 'tz': tz, 'ts_utc': _utc(local, tz),
            'sender_key': str(m.get('from_id') or m.get('from') or '') or None,
            'is_forwarded': 1 if 'forwarded_from' in m else 0,
            'reply_to_id': m.get('reply_to_message_id'),
            'media_type': media,
            'text': _flatten_json_text(m.get('text', '')).strip(),
            '_from_name': m.get('from'),
        })
    return out


def load_export(path, tz='+00:00', workers=8):
    """Load every message of an export directory. Returns (messages, sender_key_type)."""
    html_files = sorted(glob.glob(os.path.join(path, 'messages*.html')))
    if html_files:
        if workers > 1:
            with Pool(workers) as p:
                chunks = p.map(_parse_html_file, html_files, chunksize=4)
        else:
            chunks = [_parse_html_file(f) for f in html_files]
        return [m for c in chunks for m in c], 'display_name'
    js = os.path.join(path, 'result.json')
    if os.path.exists(js):
        msgs = _parse_json_file(js, tz)
        for m in msgs:  # treat Telegram's deleted-account display name as such
            if m.pop('_from_name', None) == 'Deleted Account':
                m['sender_key'] = 'Deleted Account'
        return msgs, 'user_id'
    raise FileNotFoundError(f'No messages*.html or result.json found in {path}')
