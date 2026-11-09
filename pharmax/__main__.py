import argparse
import os
import secrets
import sys

from . import pipeline


def main(argv=None):
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    ap = argparse.ArgumentParser(prog='pharmax', description='Telegram drug-exchange group -> standard research dataset')
    sub = ap.add_subparsers(dest='cmd', required=True)

    r = sub.add_parser('run', help='process one channel export')
    r.add_argument('--input', required=True, help='export directory (messages*.html or result.json)')
    r.add_argument('--channel-id', required=True, help='project code such as ch001 (do not use the real channel name)')
    r.add_argument('--salt-file', default='config/.salt', help='secret salt for sender pseudonyms (never commit)')
    r.add_argument('--out', default='data', help='output root (default: data)')
    r.add_argument('--lang', default='fa', choices=sorted(pipeline.LANGS))
    r.add_argument('--tz', default='+00:00', help='UTC offset for JSON exports without offsets, e.g. +03:30 (HTML exports carry it)')
    r.add_argument('--include-text', action='store_true', help='also write PII-scrubbed texts (restricted tier)')
    r.add_argument('--workers', type=int, default=8)
    r.add_argument('--lexicon', default=None)

    s = sub.add_parser('init-salt', help='create a random secret salt file')
    s.add_argument('path', nargs='?', default='config/.salt')

    v = sub.add_parser('validate', help='check an output directory against the schema')
    v.add_argument('path')

    m = sub.add_parser('pool', help='pool all channels into the public tier (distinct senders across channels, then suppress small cells)')
    m.add_argument('--restricted', default='data/restricted')
    m.add_argument('--public', default='data/public')
    m.add_argument('--k', type=int, default=1, help='min distinct senders per cell for ordinary drugs (1 = no suppression)')
    m.add_argument('--k-sensitive', type=int, default=5, help='min distinct senders per cell for drugs with a sensitive flag')
    m.add_argument('--sensitive-flags', default='CAX', help='lexicon flag letters treated as sensitive')
    m.add_argument('--lexicon', default=None)

    d = sub.add_parser('schema-doc', help='print the data standard as Markdown (used to generate docs/DATA_STANDARD.md)')

    a = ap.parse_args(argv)
    if a.cmd == 'schema-doc':
        from . import schema
        sys.stdout.write(schema.to_markdown())
    elif a.cmd == 'init-salt':
        if os.path.exists(a.path):
            raise SystemExit(f'{a.path} exists; refusing to overwrite (changing the salt breaks pseudonym continuity)')
        os.makedirs(os.path.dirname(a.path) or '.', exist_ok=True)
        with open(a.path, 'w') as f:
            f.write(secrets.token_hex(32))
        print(f'wrote {a.path}. Keep it secret and backed up; it is git-ignored.')
    elif a.cmd == 'run':
        pipeline.run(a.input, a.channel_id, a.out, pipeline.read_salt(a.salt_file), a.lang, a.tz,
                     a.include_text, a.workers, a.lexicon)
    elif a.cmd == 'validate':
        probs = pipeline.validate(a.path)
        print('OK: conforms to schema' if not probs else '\n'.join(probs))
        raise SystemExit(1 if probs else 0)
    elif a.cmd == 'pool':
        pipeline.pool(a.restricted, a.public, a.k, a.k_sensitive, a.sensitive_flags, a.lexicon)


if __name__ == '__main__':
    main()
