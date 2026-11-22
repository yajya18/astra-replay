"""Small, dependency-free text normalisation: verb base forms, stemming, tokens."""

from __future__ import annotations

import re

_WORD = re.compile(r"[a-z0-9]+")

# Irregular or awkward forms -> base form.
_IRREGULAR: dict[str, str] = {
    "putting": "put",
    "puts": "put",
    "cutting": "cut",
    "cuts": "cut",
    "set": "set",
    "setting": "set",
    "sets": "set",
    "got": "get",
    "getting": "get",
    "gets": "get",
    "taking": "take",
    "took": "take",
    "takes": "take",
    "taken": "take",
    "making": "make",
    "made": "make",
    "makes": "make",
    "holding": "hold",
    "held": "hold",
    "spreading": "spread",
    "spreads": "spread",
    "beating": "beat",
    "beaten": "beat",
    "stirring": "stir",
    "stirred": "stir",
    "stirs": "stir",
    "chopping": "chop",
    "chopped": "chop",
    "chops": "chop",
    "dicing": "dice",
    "diced": "dice",
    "dices": "dice",
    "slicing": "slice",
    "sliced": "slice",
    "slices": "slice",
    "grating": "grate",
    "grated": "grate",
    "placing": "place",
    "placed": "place",
    "places": "place",
    "pouring": "pour",
    "poured": "pour",
    "pours": "pour",
    "wiping": "wipe",
    "wiped": "wipe",
    "screwing": "screw",
    "screwed": "screw",
    "unscrewing": "unscrew",
    "unscrewed": "unscrew",
    "whisking": "whisk",
    "whisked": "whisk",
    "whisks": "whisk",
    "adding": "add",
    "added": "add",
    "adds": "add",
    "flipping": "flip",
    "flipped": "flip",
    "plating": "plate",
    "plated": "plate",
    "serving": "serve",
    "served": "serve",
    "frying": "fry",
    "fried": "fry",
    "fries": "fry",
    "mixing": "mix",
    "mixed": "mix",
    "mixes": "mix",
    "washing": "wash",
    "washed": "wash",
    "washes": "wash",
    "peeling": "peel",
    "peeled": "peel",
    "cracking": "crack",
    "cracked": "crack",
    "toasting": "toast",
    "toasted": "toast",
    "heating": "heat",
    "heated": "heat",
    "preheating": "preheat",
    "preheated": "preheat",
    "seasoning": "season",
    "seasoned": "season",
    "folding": "fold",
    "folded": "fold",
    "tightening": "tighten",
    "tightened": "tighten",
    "attaching": "attach",
    "attached": "attach",
    "inserting": "insert",
    "inserted": "insert",
    "removing": "remove",
    "removed": "remove",
    "opening": "open",
    "opened": "open",
    "closing": "close",
    "closed": "close",
    "measuring": "measure",
    "measured": "measure",
    "pressing": "press",
    "pressed": "press",
    "rinsing": "rinse",
    "rinsed": "rinse",
    "drying": "dry",
    "dried": "dry",
    "assembling": "assemble",
    "assembled": "assemble",
    "aligning": "align",
    "aligned": "align",
    "spraying": "spray",
    "sprayed": "spray",
    "lifting": "lift",
    "lifted": "lift",
    "moving": "move",
    "moved": "move",
    "using": "use",
    "used": "use",
    "picking": "pick",
    "picked": "pick",
    "dropping": "drop",
    "dropped": "drop",
    "shaking": "shake",
    "shook": "shake",
    "sprinkling": "sprinkle",
    "sprinkled": "sprinkle",
    "turning": "turn",
    "turned": "turn",
    "transferring": "transfer",
    "transferred": "transfer",
    "scooping": "scoop",
    "scooped": "scoop",
    "kneading": "knead",
    "kneaded": "knead",
    "rolling": "roll",
    "rolled": "roll",
    "melting": "melt",
    "melted": "melt",
    "boiling": "boil",
    "boiled": "boil",
    "draining": "drain",
    "drained": "drain",
    "trimming": "trim",
    "trimmed": "trim",
    "sanding": "sand",
    "sanded": "sand",
    "drilling": "drill",
    "drilled": "drill",
    "gluing": "glue",
    "glued": "glue",
    "hammering": "hammer",
    "hammered": "hammer",
    "connecting": "connect",
    "connected": "connect",
    "plugging": "plug",
    "plugged": "plug",
    "unplugging": "unplug",
    "checking": "check",
    "checked": "check",
    "labeling": "label",
    "labelling": "label",
    "labeled": "label",
    "pipetting": "pipette",
    "pipetted": "pipette",
    "filling": "fill",
    "filled": "fill",
    "emptying": "empty",
    "emptied": "empty",
    "cleaning": "clean",
    "cleaned": "clean",
    "arranging": "arrange",
    "arranged": "arrange",
    "squeezing": "squeeze",
    "squeezed": "squeeze",
    "layering": "layer",
    "layered": "layer",
    "covering": "cover",
    "covered": "cover",
    "waiting": "wait",
    "waited": "wait",
    "reaching": "reach",
    "reached": "reach",
    "grabbing": "grab",
    "grabbed": "grab",
    "tearing": "tear",
    "tore": "tear",
}

