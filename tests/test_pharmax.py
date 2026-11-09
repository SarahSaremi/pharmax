"""Run with:  python -m unittest discover -s tests -v   (from the repo root). Synthetic data only."""
import csv
import gzip
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pharmax import pipeline, rules_fa
from pharmax.parse import load_export
from pharmax.text import pseudonym, scrub

SALT = b'unit-test-salt'


def html_msg(mid, ts, sender, text='', reply=None, media=None, forwarded=False, joined=False):
    s = f'<div class="message default clearfix{" joined" if joined else ""}" id="message{mid}">\n<div class="body">\n'
    s += f'<div class="pull_right date details" title="{ts} UTC+03:30">x</div>\n'
    if sender and not joined:
        s += f'<div class="from_name">\n{sender}\n</div>\n'
    if forwarded:
        s += '<div class="forwarded body"><div class="from_name">Other<span class="date details"> x</span></div></div>\n'
    if reply:
        s += f'<div class="reply_to details">\nIn reply to <a href="#go_to_message{reply}" onclick="return GoToMessage({reply})">this message</a>\n</div>\n'
    if media:
        s += f'<div class="media_wrap clearfix"><div class="media clearfix pull_left media_{media}"></div></div>\n'
    if text:
        s += f'<div class="text">\n{text.replace(chr(10), "<br>")}\n</div>\n'
    return s + '</div>\n</div>\n'


PAGE = ('<html><body><div class="history"><div class="message service" id="message-1"><div class="body details">8 October 2018</div></div>'
        + html_msg(1, '01.03.2021 10:00:00', 'Seller A', 'گارداسیل موجود است\nپلاویکس\nمادوپار\nتگرتول\nتماس 09123456789 @sellerx')
        + html_msg(2, '01.03.2021 10:05:00', 'Buyer B', 'نیازمند ریتالین')
        + html_msg(3, '01.03.2021 10:06:00', None, 'سلام کسی سایتوتک داره؟', joined=True)
        + html_msg(4, '01.03.2021 10:30:00', 'Seller A', 'ریتالین موجود است', reply=2)
        + html_msg(5, '02.03.2021 09:00:00', 'Deleted Account', 'متادون موجود پی وی')
        + html_msg(6, '03.03.2021 09:00:00', 'Seller A', '', media='photo')
        + html_msg(7, '03.03.2021 09:10:00', 'Buyer B', 'استخدام داروساز با تجربه')
        + html_msg(8, '04.03.2021 11:00:00', 'Seller A', 'گارداسیل موجود است\nپلاویکس\nمادوپار\nتگرتول\nتماس 09123456789 @sellerx')
        + html_msg(9, '04.03.2021 12:00:00', 'Seller A', 'گارداسیل موجود است\nپلاویکس\nمادوپار\nتگرتول\nتماس 09123456789 @sellerx')
        + '</div></body></html>')


def make_html_export(d):
    with open(os.path.join(d, 'messages.html'), 'w', encoding='utf-8') as f:
        f.write(PAGE)


class TestText(unittest.TestCase):
    def test_scrub(self):
        t = scrub('تماس ۰۹۱۲۳۴۵۶۷۸۹ یا +98 912 345 6789 @seller_x https://t.me/abc mail a.b@c.com 021-12345678')
        for bad in ('0912345', '912 345', '@seller_x', 't.me', 'a.b@c.com', '12345678'):
            self.assertNotIn(bad, t)
        for tag in ('<PHONE>', '<HANDLE>', '<URL>', '<EMAIL>'):
            self.assertIn(tag, t)

    def test_scrub_keeps_prices(self):
        self.assertIn('28500', scrub('گارداسیل 28500 تومان'))

    def test_pseudonym(self):
        self.assertEqual(pseudonym(SALT, 'x'), pseudonym(SALT, 'x'))
        self.assertNotEqual(pseudonym(SALT, 'x'), pseudonym(b'other', 'x'))
        self.assertNotIn('x', pseudonym(SALT, 'Seller A'))


