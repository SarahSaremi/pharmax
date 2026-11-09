# Methodology

How raw Telegram exports become the tables described in [DATA_STANDARD.md](DATA_STANDARD.md). Everything here is
implemented in `pharmax/` and versioned: `rules_version` and `lexicon_sha1` are written into every
`channel_meta.json`, so any published number can be traced to the exact rules that produced it.

## Pipeline

```
export (HTML / JSON) --parse--> messages --normalise--> role + items --lexicon--> drug mentions --aggregate--> public tables
                                   |                                        \--> restricted row-level tables
                                   \-- sender -> HMAC pseudonym (secret salt)
```

1. **Parse** (`parse.py`). Telegram Desktop HTML (`messages*.html`) or JSON (`result.json`). Extracted: id, local
   timestamp and UTC offset, sender, forwarded flag, reply-to id, media type, text. HTML "joined" messages (same sender as
   the previous one) have no name in the export; they inherit the previous message's sender after sorting by id.
   Service messages (joins, pins) are dropped.
2. **Normalise** (language pack, e.g. `rules_fa.py`). Unify Arabic/Persian letter variants (ك/ک, ي/ی), digits, zero-width
   characters, diacritics; lower-case Latin text.
3. **Role** (rule-based, auditable). Each text message gets one of `supply`, `demand`, `mixed`, `other`, `jobs` plus the name
   of the rule that fired (`role_rule`). Order of precedence:
   1. `jobs` - hiring / job-seeking / pharmacy-sale ads (they reuse "needed" wording and would pollute demand).
   2. boilerplate such as "if you need it, PM me" is neutralised (it contains a demand word but is a supply phrase).
   3. `offer_phrase` ("if anyone wants…") -> supply; `ask_phrase` ("does anyone have…?", "I wanted…") -> demand.
   4. Cue words: demand cues (needed, buyer, "do you have?"), supply cues (available, for sale, price, PM).
      Only demand -> demand, only supply -> supply. Both -> demand if an explicit need word is present in a short
      message or it is a short question, otherwise `mixed`.
   5. No cue: a short question -> demand; a list of >=4 item lines without a question -> supply (`item_list`); else `other`.
   Messages with fewer than 3 characters of text are `other` / `no_text` (many are image-only ads, see Limitations).
4. **Items** (`clean_items`). Text is split into lines and emoji/punctuation-separated chunks; stop words, dosage forms
   (syrup, tablet, vial…), packaging words and numbers are removed; chunks of 1-2 words are kept as candidate item names.
5. **Lexicon** (`lexicon/drug_lexicon.csv`). Whole-word match of lexicon variants (brands, generics, spelling variants)
   inside each item; longest variant wins. Output `drug_id` is a drug or drug *group* (e.g. "SSRIs/antidepressants"),
   `variant` keeps the brand-level string so brand-level analysis is possible.
6. **Aggregate** per channel (`aggregate.py`, restricted), then **pool** across channels (`pipeline.pool`, public). See below.

## The counting unit: sender-months

Telegram exchange groups are dominated by re-posting. In the first channel only 151k of 469k text messages are distinct
and the five most active accounts wrote 47% of supply messages. Message counts therefore mostly measure how often a few
bots re-post a catalogue. The primary measure in `drug_month_counts` is **`n_senders`: the number of distinct pseudonymous
senders mentioning a drug in a month in a role.** `n_messages` (raw) and `n_messages_dedup` (distinct sender+text) are
also provided so users can see the difference. Always compare *shares* across periods, not raw counts: activity can
change by an order of magnitude between years.

`n_replied` counts distinct messages that received at least one reply in the channel. For demand messages it is a crude
fulfilment proxy (a reply is not proof of a sale).

**Pooling.** `pharmax pool` counts distinct senders across all channels (union of pseudonyms per month, role and drug) and
sums the message-level counts (messages are disjoint across channels). Sender linkage across channels needs one shared salt
and the same sender key type; with HTML exports the key is a display name, so two different people with the same name merge
and one person with two names splits (JSON exports use stable user ids and are preferred). `n_messages_dedup` is a sum of
per-channel de-duplicated counts, so it is an upper bound if a sender posts the same text in two channels.

**Suppression lowers totals for rare and sensitive drugs.** Pooled cells below `--k` (ordinary drugs, default 1 = none) or
`--k-sensitive` (drugs flagged C/A/X, default 5) are removed, so summing public `n_senders` over months *understates* the
sensitive drugs. For example, in the first channel alone misoprostol requests total 153 sender-months in the full
restricted table; with a threshold of 3 only 101 survive. `pooled_meta.json` reports how many cells were suppressed. Use
the per-channel restricted tables for internal analysis and state the thresholds in any publication.

**Deleted accounts.** All deleted accounts share the pseudonym `DELETED` and count as one sender per month. In the first
channel's early months about half of all messages came from deleted accounts (357 of 681 messages in 2018-10), so early
`n_senders` are strongly undercounted. `monthly_summary.n_deleted_msgs` lets you see this.

## Repeat flag

`is_repeat = 1` when the same sender already posted the same normalised text earlier in the same calendar month.

## Validation status

- Informal spot check on the first channel: ~28/30 random supply and ~29/30 random demand messages labelled correctly
  by the rules (n=30 per class, one reviewer). **This is not a formal accuracy estimate.**
- Each new channel must go through the QA protocol in [ADDING_A_CHANNEL.md](ADDING_A_CHANNEL.md) before its tables are published, and
  the measured precision per role recorded in `docs/qa/`.
- The lexicon is `unreviewed`: brand-to-drug mapping and flags were made by the project author, not a pharmacist.

## Limitations (read before publishing results)

- **Image-only ads are invisible.** In the first channel ~108k messages are photos; many are supply ads whose content is only in
  the picture. `monthly_summary.n_media_only` quantifies the blind spot. Supply may be under-counted in image-heavy periods.
- **Lexicon coverage ~45%** of extracted items in the first channel; long-tail drugs, devices and consumables are unmatched.
  `restricted/unmatched_items.csv` lists the most common unmatched items for lexicon growth.
- **Sender identity.** HTML exports carry only display names, which can change or collide. JSON exports carry user ids
  (recommended). All deleted accounts collapse into one pseudonym `DELETED`, which undercounts distinct senders.
- **Role rules are language-specific** and tuned on Persian pharmacy slang. A new language needs its own pack and QA.
- **Brand ambiguity.** Some brands are ambiguous with common words (e.g. a heart drug whose Persian brand equals the word for
  the university entrance exam). Whole-word matching reduces but does not remove this; ambiguity notes are in the lexicon.
- **Representativeness.** A Telegram group is not the market. It reflects what a self-selected community chooses to post,
  and demand posted there is often for hard-to-find drugs.
- **A mention is not an event.** A supply post is not a sale; a demand post is not a patient. Flags such as `A` (obstetric
  / abortifacient-related) mark drugs with sensitive potential uses, not intent.