# Merges between near-identical verbs. Distinct actions (slice / cut / dice) stay distinct.
SYNONYMS: dict[str, str] = {
    "beat": "whisk",
    "blend": "mix",
    "combine": "mix",
    "put": "place",
    "lay": "place",
    "position": "place",
    "grab": "pick",
    "fetch": "pick",
    "saute": "fry",
    "sauté": "fry",
    "rinse": "wash",
    "sprinkle": "season",
    "salt": "season",
    "smear": "spread",
    "decant": "pour",
}

_STOPWORDS = {
    "a",
    "an",
    "the",
    "and",
    "or",
    "of",
    "to",
    "in",
    "on",
    "into",
    "onto",
    "with",
    "for",
    "from",
    "at",
    "by",
    "it",
    "its",
    "is",
    "are",
    "was",
    "be",
    "this",
    "that",
    "some",
    "then",
    "up",
    "down",
    "out",
    "over",
    "i",
    "my",
    "me",
    "you",
    "your",
    "did",
    "do",
    "when",
    "what",
    "where",
    "how",
    "which",
    "while",
    "until",
    "about",
    "s",
}


def tokens(text: str) -> list[str]:
    return _WORD.findall(text.lower())


def content_tokens(text: str) -> list[str]:
    return [stem(t) for t in tokens(text) if t not in _STOPWORDS]


def stem(word: str) -> str:
    """A light suffix stripper, good enough for matching 'eggs' with 'egg'."""
    w = word.lower()
    if w in _IRREGULAR:
        return _IRREGULAR[w]
    if len(w) > 4 and w.endswith("ies"):
        return w[:-3] + "y"
    if len(w) > 5 and w.endswith("ing"):
        base = w[:-3]
        if len(base) > 2 and base[-1] == base[-2] and base[-1] not in "lsz":
            base = base[:-1]
        return base
    if len(w) > 4 and w.endswith("ed"):
        base = w[:-2]
        if len(base) > 2 and base[-1] == base[-2] and base[-1] not in "lsz":
            base = base[:-1]
        return base
    if len(w) > 4 and w.endswith(("ches", "shes", "sses", "xes")):
        return w[:-2]
    if len(w) > 3 and w.endswith("s") and not w.endswith(("ss", "us", "is")):
        return w[:-1]
    return w


def normalize_verb(verb: str) -> str:
    """Lowercase base form of the first word, with a small synonym map."""
    words = tokens(verb)
    if not words:
        return "unknown"
    head = words[0]
    base = _IRREGULAR.get(head)
    if base is None:
        base = stem(head) if head.endswith(("ing", "ed")) else head
        if base == head and len(head) > 3 and head.endswith("s") and not head.endswith("ss"):
            base = head[:-1]
    return SYNONYMS.get(base, base)


def normalize_phrase(text: str) -> str:
    """Lowercase, trimmed noun phrase without leading articles."""
    words = tokens(text)
    while words and words[0] in {"a", "an", "the", "some", "my"}:
        words = words[1:]
    return " ".join(words)


