# Privacy and ethics

This is a project working with messages written by real people who did not consent to research: pharmacists, patients
and sellers, some of whom advertise controlled medicines. The design follows one rule: **publish aggregates, keep
anything row-level restricted, never publish text or identities.** This document is guidance, not legal advice; get
institutional ethics review (IRB / ethics committee) and legal advice for your jurisdiction before releasing data.

## Data tiers

| Tier | Contents | Where | May be published? |
|---|---|---|---|
| 0 - raw | Telegram export (names, phones, photos, text) | outside the repo | **Never** |
| 1 - restricted | everything per channel: pseudonymised row-level tables (`messages`, `mentions`, `unmatched_items`, optional `texts_scrubbed`), per-channel aggregates and `channel_meta.json` | `data/restricted/<ch>/` (git-ignored) | No. Share only under a data-use agreement after review |
| 2 - public | tables **pooled across all channels** (`pooled_monthly_summary`, `pooled_drug_month_counts`, `lexicon`, `pooled_meta.json`) | `data/public/` (committed) | Yes, after the checklist below |

## What the pipeline does for you

- **Pseudonymisation.** `sender_pid = HMAC-SHA256(secret salt, sender key)[:12]`. The salt lives in `config/.salt`, is
  git-ignored and must never be published. Use the *same* salt for all channels of a project if you want cross-channel
  sender linkage (JSON exports with user ids only); use different salts to prevent linkage.
- **No names, no contacts in the public tier.** Public tables contain no sender ids at all, only counts.
- **Pooling instead of publishing channels.** The public tier only contains numbers pooled across all channels, with
  distinct senders counted across channels (one shared salt). This removes per-channel figures, dilutes small cells and
  stops readers from attributing anything to a particular group. It does not help while only one channel is loaded;
  `pharmax pool` warns about that.
- **Threshold by sensitivity.** Cells below `--k` distinct pooled senders are dropped for ordinary drugs (default 1 =
  none, because pooled, unnamed counts of ordinary drugs identify nobody). For drugs flagged `C`, `A` or `X`, cells below
  `--k-sensitive` (default 5) are dropped. The complete per-channel counts stay in the restricted tier.
- **Scrubbed text is optional and restricted.** `--include-text` removes phone numbers, URLs, @handles and e-mails
  (best effort). It does **not** remove personal or business names, so scrubbed text must never be treated as anonymous.
- **Channel anonymity.** Restricted outputs use a project code (`ch001`); public outputs contain no channel code at all.
  The real channel name belongs only in `config/channels.private.csv` (git-ignored). Dates and language of the pooled data
  can still hint at which communities were studied; consider that.

## What you must still decide

1. **Review the sensitive-drug threshold.** Drugs flagged `C` (controlled), `A` (obstetric/abortifacient-related) and `X`
   (unlicensed enhancers) mostly come from a handful of sellers, who stay concentrated even after pooling. The default
   is 5 pooled senders per cell; consider aggregating these drugs to year level or to category totals, and check how many
   cells were suppressed in `pooled_meta.json`.
2. **Complementary disclosure.** Suppression of one cell can be undone from totals. Do not publish both `n_senders` by
   drug and a marginal that lets someone subtract back to a suppressed cell.
3. **Do not publish seller-level information.** No "top sellers", no per-sender tables, no lists of who offers narcotics,
   in any tier you share outside the team.
4. **Avoid harm-facilitating framing.** Report what is traded and how it changes, not where or from whom to obtain
   controlled or abortion-related medicines.
5. **Researcher and participant safety.** In some jurisdictions trading or studying these markets carries legal risk for
   the participants and for you. Document your legal basis and storage security.
6. **Terms of service and licensing.** Check Telegram's terms and the group's rules. The public data are CC BY 4.0
   and the code MIT (see README), so reuse cannot be restricted by licence: the safeguards must be in the data itself.

## Release checklist (public tier)

- [ ] `python -m pharmax validate data/public` passes and `pooled_meta.json` shows `n_channels` >= 2
- [ ] no `data/restricted/` or `config/.salt` in `git status`, and none in git history (`git log --all -- config/.salt`)
- [ ] sensitive threshold reviewed (see 1) and checked for complementary disclosure
- [ ] QA report for the channel exists in `docs/qa/` and role precision is stated in the release notes
- [ ] no channel codes or titles anywhere under `data/public/`; code mapping is only in the private file
- [ ] ethics approval / legal review recorded
- [ ] lexicon `review_status` honestly stated (unreviewed vs pharmacist-reviewed)
