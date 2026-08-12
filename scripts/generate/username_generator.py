import argparse
import os
import random
import re

DEFAULT_USERNAME_STYLE = (os.getenv("USERNAME_STYLE", "varied") or "varied").strip().lower()
DEFAULT_USERNAME_LENGTH = (os.getenv("USERNAME_LENGTH", "varied") or "varied").strip().lower()
DEFAULT_USERNAME_KEYWORD = re.sub(r"[^A-Za-z0-9_]", "", (os.getenv("USERNAME_KEYWORD", "") or "")).strip("_")

STYLE_BANK = {
    "cool": [
        "aero", "arc", "brisk", "cipher", "dash", "drift", "ember", "flare", "flux", "glide",
        "halo", "lumen", "matrix", "nimbus", "nova", "orbit", "prism", "pulse", "quartz",
        "ripple", "signal", "sonic", "spark", "swift", "vector", "vertex", "volt", "wave",
        "zenith",
    ],
    "funny": [
        "banter", "bean", "bingo", "boop", "bounce", "bubble", "button", "cheddar", "chuckle",
        "doodle", "fizz", "jelly", "jolly", "mango", "mirth", "muffin", "noodle", "pogo",
        "popcorn", "sketch", "sprout", "toast", "waffle", "wiggle", "zippy",
    ],
    "tryhard": [
        "ace", "aim", "burst", "carry", "clutch", "combo", "dash", "duel", "elite", "focus",
        "grind", "impact", "macro", "marker", "mvp", "peak", "rank", "rapid", "recoil",
        "rush", "score", "sharp", "shift", "skill", "sprint", "streak", "tempo", "track",
    ],
    "aesthetic": [
        "amber", "aurora", "bloom", "blush", "breeze", "celeste", "clover", "dawn", "dream",
        "echo", "flora", "glimmer", "glow", "haven", "honey", "iris", "ivory", "lotus",
        "luna", "meadow", "mist", "opal", "pearl", "petal", "silk", "sora", "velvet",
        "willow",
    ],
    "edgy": [
        "ashen", "cipher", "eclipse", "ember", "hex", "midnight", "nexus", "night",
        "nocturne", "obsidian", "onyx", "phantom", "rift", "sable", "shade", "shiver",
        "smoke", "static", "thorn", "umbra", "vanta", "void",
    ],
    "og": [
        "ace", "atlas", "blade", "blaze", "chief", "classic", "crest", "hero", "iron",
        "king", "legacy", "lord", "major", "pilot", "prime", "rider", "rook", "solid",
        "stone", "storm", "titan", "valor", "zero",
    ],
    "anime": [
        "aiko", "akira", "aoi", "haru", "hikari", "kaori", "kaze", "kira", "kuro", "mika",
        "nami", "ren", "riku", "rin", "ryu", "sora", "yami", "yuki", "yuna", "zen",
    ],
    "gaming": [
        "arcade", "arena", "boost", "boss", "checkpoint", "combo", "core", "drop", "duel",
        "game", "guild", "level", "lobby", "loot", "match", "pixel", "quest", "raid",
        "respawn", "score", "spawn", "sprint", "stage", "token", "xp",
    ],
}

STYLE_DECORATORS = {
    "cool": ["x", "v2", "lab", "sync", "zone"],
    "funny": ["lol", "haha", "bits", "club", "plus"],
    "tryhard": ["pro", "rank", "fps", "aim", "win"],
    "aesthetic": ["xo", "ia", "ly", "aura", "halo"],
    "edgy": ["x", "rx", "vx", "noir", "shade"],
    "og": ["ii", "iv", "x", "one", "prime"],
    "anime": ["kai", "ko", "mi", "rin", "zen"],
    "gaming": ["gg", "hq", "pro", "xp", "tv"],
}

