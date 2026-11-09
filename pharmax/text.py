"""Language-independent text utilities: scrubbing, hashing, pseudonymisation."""
import hashlib
import hmac
import re

_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")

_URL = re.compile(r"(https?://\S+|www\.\S+|t\.me/\S+|telegram\.me/\S+)", re.I)
_HANDLE = re.compile(r"(?<![\w.])@[A-Za-z0-9_]{3,}")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
# Iranian mobile (09xx xxx xxxx, +98 9xx..., 9xxxxxxxxx) and landlines (0xx xxxxxxxx), tolerant of single separators.
_PHONE = re.compile(
    r"(?<!\d)(?:(?:\+|00)?98[\s-]?|0)?9\d{2}[\s-]?\d{3}[\s-]?\d{4}(?!\d)"
    r"|(?<!\d)0\d{2,3}[\s-]?\d{7,8}(?!\d)"
    r"|(?<!\d)\+?\d{1,3}[\s-]\d{2,4}[\s-]\d{3,4}[\s-]\d{3,4}(?!\d)"
)


def scrub(text):
    """Best-effort removal of contact details. Does NOT remove personal or business names."""
    t = text.translate(_DIGITS)
    t = _EMAIL.sub("<EMAIL>", t)
    t = _URL.sub("<URL>", t)
    t = _HANDLE.sub("<HANDLE>", t)
    t = _PHONE.sub("<PHONE>", t)
    return t


def text_hash(normalised_text):
    return hashlib.sha1(normalised_text.encode("utf-8")).hexdigest()[:12]


def pseudonym(salt, sender_key):
    """Stable pseudonym for a sender. `salt` is a secret (bytes); never publish it."""
    mac = hmac.new(salt, sender_key.encode("utf-8"), hashlib.sha256).hexdigest()
    return "u_" + mac[:12]