class TestDocs(unittest.TestCase):
    def test_data_standard_doc_is_current(self):
        from pharmax import schema
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(root, 'docs', 'DATA_STANDARD.md'), encoding='utf-8', newline='') as f:
            on_disk = f.read().replace('\r\n', '\n')
        self.assertEqual(on_disk, schema.to_markdown(), 'run: python -m pharmax schema-doc > docs/DATA_STANDARD.md')

    def test_lexicon_ids_unique_and_variants_not_shared(self):
        from pharmax.lexicon import Lexicon
        lx = Lexicon()
        seen = {}
        for r in lx.rows.values():
            for v in r['variants'].split('|'):
                self.assertNotIn(v, seen, f'variant {v!r} in both {seen.get(v)} and {r["drug_id"]}')
                seen[v] = r['drug_id']
        self.assertTrue(all(r['flags'] == ''.join(sorted(r['flags'])) for r in lx.rows.values()))


class TestRules(unittest.TestCase):
    CASES = [
        ('نیازمند گارداسیل', 'demand'), ('سلام دوستان کسی داره؟', 'demand'), ('ریتالین خریدارم', 'demand'),
        ('مادوپار موجود است در صورت نیاز پی وی', 'supply'), ('تگرتول قیمت مناسب موجود', 'supply'),
        ('استخدام داروساز', 'jobs'), ('ک' * 3, 'other'),
    ]

    def test_classify(self):
        for text, role in self.CASES:
            self.assertEqual(rules_fa.classify(text)[0], role, text)

    def test_neutral_phrase_is_not_demand(self):
        self.assertEqual(rules_fa.classify('پلاویکس موجود درصورت نیاز پی وی')[0], 'supply')

    def test_normalize_unifies_variants(self):
        self.assertEqual(rules_fa.normalize('ريتالين ٥'), rules_fa.normalize('ریتالین ۵'))

    def test_items_strip_forms_and_numbers(self):
        items = rules_fa.clean_items('شربت دپاکین ۵۰۰\nقرص مادوپار ۱۲۵\nموجود')
        self.assertIn('دپاکین', items)
        self.assertIn('مادوپار', items)


PAGE2 = ('<html><body><div class="history">'
         + html_msg(1, '05.03.2021 10:00:00', 'Seller A', 'گارداسیل موجود است\nمادوپار')   # same person as in channel 1
         + html_msg(2, '05.03.2021 10:05:00', 'Buyer C', 'نیازمند ریتالین')
         + html_msg(3, '06.03.2021 10:05:00', 'Seller D', 'متادون موجود پی وی')
         + '</div></body></html>')