STYLE_PREFIXES = {
    "cool": ["neo", "ultra", "astro", "aero", "hyper", "luxe"],
    "funny": ["big", "tiny", "mister", "sir", "silly", "lucky"],
    "tryhard": ["ace", "max", "pro", "rapid", "prime", "elite"],
    "aesthetic": ["soft", "moon", "rose", "star", "dear", "glow"],
    "edgy": ["dark", "night", "void", "noir", "hex", "shade"],
    "og": ["the", "old", "true", "prime", "classic", "solid"],
    "anime": ["aka", "kuro", "shiro", "neo", "hikari", "yume"],
    "gaming": ["play", "game", "zone", "pixel", "level", "quest"],
}

STYLE_SUFFIXES = {
    "cool": ["x", "sync", "wave", "zone", "lab", "io"],
    "funny": ["lol", "time", "bits", "mode", "club"],
    "tryhard": ["pro", "rank", "fps", "aim", "win"],
    "aesthetic": ["ia", "ly", "dream", "aura", "glow", "xo"],
    "edgy": ["x", "rx", "vx", "shade", "noir"],
    "og": ["x", "ii", "prime", "one", "classic"],
    "anime": ["kai", "ko", "rin", "zen", "yume"],
    "gaming": ["gg", "hub", "pro", "xp", "tv"],
}

GLOBAL_TOKENS = [
    "alpha", "apex", "binary", "byte", "delta", "echo", "ember", "gamma", "hyper", "lumen",
    "matrix", "nexus", "omega", "pixel", "prime", "signal", "spark", "swift", "vector",
    "vertex", "zenith",
]

NUMERIC_SUFFIXES = [
    "7", "8", "9", "11", "12", "14", "16", "18", "21", "24", "27", "32", "42", "64",
    "77", "88", "99", "101", "202", "303", "404", "808", "909",
]

GENERATED_SYLLABLES = [
    "a", "ae", "ari", "ba", "be", "bo", "ca", "chi", "da", "de", "fi", "ha", "io",
    "ja", "ka", "ki", "la", "li", "lo", "lu", "ma", "mi", "mo", "na", "ni", "no",
    "ora", "ra", "re", "ri", "ro", "sa", "shi", "ta", "ti", "va", "ve", "vi", "ya",
    "za", "zo",
]

PROFILE_NAMES = [
    "abby", "aiko", "alleah", "ariel", "ashley", "austin", "belle", "chan", "cole",
    "draco", "emm", "finn", "forrest", "gabriela", "izzy", "jai", "jill", "jocelyn",
    "keen", "kenny", "kimmy", "lena", "lexi", "lucja", "maddie", "madz", "mayo",
    "meel", "mery", "mika", "molly", "nako", "niki", "rell", "rosie", "sofi",
    "sophia", "stella", "taya", "viel", "yuna",
]

PROFILE_WORDS = [
    "agent", "angel", "badd", "bloom", "bun", "choco", "crystal", "fairy", "grass",
    "hunter", "jelly", "mayo", "mochi", "nooby", "petals", "pixel", "pixlr", "queen",
    "roach", "rock", "rocks", "rose", "salmon", "slay", "spade", "star", "swan",
    "toast", "venus", "vibe",
]

PROFILE_PREFIXES = ["x", "i", "ii", "its", "not", "luv", "stxrry", "t0kyo"]
PROFILE_SUFFIXES = ["xo", "x", "z", "yy", "luv", "qt", "hearts", "fromvenus"]
PROFILE_ENDINGS = ["y", "yy", "o", "ie", "bun", "ger", "crunch", "for4u", "plays"]
PROFILE_NUMBERS = [
    "0", "00", "1", "2", "3", "7", "8", "12", "14", "38", "45", "56", "68", "88",
    "333", "600", "716", "720",
]

STYLE_ALIASES = {
    "varied": "profile",
    "og/classic": "og",
    "classic": "og",
    "inspo": "profile",
    "realistic": "profile",
    "social": "profile",
}

THEMED_STYLES = tuple(STYLE_BANK.keys())
VALID_STYLES = ("profile", *THEMED_STYLES)
STYLE_CHOICES = tuple(dict.fromkeys(("varied", *VALID_STYLES, *STYLE_ALIASES.keys())))
RECENT_USERNAMES = []
RECENT_USERNAME_LIMIT = 3000


