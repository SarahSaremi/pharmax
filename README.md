# pharmax

A pipeline and a **data standard** for studying drug supply and demand in Telegram pharmacy-exchange groups.
Give it Telegram exports; it produces (a) pseudonymised per-channel tables for researchers (restricted) and (b) tables **pooled
across all channels** and threshold-suppressed, which can be published without identifying any single channel.

> **Status: v0.1 (draft).** Built on one Persian-language channel. The lexicon is unreviewed by a pharmacist, role rules
> are validated only by a small informal spot check, and no licence has been chosen yet. Read
> [docs/METHODOLOGY.md](docs/METHODOLOGY.md) (limitations) and [docs/PRIVACY_AND_ETHICS.md](docs/PRIVACY_AND_ETHICS.md) before using or publishing anything.

## What it extracts from each channel

| Question | Where to find it |
|---|---|
| How active is the channel, who posts, how concentrated is re-posting? | `monthly_summary` (per channel, restricted) / `pooled_monthly_summary` (public) |
| Which drugs are offered / requested, and how does it change over time? | `drug_month_counts` (per channel, restricted) / `pooled_drug_month_counts` (public) |
| Which messages are supply, demand, job ads, other - and why? | `messages.role`, `messages.role_rule` |
| Do requests get answered? | `n_replied` in the drug-month tables, `messages.reply_to_id` |
| Sensitive categories (controlled, obstetric/abortifacient-related, rare-disease, COVID-era, unlicensed enhancers) | lexicon `flags` |
| How much is invisible to text analysis (image-only ads)? | `monthly_summary.n_media_only` |
| What drugs are we missing? | `unmatched_items` (restricted) |

**Counting unit.** Everything is counted in *distinct senders per month*, not messages, because a few accounts re-post
the same catalogue thousands of times. Raw and de-duplicated message counts are also provided.

## Quick start

Requires Python >= 3.9, no third-party packages.

```bash
python -m pharmax init-salt config/.salt                       # once per project; secret, git-ignored
python -m pharmax run --input /path/to/telegram-export \
       --channel-id ch001 --tz +03:30                         # per channel; add --include-text for scrubbed texts (restricted)
python -m pharmax validate data/restricted/ch001              # check against the schema
python -m pharmax pool --k 1 --k-sensitive 5                  # pool ALL channels -> data/public/ (distinct senders across channels)
python -m pharmax validate data/public
python -m unittest discover -s tests -v                       # tests (synthetic data only)
```

Supports Telegram Desktop **HTML** (`messages*.html`) and **JSON** (`result.json`, recommended) exports.
The HTML reader is tested on a real 500k-message export; the JSON reader is tested on a synthetic fixture only.

## Repository layout

```
pharmax/            package: parse, language pack (rules_fa), lexicon loader, aggregation, pipeline, CLI, schema
lexicon/            drug_lexicon.csv  - reviewable, versioned drug / brand / spelling-variant dictionary
docs/               DATA_STANDARD.md (generated), METHODOLOGY.md, PRIVACY_AND_ETHICS.md, ADDING_A_CHANNEL.md
tests/              unit + end-to-end tests on synthetic exports
data/public/        pooled tables, no channel ids (committed)
data/restricted/<ch>/ all per-channel tables, row-level and aggregate (git-ignored, never published)
config/             .salt and channels.private.csv (git-ignored)
```

## The standard in one screen

Three tiers (full detail in [docs/DATA_STANDARD.md](docs/DATA_STANDARD.md), generated from `pharmax/schema.py`):

- **Tier 0 raw export** - never in this repo.
- **Tier 1 restricted (per channel)** - `messages`, `mentions`, `monthly_summary`, `drug_month_counts`, `unmatched_items`,
  optional `texts_scrubbed`, `channel_meta.json`. Sender ids are `HMAC(secret salt, sender)` pseudonyms. Git-ignored.
- **Tier 2 public (pooled)** - `pooled_monthly_summary`, `pooled_drug_month_counts`, `lexicon`, `pooled_meta.json`.
  Distinct senders are counted *across* channels (one shared salt), so small cells grow as channels are added. Cells below a
  threshold are removed: `--k` (default 1, i.e. none) for ordinary drugs and `--k-sensitive` (default 5) for drugs flagged
  controlled / obstetric-abortifacient-related / unlicensed enhancer. No per-channel numbers and no channel codes are public.

`pool` refuses to run if channels were processed with different lexicons or schema versions, so every pooled number comes
from one consistent set of rules. With a single channel pooling gives no dilution and `pool` warns you.

## Adding more channels

See [docs/ADDING_A_CHANNEL.md](docs/ADDING_A_CHANNEL.md): export (prefer JSON) -> assign a code -> run -> **mandatory QA**
(blind-labelled sample, lexicon gaps) -> re-run all channels if the lexicon changed -> pool -> release checklist.

## Known limitations

Image-only ads are invisible; lexicon coverage is partial (~45% of items in the first channel); all deleted accounts share
one pseudonym; role rules are Persian-specific; a mention is not a transaction. Details in [docs/METHODOLOGY.md](docs/METHODOLOGY.md).

## Responsible use

The underlying messages come from people who did not consent to research and include sellers of controlled medicines.
Publish pooled aggregates only, keep the higher threshold for sensitive categories, never publish text, per-channel or sender-level data, and get ethics and
legal review. See [docs/PRIVACY_AND_ETHICS.md](docs/PRIVACY_AND_ETHICS.md).

## License and citation

**Not yet chosen.** Until a licence file is added, all rights are reserved. Decide separately on a code licence (e.g. MIT) and
a data licence (e.g. CC BY 4.0) before the first public release.
