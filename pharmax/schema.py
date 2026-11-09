"""Data standard: the single source of truth for every table the pipeline writes.

Each table is (tier, [(column, type, description), ...]).
  tier "public"     -> pooled across channels and threshold-suppressed; the only tier that may be published
  tier "restricted" -> per-channel tables (row-level and per-channel aggregates); never commit or publish
Types: str | int | float | date (YYYY-MM-DD) | month (YYYY-MM) | datetime (ISO 8601)
"""

ROLES = ["supply", "demand", "mixed", "other", "jobs"]
FLAGS = {
    "C": "controlled / narcotic / psychotropic / stimulant-type drug",
    "A": "obstetric / abortifacient-related (e.g. misoprostol, mifepristone, oxytocin)",
    "R": "rare-disease / orphan-type drug",
    "V": "COVID-19-era drug",
    "X": "unlicensed sexual-enhancement product",
}
MEDIA_TYPES = ["none", "photo", "video", "file", "audio", "voice", "sticker", "location", "contact", "other"]

TABLES = {
    "messages": ("restricted", [
        ("channel_id", "str", "Project-assigned channel code, e.g. ch001 (never the real channel name)"),
        ("msg_id", "int", "Telegram message id within the channel"),
        ("ts_local", "datetime", "Timestamp as shown in the export (local time of the exporter)"),
        ("ts_utc", "datetime", "Timestamp converted to UTC using the export's offset (or --tz)"),
        ("month", "month", "YYYY-MM of ts_local; the time bucket used by all aggregates"),
        ("sender_pid", "str", "Pseudonymous sender id = HMAC-SHA256(secret salt, sender key)[:12]; 'DELETED' for deleted accounts"),
        ("sender_is_deleted", "int", "1 if the sender is a deleted account (many people share one 'DELETED' pid)"),
        ("is_forwarded", "int", "1 if forwarded from elsewhere"),
        ("reply_to_id", "int", "msg_id this message replies to, empty if none"),
        ("media_type", "str", "one of MEDIA_TYPES; media with text_len < 3 cannot be read by the text pipeline (photo posts with a caption are analysed through the caption)"),
        ("text_len", "int", "Characters of text (0 for media-only)"),
        ("role", "str", "supply | demand | mixed | other | jobs (rule-based, see METHODOLOGY)"),
        ("role_rule", "str", "Name of the rule that assigned the role (for auditing)"),
        ("n_items", "int", "Number of candidate item lines extracted"),
        ("text_hash", "str", "SHA1[:12] of the normalised text; identical ads share a hash"),
        ("is_repeat", "int", "1 if the same sender already posted the same text_hash earlier in the same month"),
    ]),
    "mentions": ("restricted", [
        ("channel_id", "str", ""), ("msg_id", "int", ""), ("month", "month", ""),
        ("sender_pid", "str", ""), ("role", "str", "role of the parent message"),
        ("item_norm", "str", "Normalised item line (1-2 words) extracted from the message"),
        ("drug_id", "str", "Lexicon drug_id, empty if unmatched"),
        ("variant", "str", "Lexicon variant string that matched (brand/spelling level)"),
        ("n_posts", "int", "Rows are de-duplicated per (sender, month, role, item); n_posts = how many messages repeated it. msg_id = first such message"),
    ]),
    "texts_scrubbed": ("restricted", [
        ("channel_id", "str", ""), ("msg_id", "int", ""),
        ("text_scrubbed", "str", "Message text with phone numbers, URLs, @handles, e-mails removed (best effort; names are NOT removed)"),
    ]),
    "unmatched_items": ("restricted", [
        ("channel_id", "str", ""), ("item_norm", "str", "Item lines not in the lexicon (candidates to add)"),
        ("n_senders", "int", "Distinct senders using the item"), ("n_messages", "int", ""),
    ]),
    "monthly_summary": ("restricted", [
        ("channel_id", "str", ""), ("month", "month", ""),
        ("n_messages", "int", "All messages incl. media-only"), ("n_with_text", "int", ""),
        ("n_supply", "int", ""), ("n_demand", "int", ""), ("n_mixed", "int", ""), ("n_other", "int", ""), ("n_jobs", "int", ""),
        ("n_media_only", "int", "Messages with media and no text (invisible to text analysis)"),
        ("n_deleted_msgs", "int", "Messages from deleted accounts"),
        ("n_senders", "int", "Distinct sender_pid (DELETED counts as 1)"),
        ("n_senders_supply", "int", ""), ("n_senders_demand", "int", ""),
        ("n_distinct_texts", "int", "Distinct text_hash among messages with text"),
        ("repeat_share", "float", "Share of text messages flagged is_repeat"),
        ("top5_sender_share_supply", "float", "Share of supply messages posted by the 5 most active supply senders (re-posting concentration)"),
    ]),
    "drug_month_counts": ("restricted", [
        ("channel_id", "str", ""), ("month", "month", ""),
        ("role", "str", "supply | demand | mixed | other"), ("drug_id", "str", "Lexicon drug_id"),
        ("n_senders", "int", "PRIMARY MEASURE: distinct sender_pid mentioning the drug in that month and role"),
        ("n_messages", "int", "Raw messages (inflated by re-posting)"),
        ("n_messages_dedup", "int", "Distinct (sender, text_hash) messages"),
        ("n_replied", "int", "Distinct messages that received >=1 reply in the channel (response proxy; meaningful for demand)"),
    ]),
    "pooled_monthly_summary": ("public", [
        ("month", "month", ""), ("n_channels", "int", "Channels with any message that month"),
        ("n_messages", "int", "Sum over channels (messages are disjoint across channels)"), ("n_with_text", "int", "Sum"),
        ("n_supply", "int", "Sum"), ("n_demand", "int", "Sum"), ("n_mixed", "int", "Sum"), ("n_other", "int", "Sum"), ("n_jobs", "int", "Sum"),
        ("n_media_only", "int", "Sum"), ("n_deleted_msgs", "int", "Sum"),
        ("n_senders", "int", "Distinct sender_pid across ALL channels (needs one shared salt; DELETED counts as 1)"),
        ("n_senders_supply", "int", "Distinct across channels"), ("n_senders_demand", "int", "Distinct across channels"),
    ]),
    "pooled_drug_month_counts": ("public", [
        ("month", "month", ""), ("role", "str", "supply | demand | mixed | other"), ("drug_id", "str", "Lexicon drug_id"),
        ("n_channels", "int", "Channels contributing to the cell"),
        ("n_senders", "int", "PRIMARY MEASURE: distinct sender_pid across all channels. Cells below the threshold are removed (see pooled_meta.json)"),
        ("n_messages", "int", "Sum of raw messages over channels"),
        ("n_messages_dedup", "int", "Sum over channels of distinct (sender, text) messages; an upper bound when a sender posts the same text in two channels"),
        ("n_replied", "int", "Sum over channels of messages that received >=1 reply"),
    ]),
    "lexicon": ("public", [
        ("drug_id", "str", "Stable slug"), ("name", "str", "Canonical drug / drug-group name"),
        ("category", "str", "Therapeutic category"), ("flags", "str", "Concatenated flag letters, see FLAGS"),
        ("variants", "str", "Pipe-separated brand / generic / spelling variants (normalised Persian)"),
        ("review_status", "str", "unreviewed | reviewed (by a pharmacist)"), ("notes", "str", ""),
    ]),
}