def _normalize_style(style):
    style = (style or "varied").strip().lower()
    style = STYLE_ALIASES.get(style, style)
    if style in VALID_STYLES:
        return style
    raise ValueError(f"Unsupported username style: {style}")


def _target_length_profile(length, rng):
    length = (length or "varied").strip().lower()
    if length == "short":
        return 3, 8, rng.randint(6, 8)
    if length == "medium":
        return 9, 14, rng.randint(11, 14)
    if length == "long":
        return 15, 20, rng.randint(16, 20)
    if length == "varied":
        bucket = rng.choices(["short", "medium"], weights=[20, 80], k=1)[0]
        ranges = {
            "short": (3, 8, rng.randint(6, 8)),
            "medium": (9, 14, rng.randint(9, 13)),
        }
        return ranges[bucket]
    raise ValueError(f"Unsupported username length: {length}")


def sanitize_username(candidate):
    sanitized = re.sub(r"[^A-Za-z0-9_]", "", str(candidate))
    sanitized = re.sub(r"_+", "_", sanitized)
    sanitized = sanitized.strip("_")
    if sanitized.count("_") > 1:
        first, *rest = sanitized.split("_")
        sanitized = first + "_" + "".join(rest)
    return sanitized[:20].strip("_")


def is_valid_username(candidate):
    if len(candidate) < 3 or len(candidate) > 20:
        return False
    if not re.match(r"^[A-Za-z0-9_]+$", candidate):
        return False
    if candidate.startswith("_") or candidate.endswith("_"):
        return False
    if "__" in candidate:
        return False
    if candidate.count("_") > 1:
        return False
    return not re.search(r"(.)\1\1\1", candidate.lower())


def _syllable_word(rng, syllables=None):
    count = syllables if syllables is not None else rng.choice([2, 2, 3])
    chunks = []
    previous = ""
    for _ in range(count):
        syllable = rng.choice(GENERATED_SYLLABLES)
        while syllable == previous:
            syllable = rng.choice(GENERATED_SYLLABLES)
        chunks.append(syllable)
        previous = syllable
    return "".join(chunks)


def _stylize_case(value, style, rng):
    if not value:
        return value
    mode = rng.choices(["lower", "pascal", "camel", "mixed"], weights=[62, 25, 12, 1], k=1)[0]
    if style in ("og", "aesthetic", "anime") and rng.randint(1, 100) <= 55:
        mode = rng.choices(["pascal", "camel", "lower"], weights=[42, 35, 23], k=1)[0]
    if mode == "lower":
        return value.lower()
    if mode == "pascal":
        return value[:1].upper() + value[1:].lower()
    if mode == "camel":
        return value[:1].lower() + value[1:].lower()

    chars = []
    for ch in value:
        if ch.isalpha() and rng.randint(1, 100) <= 28:
            chars.append(ch.upper())
        else:
            chars.append(ch.lower())
    return "".join(chars)


def _apply_leet(value, style, rng):
    if style not in ("edgy", "tryhard", "gaming"):
        return value
    if rng.randint(1, 100) > 10:
        return value
    swaps = {"a": "4", "e": "3", "i": "1", "o": "0", "s": "5", "t": "7"}
    chars = []
    for ch in value:
        lower = ch.lower()
        if lower in swaps and rng.randint(1, 100) <= 18:
            chars.append(swaps[lower])
        else:
            chars.append(ch)
    return "".join(chars)


def _pick_keyword(keyword):
    keyword = DEFAULT_USERNAME_KEYWORD if keyword is None else keyword
    if keyword:
        return sanitize_username(keyword.lower())[:10]
    return ""


def _random_pair(values, rng):
    first = rng.choice(values)
    remaining = [value for value in values if value != first]
    second = rng.choice(remaining or values)
    return first, second


def _join_username_parts(parts, rng):
    clean_parts = [sanitize_username(part) for part in parts if part]
    clean_parts = [part for part in clean_parts if part]
    if not clean_parts:
        return ""
    sep = rng.choices(["", "_"], weights=[86, 14], k=1)[0]
    return sanitize_username(sep.join(clean_parts))


