"""Drug lexicon loader. The lexicon is a plain CSV (see schema.TABLES['lexicon']) so it can be
reviewed and edited by pharmacists in a spreadsheet and versioned in git."""
import csv
import os
from collections import defaultdict

DEFAULT_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'lexicon', 'drug_lexicon.csv')


class Lexicon:
    def __init__(self, path=DEFAULT_PATH, normalize=lambda s: s):
        self.path = path
        self.rows = {}
        pats = []
        with open(path, encoding='utf-8', newline='') as f:
            for r in csv.DictReader(f):
                self.rows[r['drug_id']] = r
                for v in r['variants'].split('|'):
                    v = normalize(v.strip())
                    if v:
                        pats.append((v.split(), v, r['drug_id']))
        # longest variants first so 'اکسی کدون' wins over 'اکسی'; rank = position in that order
        pats.sort(key=lambda x: -sum(len(w) for w in x[0]))
        self._pats = pats
        self._by_first = defaultdict(list)  # first word -> [(rank, words, variant, drug_id)]
        for rank, (words, variant, drug_id) in enumerate(pats):
            self._by_first[words[0]].append((rank, words, variant, drug_id))
        self._cache = {}

    def lookup(self, item):
        """Whole-word match of a variant inside an item. Returns (drug_id, variant) or (None, None).
        Equivalent to scanning all variants longest-first, but indexed by first word."""
        if item in self._cache:
            return self._cache[item]
        toks = item.split()
        best = None
        for i, tok in enumerate(toks):
            for rank, words, variant, drug_id in self._by_first.get(tok, ()):
                if best is not None and rank >= best[0]:
                    break  # candidates for this token are rank-ordered; nothing better follows
                if toks[i:i + len(words)] == words:
                    best = (rank, variant, drug_id)
                    break
        res = (best[2], best[1]) if best else (None, None)
        self._cache[item] = res
        return res

    def lookup_bruteforce(self, item):
        """Reference implementation used by tests to prove the index changes nothing."""
        toks = item.split()
        for words, variant, drug_id in self._pats:
            n = len(words)
            if any(toks[i:i + n] == words for i in range(len(toks) - n + 1)):
                return drug_id, variant
        return None, None

    def flags(self, drug_id):
        return self.rows[drug_id]['flags'] if drug_id in self.rows else ''
