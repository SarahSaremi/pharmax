# pharmax

A pipeline and a **data standard** for studying drug supply and demand in Telegram pharmacy-exchange groups.
Give it Telegram exports; it produces (a) pseudonymised per-channel tables for researchers (restricted) and (b) tables **pooled
across all channels** and threshold-suppressed, which can be published without identifying any single channel.

> **Status: v0.2 (draft, release candidate).** Holds a first pooled dataset from five Persian-language channels (see
> [Current data](#current-data)). The lexicon is unreviewed by a pharmacist, the supply/demand rules were spot-checked on
> only one of the five channels, and no licence has been chosen yet. Read
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

## Current data

The repository currently contains **one pooled public dataset** built from **five Persian-language Telegram groups** in which
pharmacies and individuals offer and request medicines (including scarce and rare drugs). Headline figures at this commit:

| | |
|---|---|
| Period | Oct 2018 - Nov 2026 (98 months with activity) |
| Messages | 1.6 million (1.54 million with text); about 76% supply, 15% demand, 2% job ads |
| Distinct senders | 8,618 named accounts, linked across groups by pseudonym (deleted accounts count as one) |
| Published data | 26,241 month x role x drug-group cells over 150 drug groups; 3,041 sensitive-drug cells suppressed |
| Matching | about half of all extracted item lines match a lexicon drug group |

- **The dataset card, [data/public/README.md](data/public/README.md), is the authoritative description** of the files, thresholds,
  composition and limits. It is generated from the published files every time you run `pool`, so it cannot drift from the data.
- **Not in this repository:** the raw exports, message text, sender identifiers, channel names or codes, and every per-channel
  figure. These stay in the git-ignored restricted tier.
- **Provisional:** only the first channel's supply/demand labels were spot-checked (informally, ~90-95% correct); the QA protocol in
  [docs/ADDING_A_CHANNEL.md](docs/ADDING_A_CHANNEL.md) is still to be completed for the other four, so treat role-level results as
  provisional. Drug groups are the project's own grouping of brand names, not pharmacist-verified.

## Quick start

Requires Python >= 3.9, no third-party packages.

```bash
python -m pharmax init-salt config/.salt                       # once per project; secret, git-ignored
python -m pharmax run --input /path/to/telegram-export \
       --channel-id ch001 --tz +03:30                         # per channel; add --include-text for scrubbed texts (restricted)
python -m pharmax validate data/restricted/ch001              # check against the schema
python -m pharmax pool --k 1 --k-sensitive 5                  # pool ALL channels -> data/public/ (distinct senders across channels)
python -m pharmax validate data/public
python -m pharmax dataset-card                                # regenerate data/public/README.md (pool does this too)
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
data/public/        pooled tables + README.md dataset card, no channel ids (committed)
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

Photo-only posts (3.5% of messages) have no readable text, and captions on photo posts may not list everything shown;
lexicon coverage is partial (about half of extracted items); all deleted accounts share one pseudonym (31% of messages overall; about half
in 2019-2021), so distinct senders are under-counted; role rules are Persian-specific and only spot-checked on one channel; a mention is not a transaction. Details in [docs/METHODOLOGY.md](docs/METHODOLOGY.md).

## Responsible use

The underlying messages come from people who did not consent to research and include sellers of controlled medicines.
Publish pooled aggregates only, keep the higher threshold for sensitive categories, never publish text, per-channel or sender-level data, and get ethics and
legal review. See [docs/PRIVACY_AND_ETHICS.md](docs/PRIVACY_AND_ETHICS.md).

## License and citation

**Not yet chosen.** Until a licence file is added, all rights are reserved. Decide separately on a code licence (e.g. MIT) and
a data licence (e.g. CC BY 4.0) before the first public release.