def _append_username_part(candidate, extra, prefer_separator=False, max_len=None):
    extra = sanitize_username(extra)
    if not extra:
        return candidate
    use_separator = prefer_separator and "_" not in candidate
    separator = "_" if use_separator else ""
    if max_len is not None:
        room = max_len - len(candidate) - len(separator)
        if room < 3:
            return candidate
        extra = extra[:room]
    use_separator = bool(separator) and len(candidate) + len(extra) + 1 <= 20
    joined = f"{candidate}_{extra}" if use_separator else f"{candidate}{extra}"
    return sanitize_username(joined)


def _token_fragment(token, rng):
    token = sanitize_username(token).lower()
    if len(token) <= 4:
        return token
    if rng.randint(1, 100) <= 70:
        return token[: rng.randint(3, min(5, len(token)))]
    return token


def _profile_length_bounds(length):
    length = (length or "varied").strip().lower()
    if length == "short":
        return 4, 8
    if length == "medium":
        return 5, 12
    if length == "long":
        return 9, 20
    if length == "varied":
        return 5, 14
    raise ValueError(f"Unsupported username length: {length}")


def _profile_case(candidate, rng):
    if "_" in candidate:
        return candidate.lower()
    mode = rng.choices(["lower", "title"], weights=[68, 32], k=1)[0]
    if mode == "title":
        return candidate[:1].upper() + candidate[1:].lower()
    return candidate.lower()


def _profile_stylized_base(base, rng):
    base = sanitize_username(base).lower()
    mode = rng.choices(["ending", "repeat", "soft_number", "prefix"], weights=[38, 20, 32, 10], k=1)[0]
    if mode == "repeat":
        return f"{base}{base[-1] * rng.randint(1, 3)}"
    if mode == "soft_number":
        return f"{base}{rng.choice(PROFILE_NUMBERS)}"
    if mode == "prefix":
        return f"{rng.choice(PROFILE_PREFIXES)}{base}"
    return f"{base}{rng.choice(PROFILE_ENDINGS)}"


def _too_simple_profile_username(candidate):
    lower = candidate.lower()
    simple_tokens = set(PROFILE_NAMES) | set(PROFILE_WORDS)
    return lower in simple_tokens


def _build_profile_username(keyword, length, rng):
    min_len, max_len = _profile_length_bounds(length)
    keyword = sanitize_username(keyword.lower()) if keyword else ""

    for _ in range(80):
        name = keyword or rng.choice(PROFILE_NAMES)
        other_name = rng.choice([value for value in PROFILE_NAMES if value != name] or PROFILE_NAMES)
        word = rng.choice(PROFILE_WORDS)
        other_word = rng.choice([value for value in PROFILE_WORDS if value != word] or PROFILE_WORDS)
        number = rng.choice(PROFILE_NUMBERS)

        templates = [
            ("name_number", 24),
            ("name_suffix", 18),
            ("name_bumped", 16),
            ("word_number", 14),
            ("word_bumped", 12),
            ("underscore", 12),
            ("name_word", 7),
            ("word_word", 6),
            ("word_name", 4),
            ("prefix_name", 4),
            ("phrase", 3),
        ]

        template = rng.choices([tpl[0] for tpl in templates], weights=[tpl[1] for tpl in templates], k=1)[0]
        if template == "name_number":
            candidate = f"{name}{number}"
        elif template == "name_suffix":
            candidate = f"{name}{rng.choice(PROFILE_SUFFIXES)}"
        elif template == "name_bumped":
            candidate = _profile_stylized_base(name, rng)
        elif template == "word_number":
            candidate = f"{word}{number}"
        elif template == "word_bumped":
            candidate = _profile_stylized_base(word, rng)
        elif template == "word_name":
            connector = "n" if word == "rock" else ""
            candidate = f"{word}{connector}{other_name}"
        elif template == "name_word":
            connector = rng.choices(["", "hearts"], weights=[75, 25], k=1)[0]
            candidate = f"{name}{connector}{word}"
        elif template == "word_word":
            candidate = f"{word}{other_word}"
        elif template == "underscore":
            left = rng.choice([name, word])
            right = rng.choice([other_name, other_word, rng.choice(PROFILE_SUFFIXES), number])
            candidate = f"{left}_{right}"
        elif template == "prefix_name":
            candidate = f"{rng.choice(PROFILE_PREFIXES)}{name}"
        elif template == "phrase":
            phrase = rng.choice(["ilove", "luvfor", "petalsin", "kickstart", "mon", "lol"])
            tail = rng.choice([word, other_word, name, other_name, "4u"])
            candidate = f"{phrase}{tail}"
        else:
            raise AssertionError(f"Unhandled profile template: {template}")

        candidate = _profile_case(sanitize_username(candidate), rng)
        if min_len <= len(candidate) <= max_len and not _too_simple_profile_username(candidate):
            return candidate

    raise RuntimeError("Failed to build a profile username")