def to_markdown():
    """Render the standard as Markdown (docs/DATA_STANDARD.md is generated from this)."""
    from . import SCHEMA_VERSION
    out = [f"# Data standard v{SCHEMA_VERSION}", "",
           "_Generated from `pharmax/schema.py` by `python -m pharmax schema-doc`. Do not edit by hand._", "",
           "All tables are UTF-8 CSV (`.csv` or `.csv.gz`) with a header row, one file per table per channel, "
           "named `<table>.csv[.gz]` inside `data/restricted/<channel_id>/` (per-channel tables) or `data/public/` (pooled tables, no channel id). Empty string = missing. "
           "Types: `str`, `int`, `float`, `month` (YYYY-MM), `datetime` (ISO 8601, no zone suffix).", "",
           "## Vocabularies", "",
           "- **role**: " + ", ".join(f"`{r}`" for r in ROLES),
           "- **media_type**: " + ", ".join(f"`{m}`" for m in MEDIA_TYPES), "",
           "**Lexicon flags** (concatenated letters in `lexicon.flags`):", ""]
    out += [f"- `{k}` - {v}" for k, v in FLAGS.items()]
    for tier_name, title in (("public", "Public tier (pooled across channels, threshold-suppressed; may be published)"),
                             ("restricted", "Restricted tier (per-channel; never commit or publish)")):
        out += ["", f"## {title}", ""]
        for name, (t, cols) in TABLES.items():
            if t != tier_name:
                continue
            out += [f"### `{name}`", "", "| column | type | description |", "|---|---|---|"]
            out += [f"| `{c}` | {ty} | {d} |" for c, ty, d in cols]
            out.append("")
    return "\n".join(out).rstrip() + "\n"


def columns(table):
    return [c[0] for c in TABLES[table][1]]


def tier(table):
    return TABLES[table][0]
