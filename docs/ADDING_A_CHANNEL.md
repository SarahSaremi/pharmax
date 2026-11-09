# Adding a channel / group

Follow this checklist for every new Telegram export so all channels end up in the same standard and are comparable.

## 1. Export correctly

In Telegram Desktop: *Export chat history*. Prefer **JSON** (`result.json`): it contains stable user ids (better sender
counts), reply ids and media types. HTML also works (`messages*.html`). Photos/files are not needed; keep the export
**outside this repository**. Export one chat at a time (multi-chat `result.json` files are not supported).

## 2. Assign a channel code

Pick the next free code (`ch002`, `ch003`, ...). Record `code, real name, language, timezone offset, export format, export date`
in `config/channels.private.csv` (git-ignored). Never use the real name in outputs or file names.

## 3. Create the salt once per project

```bash
python -m pharmax init-salt config/.salt     # refuses to overwrite an existing salt
```

Use the same salt for all channels if JSON user ids should link senders across channels.

## 4. Run

```bash
python -m pharmax run --input /path/to/export --channel-id ch002 --tz +03:30
python -m pharmax validate data/restricted/ch002
```

`--tz` is only needed for JSON (HTML carries the offset). Use `--lang` for a language other than Persian (see 6).

## 5. QA before anything is published (mandatory)

1. Draw 100 random messages per role (`supply`, `demand`) and 50 for `mixed`/`other` from the restricted tier
   (`messages.csv.gz` joined with `texts_scrubbed.csv.gz`, run with `--include-text`).
2. A second person labels them blind; compute precision per role and note disagreements.
3. Check the 30 most common matched drugs: are the top mentions plausible, or is a brand colliding with an ordinary word?
4. Read `restricted/<ch>/unmatched_items.csv` (top 100) and add missing drugs to `lexicon/drug_lexicon.csv`.
5. Write the findings to `docs/qa/ch002.md` (precision per role, lexicon coverage = matched / all items, image-only share
   from `monthly_summary.n_media_only`, anything odd such as spam bursts).
6. If the lexicon changed, re-run **all** channels so every channel uses the same `lexicon_sha1`, and bump `lexicon/VERSION`.

## 6. Different language or very different slang

Copy `pharmax/rules_fa.py` to `pharmax/rules_<lang>.py`, implement `normalize`, `classify`, `clean_items`, set `LANG` and
`RULES_VERSION`, and register it in `pipeline.LANGS`. Add a language-specific lexicon column set if brand names differ
(variants for the same `drug_id` can live in one row; keep the `drug_id` stable across languages). Add unit tests with
synthetic messages and complete step 5 from scratch: precision from one language does not transfer.

## 7. Pool and commit

```bash
python -m pharmax pool --k 1 --k-sensitive 5   # all channels -> data/public/ ; distinct senders counted ACROSS channels
python -m pharmax validate data/public
git add data/public docs lexicon
git status                       # confirm nothing under data/restricted or config/.salt is staged
```

Then complete the release checklist in [PRIVACY_AND_ETHICS.md](PRIVACY_AND_ETHICS.md).