_PREPOSITIONS = {
    "with",
    "using",
    "in",
    "into",
    "on",
    "onto",
    "to",
    "for",
    "until",
    "from",
    "over",
    "under",
    "at",
    "by",
    "through",
    "inside",
    "across",
    "around",
    "off",
    "of",
}
_TOOL_MARKERS = {"with", "using"}
_NUMBER_WORDS = {"one", "two", "three", "four", "five", "six", "half", "a", "an", "the", "some"}
_UNITS = {
    "cup",
    "cups",
    "tbsp",
    "tsp",
    "g",
    "kg",
    "ml",
    "l",
    "pinch",
    "slice",
    "slices",
    "tablespoon",
    "tablespoons",
    "teaspoon",
    "teaspoons",
    "piece",
    "pieces",
}
_LEADING = re.compile(r"^\s*(?:step\s*)?(?:\d+[\.\):\-]?|[-*•]|\(\d+\))\s*", re.IGNORECASE)


def strip_numbering(line: str) -> str:
    return _LEADING.sub("", line).strip()


def parse_step_text(text: str) -> tuple[str, str, str]:
    """Heuristic (verb, object, tool) from a procedure line like 'Crack 2 eggs into a bowl'."""
    words = tokens(strip_numbering(text))
    if not words:
        return "unknown", "", ""
    verb = normalize_verb(words[0])
    obj_words: list[str] = []
    tool_words: list[str] = []
    mode = "object"
    for w in words[1:]:
        if w in _PREPOSITIONS:
            if obj_words and mode == "object":
                mode = "tool" if w in _TOOL_MARKERS else "rest"
            elif w in _TOOL_MARKERS:
                mode = "tool"
            continue
        if w.isdigit() or w in _NUMBER_WORDS or w in _UNITS:
            continue
        if mode == "object":
            obj_words.append(w)
        elif mode == "tool":
            tool_words.append(w)
    return verb, " ".join(obj_words[:3]), " ".join(tool_words[:2])


def gerund(verb: str) -> str:
    v = verb.lower()
    if not v or v == "unknown":
        return "doing something"
    if v.endswith("ie"):
        return v[:-2] + "ying"
    if v.endswith("e") and not v.endswith(("ee", "ye", "oe")):
        return v[:-1] + "ing"
    if (
        len(v) >= 3
        and v[-1] not in "aeiouwxy"
        and v[-2] in "aeiou"
        and v[-3] not in "aeiou"
        and v
        in {
            "chop",
            "stir",
            "cut",
            "put",
            "dip",
            "drop",
            "flip",
            "grab",
            "pat",
            "plug",
            "rub",
            "scrub",
            "set",
            "ship",
            "skim",
            "slip",
            "snip",
            "spin",
            "strip",
            "swap",
            "tap",
            "trim",
            "whip",
            "wrap",
            "zip",
            "mop",
            "pop",
            "sit",
        }
    ):
        return v + v[-1] + "ing"
    return v + "ing"


def imperative_title(verb: str, obj: str, tool: str = "") -> str:
    """Deterministic step title, e.g. ('chop', 'onion') -> 'Chop the onion'."""
    v = (verb or "").strip().lower()
    o = normalize_phrase(obj or "")
    if not v or v == "unknown":
        return f"Work on the {o}" if o else "Unclear action"
    title = v.capitalize()
    if o:
        title += f" the {o}"
    t = normalize_phrase(tool or "")
    if t and t not in {"hand", "hands"} and t != o:
        title += f" with the {t}"
    return title


def parse_reference_steps(text: str | None) -> list[str]:
    """Reference procedure (one step per line, optionally numbered) -> clean ordered list."""
    if not text:
        return []
    steps: list[str] = []
    for raw in text.replace("\r", "\n").split("\n"):
        line = strip_numbering(raw.strip())
        line = re.sub(r"\s+", " ", line).strip(" .;:-")
        if len(line) >= 2 and any(ch.isalpha() for ch in line):
            steps.append(line[:200])
    return steps[:60]