def _build_core(style, keyword, rng):
    bank = STYLE_BANK[style]
    other_style = rng.choice([value for value in THEMED_STYLES if value != style] or THEMED_STYLES)
    generated = _syllable_word(rng, rng.choice([2, 2, 3]))
    raw_a, raw_b = _random_pair(bank, rng)
    word_a = raw_a
    word_b = raw_b
    word_c = rng.choice(STYLE_BANK[other_style])
    global_word = rng.choice(GLOBAL_TOKENS)
    prefix = rng.choice(STYLE_PREFIXES[style])
    suffix = rng.choice(STYLE_SUFFIXES[style])
    number = rng.choice(NUMERIC_SUFFIXES)

    templates = [
        ("bank_bank", 28),
        ("bank_bank_bank", 6),
        ("bank_generated", 1),
        ("generated_bank", 1),
        ("prefix_bank", 10),
        ("bank_suffix", 10),
        ("prefix_bank_suffix", 6),
        ("global_bank", 10),
        ("bank_global", 10),
        ("bank_number", 7),
        ("bank_crossstyle", 6),
        ("keyword_bank", 5),
        ("bank_keyword", 5),
        ("keyword_generated", 6),
        ("generated_keyword", 6),
    ]
    if not keyword:
        templates = [tpl for tpl in templates if not tpl[0].startswith("keyword")]
        templates = [tpl for tpl in templates if not tpl[0].endswith("keyword")]

    template = rng.choices([tpl[0] for tpl in templates], weights=[tpl[1] for tpl in templates], k=1)[0]

    if template == "bank_bank":
        parts = [word_a, word_b]
    elif template == "bank_bank_bank":
        parts = [word_a, word_b, word_c]
    elif template == "bank_generated":
        parts = [word_a, generated]
    elif template == "generated_bank":
        parts = [generated, word_a]
    elif template == "prefix_bank":
        parts = [prefix, word_a]
    elif template == "bank_suffix":
        parts = [word_a, suffix]
    elif template == "prefix_bank_suffix":
        parts = [prefix, word_a, suffix]
    elif template == "global_bank":
        parts = [global_word, word_a]
    elif template == "bank_global":
        parts = [word_a, global_word]
    elif template == "bank_number":
        parts = [word_a, number]
    elif template == "bank_crossstyle":
        parts = [word_a, word_c]
    elif template == "keyword_bank":
        parts = [keyword, word_a]
    elif template == "bank_keyword":
        parts = [word_a, keyword]
    elif template == "keyword_generated":
        parts = [keyword, generated]
    elif template == "generated_keyword":
        parts = [generated, keyword]
    else:
        raise AssertionError(f"Unhandled themed template: {template}")

    return _join_username_parts(parts, rng)