class TestParseAndPipeline(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.inp = os.path.join(self.tmp.name, 'export')
        os.makedirs(self.inp)
        make_html_export(self.inp)

    def tearDown(self):
        self.tmp.cleanup()

    def test_parse_html(self):
        msgs, key_type = load_export(self.inp, workers=1)
        self.assertEqual(key_type, 'display_name')
        by = {m['msg_id']: m for m in msgs}
        self.assertEqual(len(by), 9)  # service message skipped
        self.assertEqual(by[1]['ts_local'], '2021-03-01T10:00:00')
        self.assertEqual(by[1]['ts_utc'], '2021-03-01T06:30:00')
        self.assertIsNone(by[3]['sender_key'])  # joined
        self.assertEqual(by[4]['reply_to_id'], 2)
        self.assertEqual(by[6]['media_type'], 'photo')
        self.assertEqual(by[6]['text'], '')

    def out(self, *p):
        return os.path.join(self.tmp.name, 'data', *p)

    def run_pipeline(self, inp=None, cid='chT', **kw):
        return pipeline.run(inp or self.inp, cid, os.path.join(self.tmp.name, 'data'), SALT, workers=1, log=lambda *_: None, **kw)

    def pool(self, **kw):
        return pipeline.pool(self.out('restricted'), self.out('public'), log=lambda *_: None, **kw)

    def rows(self, path):
        op = gzip.open if path.endswith('.gz') else open
        with op(path, 'rt', encoding='utf-8', newline='') as f:
            return list(csv.DictReader(f))

    def second_channel(self):
        d2 = os.path.join(self.tmp.name, 'export2')
        os.makedirs(d2)
        with open(os.path.join(d2, 'messages.html'), 'w', encoding='utf-8') as f:
            f.write(PAGE2)
        self.run_pipeline(d2, 'chU')

    def test_end_to_end(self):
        self.run_pipeline()
        msgs = {int(r['msg_id']): r for r in self.rows(self.out('restricted/chT/messages.csv.gz'))}
        self.assertEqual(msgs[1]['role'], 'supply')
        self.assertEqual(msgs[2]['role'], 'demand')
        self.assertEqual(msgs[3]['sender_pid'], msgs[2]['sender_pid'])      # joined message inherits sender
        self.assertEqual(msgs[3]['role'], 'demand')
        self.assertEqual(msgs[5]['sender_pid'], 'DELETED')
        self.assertEqual(msgs[5]['sender_is_deleted'], '1')
        self.assertEqual(msgs[6]['media_type'], 'photo')
        self.assertEqual(msgs[7]['role'], 'jobs')
        self.assertEqual([msgs[i]['is_repeat'] for i in (1, 8, 9)], ['0', '1', '1'])  # re-posts flagged
        dmc = {(r['month'], r['role'], r['drug_id']): r for r in self.rows(self.out('restricted/chT/drug_month_counts.csv'))}
        g = dmc[('2021-03', 'supply', 'vaccines_gardasil_flu_other')]
        self.assertEqual((g['n_senders'], g['n_messages'], g['n_messages_dedup']), ('1', '3', '1'))  # spam collapsed to 1 sender
        r = dmc[('2021-03', 'demand', 'methylphenidate_ritalin_etc')]
        self.assertEqual(r['n_replied'], '1')  # msg 2 was answered by msg 4
        summ = {r['month']: r for r in self.rows(self.out('restricted/chT/monthly_summary.csv'))}
        self.assertEqual(summ['2021-03']['n_media_only'], '1')
        self.assertEqual(summ['2021-03']['n_jobs'], '1')
        self.assertFalse(os.path.exists(self.out('public')))  # run never writes to the public tier

    def test_pool_counts_shared_sender_once_across_channels(self):
        self.run_pipeline()
        self.second_channel()
        self.pool(k=1, k_sensitive=1)
        cells = {(r['month'], r['role'], r['drug_id']): r for r in self.rows(self.out('public/pooled_drug_month_counts.csv'))}
        g = cells[('2021-03', 'supply', 'vaccines_gardasil_flu_other')]
        self.assertEqual((g['n_senders'], g['n_channels']), ('1', '2'))   # Seller A is one person in both channels
        self.assertEqual(g['n_messages'], '4')                            # messages are disjoint: 3 + 1
        r = cells[('2021-03', 'demand', 'methylphenidate_ritalin_etc')]
        self.assertEqual((r['n_senders'], r['n_channels']), ('2', '2'))   # Buyer B + Buyer C
        summ = {r['month']: r for r in self.rows(self.out('public/pooled_monthly_summary.csv'))}
        self.assertEqual(summ['2021-03']['n_channels'], '2')
        self.assertEqual(summ['2021-03']['n_messages'], '12')             # 9 + 3

    def test_thresholds_ordinary_vs_sensitive(self):
        self.run_pipeline()
        self.second_channel()
        meta = self.pool(k=1, k_sensitive=5)
        cells = {(r['month'], r['role'], r['drug_id']) for r in self.rows(self.out('public/pooled_drug_month_counts.csv'))}
        self.assertIn(('2021-03', 'supply', 'vaccines_gardasil_flu_other'), cells)   # ordinary, 1 sender, k=1 -> kept
        self.assertNotIn(('2021-03', 'supply', 'methadone'), cells)                  # flag C, <5 senders -> dropped
        self.assertGreater(meta['n_cells_suppressed_sensitive'], 0)
        self.pool(k=2, k_sensitive=1)
        cells = {(r['month'], r['role'], r['drug_id']) for r in self.rows(self.out('public/pooled_drug_month_counts.csv'))}
        self.assertNotIn(('2021-03', 'supply', 'vaccines_gardasil_flu_other'), cells)  # 1 sender < k=2
        self.assertIn(('2021-03', 'demand', 'methylphenidate_ritalin_etc'), cells)     # 2 senders >= k=2
        self.assertIn(('2021-03', 'supply', 'methadone'), cells)                       # k_sensitive=1

    def test_public_tier_has_no_identifiers(self):
        self.run_pipeline(include_text=True)
        self.second_channel()
        self.pool(k=1, k_sensitive=1)
        blob = ''
        for root, _, files in os.walk(self.out()):
            for fn in files:
                p = os.path.join(root, fn)
                op = gzip.open if fn.endswith('.gz') else open
                with op(p, 'rt', encoding='utf-8') as f:
                    text = f.read()
                for secret in ('Seller A', 'Buyer B', '09123456789', 'sellerx', SALT.decode()):
                    self.assertNotIn(secret, text, f'{secret!r} leaked into {p}')   # nowhere, restricted tier included
                if os.sep + 'public' + os.sep in p:
                    blob += text
        import re
        self.assertIsNone(re.search(r'u_[0-9a-f]{12}', blob))   # no pseudonymous sender ids in the public tier
        self.assertNotIn('chT', blob)          # no channel codes either
        self.assertNotIn('chU', blob)

    def test_pool_refuses_lexicon_mismatch(self):
        self.run_pipeline()
        alt = os.path.join(self.tmp.name, 'other_lexicon.csv')
        src = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'lexicon', 'drug_lexicon.csv')
        with open(src, encoding='utf-8', newline='') as f:
            content = f.read()
        with open(alt, 'w', encoding='utf-8', newline='') as f:
            f.write(content + '\n')
        with self.assertRaises(SystemExit):
            self.pool(lexicon_path=alt)

    def test_validate(self):
        self.run_pipeline(include_text=True)
        self.second_channel()
        self.pool()
        self.assertEqual(pipeline.validate(self.out('restricted/chT')), [])
        self.assertEqual(pipeline.validate(self.out('public')), [])

    def test_dataset_card_is_generated_from_public_files_only(self):
        self.run_pipeline()
        self.second_channel()
        self.pool(k=1, k_sensitive=5)
        with open(self.out('public/README.md'), encoding='utf-8') as f:
            card = f.read()
        self.assertIn('Channels pooled | 2', card)
        self.assertIn('Period | 2021-03 to 2021-03', card)
        for leak in ('chT', 'chU', 'Seller A', 'Buyer B', 'sellerx'):
            self.assertNotIn(leak, card)
        import re
        self.assertIsNone(re.search(r'u_[0-9a-f]{12}', card))
        self.assertEqual(pipeline.validate(self.out('public')), [])

    def test_json_export(self):
        d = os.path.join(self.tmp.name, 'jexport')
        os.makedirs(d)
        data = {'name': 'x', 'messages': [
            {'id': 1, 'type': 'message', 'date': '2021-03-01T10:00:00', 'from': 'A', 'from_id': 'user1', 'text': 'گارداسیل موجود است'},
            {'id': 2, 'type': 'message', 'date': '2021-03-01T10:05:00', 'from': 'B', 'from_id': 'user2',
             'text': [{'type': 'plain', 'text': 'نیازمند '}, {'type': 'bold', 'text': 'ریتالین'}]},
            {'id': 3, 'type': 'message', 'date': '2021-03-01T10:06:00', 'from': 'A', 'from_id': 'user1', 'text': '',
             'photo': 'p.jpg', 'reply_to_message_id': 2},
            {'id': 4, 'type': 'service', 'date': '2021-03-01T10:07:00', 'text': ''}]}
        with open(os.path.join(d, 'result.json'), 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False)
        msgs, key_type = load_export(d, tz='+03:30')
        self.assertEqual(key_type, 'user_id')
        self.assertEqual(len(msgs), 3)
        self.assertEqual(msgs[1]['text'], 'نیازمند ریتالین')
        self.assertEqual(msgs[2]['media_type'], 'photo')
        self.assertEqual(msgs[0]['ts_utc'], '2021-03-01T06:30:00')


class TestLexiconIndex(unittest.TestCase):
    def test_index_equals_bruteforce(self):
        from pharmax.lexicon import Lexicon
        lx = Lexicon(normalize=rules_fa.normalize)
        probes = set()
        for words, variant, _ in lx._pats:
            probes.update({variant, 'xx ' + variant, variant + ' yy', 'xx ' + variant + ' yy', variant.split()[0]})
            probes.add(variant + ' ' + lx._pats[len(probes) % len(lx._pats)][1])  # two drugs in one item
        probes.update({'', 'unknownword', 'اکسی کدون', 'اکسی'})
        for item in probes:
            self.assertEqual(lx.lookup(item), lx.lookup_bruteforce(item), item)
        self.assertEqual(lx.lookup('اکسی کدون')[0], 'oxycodone')   # longest variant wins


if __name__ == '__main__':
    unittest.main()
