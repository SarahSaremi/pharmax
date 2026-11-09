# Changelog

## 0.2.0 (draft)
- **Breaking (schema 0.2.0):** the public tier is now *pooled across channels* (`pooled_monthly_summary`,
  `pooled_drug_month_counts`, `lexicon`, `pooled_meta.json`); all per-channel tables (including `monthly_summary`,
  `drug_month_counts`, `channel_meta.json`) moved to the restricted tier.
- New `pool` command (replaces `merge`): distinct senders counted across channels; per-flag thresholds
  (`--k` ordinary, `--k-sensitive` for flags C/A/X); refuses mixed lexicon/schema versions.
- `run` no longer takes `--k`; it never writes to the public tier.
- Lexicon lookup indexed by first word (same matches, proven by test; much faster).
- Channels ch002-ch005 added (5 channels, 1.6M messages, pooled; 8,618 distinct named senders after cross-channel linking).

## 0.1.0 (draft)
- Data standard v0.1.0: restricted tables (`messages`, `mentions`, `texts_scrubbed`, `unmatched_items`) and public tables
  (`monthly_summary`, `drug_month_counts`, `lexicon`, `channel_meta.json`).
- Persian language pack `fa-0.1.0`; drug lexicon with 150 drug groups (unreviewed).
- Pipeline CLI: `run`, `validate`, `merge`, `init-salt`, `schema-doc`.