def _length_fit(candidate, min_len, max_len, target_len, style, rng):
    candidate = sanitize_username(candidate)
    if len(candidate) > max_len:
        return ""
    decorators = STYLE_DECORATORS[style]
    suffixes = STYLE_SUFFIXES[style]
    prefixes = STYLE_PREFIXES[style]

    attempts = 0
    while len(candidate) < target_len and attempts < 8:
        attempts += 1
        mode = rng.choices(
            ["digits", "decorator", "word", "global", "affix"],
            weights=[22, 20, 28, 18, 12],
            k=1,
        )[0]
        if mode == "digits":
            candidate = _append_username_part(candidate, rng.choice(NUMERIC_SUFFIXES), max_len=max_len)
        elif mode == "decorator":
            extra = rng.choice(decorators)
            candidate = _append_username_part(
                candidate,
                extra,
                prefer_separator=rng.randint(1, 100) <= 25,
                max_len=max_len,
            )
        elif mode == "global":
            candidate = _append_username_part(candidate, _token_fragment(rng.choice(GLOBAL_TOKENS), rng), max_len=max_len)
        elif mode == "affix":
            prefix = rng.choice(prefixes)
            if rng.randint(1, 100) <= 50 and len(candidate) + len(prefix) <= max_len:
                candidate = sanitize_username(f"{prefix}{candidate}")
            else:
                candidate = _append_username_part(candidate, rng.choice(suffixes), max_len=max_len)
        else:
            candidate = _append_username_part(candidate, _token_fragment(rng.choice(STYLE_BANK[style]), rng), max_len=max_len)
        candidate = sanitize_username(candidate)

        if len(candidate) >= target_len and len(candidate) >= min_len:
            break

    return candidate


def generate_username(style=None, length=None, keyword=None, rng=None, recent_usernames=None):
    rng = rng or random
    resolved_style = _normalize_style(DEFAULT_USERNAME_STYLE if style is None else style)
    length = DEFAULT_USERNAME_LENGTH if length is None else length
    using_default_recent = recent_usernames is None
    recent_usernames = RECENT_USERNAMES if recent_usernames is None else recent_usernames
    recent_lookup = {name.lower() for name in recent_usernames}
    keyword = _pick_keyword(keyword)
    themed_length_profile = None
    if resolved_style != "profile":
        themed_length_profile = _target_length_profile(length, rng)

    for _ in range(400):
        if resolved_style == "profile":
            candidate = _build_profile_username(keyword, length, rng)
        else:
            min_len, max_len, target_len = themed_length_profile
            base = _build_core(resolved_style, keyword, rng)

            if rng.randint(1, 100) <= 30:
                base = _append_username_part(
                    base,
                    rng.choice(STYLE_DECORATORS[resolved_style]),
                    prefer_separator=True,
                    max_len=max_len,
                )

            if rng.randint(1, 100) <= 25:
                base = _append_username_part(base, rng.choice(NUMERIC_SUFFIXES), max_len=max_len)

            base = _apply_leet(base, resolved_style, rng)
            base = _stylize_case(base, resolved_style, rng)
            candidate = _length_fit(base, min_len, max_len, target_len, resolved_style, rng)
        candidate = sanitize_username(candidate)

        if not is_valid_username(candidate):
            continue
        if candidate.lower() in recent_lookup:
            continue

        recent_usernames.append(candidate)
        recent_lookup.add(candidate.lower())
        if using_default_recent and len(recent_usernames) > RECENT_USERNAME_LIMIT:
            recent_usernames.pop(0)
        return candidate

    raise RuntimeError("Failed to generate a unique valid username")


def generate_usernames(count, style=None, length=None, keyword=None, seed=None):
    rng = random.Random(seed) if seed is not None else random
    recent_usernames = []
    return [
        generate_username(
            style=style,
            length=length,
            keyword=keyword,
            rng=rng,
            recent_usernames=recent_usernames,
        )
        for _ in range(count)
    ]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-n", "--count", type=int, default=20)
    parser.add_argument("--style", default=DEFAULT_USERNAME_STYLE, choices=STYLE_CHOICES)
    parser.add_argument("--length", default=DEFAULT_USERNAME_LENGTH, choices=("varied", "short", "medium", "long"))
    parser.add_argument("--keyword", default=DEFAULT_USERNAME_KEYWORD)
    parser.add_argument("--seed", type=int)
    args = parser.parse_args()

    for username in generate_usernames(args.count, style=args.style, length=args.length, keyword=args.keyword, seed=args.seed):
        print(username)


if __name__ == "__main__":
    main()
