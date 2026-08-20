#!/usr/bin/env python3
"""Holdout task generator (order §29) — deterministic, sealed BEFORE the
candidate is frozen. The generated tasks are NEVER inspected by the
weakness mining / candidate phase; the split manifest seals id+hash.

Generates 24 text-utility tasks, each with exactly ONE subtle bug and a
test suite with exactly one failing test function. Seed-based
(deterministic). Every module has a COMPLETE correct skeleton (None/empty
handling included) and exactly one wrong detail.
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys

SEED = "HAMH-HOLDOUT-2026-08-21"
OUT_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "holdout", "tasks"
)
MANIFEST = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..",
    "holdout",
    "eval-split-manifest.json",
)

# Each task: module name, function, complete CORRECT module skeleton
# (as template with {body} for the buggy core), buggy body, correct body,
# and 5 test functions where EXACTLY ONE fails on the buggy body.
TASKS = [
    {
        "module": "slugger",
        "fn": "slugify",
        "skeleton": (
            '"""Convert text to a lowercase URL slug with accent '
            'transliteration."""\n\n'
            "import re\n\n\n"
            "def slugify(text):\n"
            "    if text is None:\n"
            '        return ""\n'
            "{body}\n"
        ),
        "buggy": (
            '    mapping = {"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"}\n'
            "    # BUG: accented Latin characters (é, è, à, ç, ñ, ô, û) are\n"
            "    # dropped instead of transliterated\n"
            "    lowered = str(text).lower()\n"
            "    for s, d in mapping.items():\n"
            "        lowered = lowered.replace(s, d)\n"
            '    out = re.sub(r"[^a-z0-9-]+", "-", lowered)\n'
            '    return re.sub(r"-{2,}", "-", out).strip("-")'
        ),
        "correct": (
            '    mapping = {"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss",\n'
            '               "é": "e", "è": "e", "à": "a", "ç": "c", "ñ": "n",\n'
            '               "ô": "o", "û": "u", "î": "i"}\n'
            "    lowered = str(text).lower()\n"
            "    for s, d in mapping.items():\n"
            "        lowered = lowered.replace(s, d)\n"
            '    out = re.sub(r"[^a-z0-9-]+", "-", lowered)\n'
            '    return re.sub(r"-{2,}", "-", out).strip("-")'
        ),
        "tests": [
            "def test_slugify_basic():\n"
            '    assert slugify("Hello World") == "hello-world"\n'
            '    assert slugify("A--B") == "a-b"\n',
            "def test_slugify_edge():\n"
            '    assert slugify("Python & JavaScript") == "python-javascript"\n'
            '    assert slugify("  spaced   out  ") == "spaced-out"\n',
            "def test_slugify_umlauts():\n"
            '    assert slugify("München") == "muenchen"\n'
            '    assert slugify("Straße") == "strasse"\n',
            "def test_slugify_accented():\n"
            '    assert slugify("café") == "cafe"\n'
            '    assert slugify("crème brûlée") == "creme-brulee"\n'
            '    assert slugify("jalapeño") == "jalapeno"\n',  # FAILS on buggy
            "def test_slugify_empty():\n"
            '    assert slugify(None) == ""\n'
            '    assert slugify("") == ""\n'
            '    assert slugify("---") == ""\n',
        ],
    },
    {
        "module": "counter",
        "fn": "word_count",
        "skeleton": (
            '"""Count words in text (hyphenated words count as one)."""\n\n'
            "import re\n\n\n"
            "def word_count(text):\n"
            "    if text is None:\n"
            "        return 0\n"
            "{body}\n"
        ),
        "buggy": (
            "    # BUG: \\w+ splits hyphenated words (one-two -> 2)\n"
            '    return len(re.findall(r"\\w+", str(text)))'
        ),
        "correct": ("    return len(str(text).split())"),
        "tests": [
            "def test_word_count_basic():\n"
            '    assert word_count("hello world") == 2\n'
            '    assert word_count("  a   b  ") == 2\n',
            "def test_word_count_punctuation():\n"
            '    assert word_count("Hello, world!") == 2\n'
            '    assert word_count("a b c") == 3\n',
            "def test_word_count_hyphen():\n"
            '    assert word_count("one-two") == 1\n',  # FAILS on buggy (2)
            "def test_word_count_unicode():\n"
            '    assert word_count("grüße welt") == 2\n'
            '    assert word_count("über") == 1\n',
            "def test_word_count_empty():\n"
            '    assert word_count("") == 0\n'
            "    assert word_count(None) == 0\n",
        ],
    },
    {
        "module": "numextract",
        "fn": "extract_numbers",
        "skeleton": (
            '"""Extract integers from a string, preserving sign."""\n\n'
            "import re\n\n\n"
            "def extract_numbers(text):\n"
            "    if text is None:\n"
            "        return []\n"
            "{body}\n"
        ),
        "buggy": (
            "    # BUG: sign is dropped (negative numbers come back positive)\n"
            '    return [int(m) for m in re.findall(r"\\d+", str(text))]'
        ),
        "correct": ('    return [int(m) for m in re.findall(r"-?\\d+", str(text))]'),
        "tests": [
            "def test_extract_numbers_basic():\n"
            '    assert extract_numbers("a1b22c333") == [1, 22, 333]\n',
            "def test_extract_numbers_negative():\n"
            '    assert extract_numbers("temp -5 and 10") == [-5, 10]\n',  # FAILS
            "def test_extract_numbers_mixed():\n"
            '    assert extract_numbers("+8 and 9") == [8, 9]\n'
            '    assert extract_numbers("x7y") == [7]\n',
            "def test_extract_numbers_versions():\n"
            '    assert extract_numbers("v1.2.3") == [1, 2, 3]\n',
            "def test_extract_numbers_empty():\n"
            '    assert extract_numbers("") == []\n'
            "    assert extract_numbers(None) == []\n"
            '    assert extract_numbers("abc") == []\n',
        ],
    },
    {
        "module": "namer",
        "fn": "camel_to_snake",
        "skeleton": (
            '"""Convert camelCase to snake_case (acronyms handled)."""\n\n'
            "import re\n\n\n"
            "def camel_to_snake(text):\n"
            "    if text is None:\n"
            '        return ""\n'
            "{body}\n"
        ),
        "buggy": (
            "    # BUG: consecutive capitals (acronyms) get an extra\n"
            "    # underscore between each letter\n"
            '    out = re.sub(r"(?<=[a-z0-9])([A-Z])", r"_\\1", str(text))\n'
            "    return out.lower()"
        ),
        "correct": (
            '    out = re.sub(r"(?<=[a-z0-9])([A-Z])", r"_\\1", str(text))\n'
            '    out = re.sub(r"([A-Z])([A-Z])(?=[a-z])", r"\\1_\\2", out)\n'
            "    return out.lower()"
        ),
        "tests": [
            "def test_camel_to_snake_basic():\n"
            '    assert camel_to_snake("helloWorld") == "hello_world"\n',
            "def test_camel_to_snake_acronym():\n"
            '    assert camel_to_snake("HTTPServer") == "http_server"\n',  # FAILS
            "def test_camel_to_snake_multi():\n"
            '    assert camel_to_snake("helloWorld") == "hello_world"\n'
            '    assert camel_to_snake("already_snake") == "already_snake"\n',
            "def test_camel_to_snake_unicode():\n"
            '    assert camel_to_snake("größeWert") == "größe_wert"\n',
            "def test_camel_to_snake_empty():\n"
            '    assert camel_to_snake("") == ""\n'
            '    assert camel_to_snake(None) == ""\n'
            '    assert camel_to_snake("X") == "x"\n',
        ],
    },
    {
        "module": "truncator",
        "fn": "truncate",
        "skeleton": (
            '"""Truncate text to max_chars with an ellipsis."""\n\n\n'
            "def truncate(text, max_chars):\n"
            "    if text is None:\n"
            '        return ""\n'
            "    if len(text) <= max_chars:\n"
            "        return text\n"
            "{body}\n"
        ),
        "buggy": (
            "    # BUG: for max_chars <= 3 the slice index goes negative\n"
            "    # and keeps too many characters\n"
            '    return text[:max_chars - 3] + "..."'
        ),
        "correct": (
            "    if max_chars <= 3:\n"
            '        return "..."\n'
            '    return text[:max_chars - 3] + "..."'
        ),
        "tests": [
            "def test_truncate_basic():\n"
            '    assert truncate("hello world", 5) == "he..."\n'
            '    assert truncate("short", 10) == "short"\n',
            "def test_truncate_exact():\n"
            '    assert truncate("exactly", 7) == "exactly"\n'
            '    assert truncate("abcdef", 6) == "abcdef"\n',
            "def test_truncate_sentence():\n"
            '    assert truncate("a very long sentence here", 8) == "a ver..."\n',
            "def test_truncate_small_max():\n"
            '    assert truncate("hello", 2) == "..."\n',  # FAILS on buggy
            "def test_truncate_empty():\n"
            '    assert truncate("", 5) == ""\n'
            '    assert truncate(None, 5) == ""\n',
        ],
    },
    {
        "module": "capitalizer",
        "fn": "title_case",
        "skeleton": (
            '"""Capitalize words, keeping small words lowercase."""\n\n\n'
            'SMALL = {"and", "of", "the", "a", "an"}\n\n\n'
            "def title_case(text):\n"
            "    if text is None:\n"
            '        return ""\n'
            "    if not str(text).strip():\n"
            '        return ""\n'
            "{body}\n"
        ),
        "buggy": (
            "    # BUG: small words are capitalized too\n"
            '    return " ".join(w.capitalize() for w in str(text).split())'
        ),
        "correct": (
            "    words = str(text).split()\n"
            "    out = []\n"
            "    for i, w in enumerate(words):\n"
            "        if i > 0 and w.lower() in SMALL:\n"
            "            out.append(w.lower())\n"
            "        else:\n"
            "            out.append(w.capitalize())\n"
            '    return " ".join(out)'
        ),
        "tests": [
            "def test_title_case_basic():\n"
            '    assert title_case("hello world") == "Hello World"\n',
            "def test_title_case_small_words():\n"
            '    assert title_case("the lord of the rings") == "The Lord of the Rings"\n',  # FAILS
            "def test_title_case_more_small():\n"
            '    assert title_case("Deep Learning") == "Deep Learning"\n'
            '    assert title_case("Open Source") == "Open Source"\n',
            "def test_title_case_unicode():\n"
            '    assert title_case("über alles") == "Über Alles"\n',
            "def test_title_case_empty():\n"
            '    assert title_case("") == ""\n'
            '    assert title_case(None) == ""\n'
            '    assert title_case("   ") == ""\n',
        ],
    },
]

READMES = [
    "Fix the bug in `slugger.py` ONLY (never modify the test file).\n"
    "Verify: python3 -m pytest test_slugger.py -q\n",
    "Fix the bug in `counter.py` ONLY (never modify the test file).\n"
    "Verify: python3 -m pytest test_counter.py -q\n",
    "Fix the bug in `numextract.py` ONLY (never modify the test file).\n"
    "Verify: python3 -m pytest test_numextract.py -q\n",
    "Fix the bug in `namer.py` ONLY (never modify the test file).\n"
    "Verify: python3 -m pytest test_namer.py -q\n",
    "Fix the bug in `truncator.py` ONLY (never modify the test file).\n"
    "Verify: python3 -m pytest test_truncator.py -q\n",
    "Fix the bug in `capitalizer.py` ONLY (never modify the test file).\n"
    "Verify: python3 -m pytest test_capitalizer.py -q\n",
]


def main():
    if os.path.isdir(OUT_DIR):
        shutil.rmtree(OUT_DIR)
    os.makedirs(OUT_DIR, exist_ok=True)
    manifest = {"seed": SEED, "generated": 0, "tasks": {}, "sealed": True}
    idx = 0
    for task in TASKS:
        for variant in range(4):
            idx += 1
            task_id = "ho-%03d" % idx
            d = os.path.join(OUT_DIR, task_id)
            os.makedirs(d, exist_ok=True)
            module = task["module"]
            fn = task["fn"]
            with open(os.path.join(d, module + ".py"), "w") as f:
                f.write(task["skeleton"].replace("{body}", task["buggy"]) + "\n")
            test_lines = ["from %s import %s\n\n\n" % (module, fn)]
            for t in task["tests"]:
                test_lines.append(t + "\n")
            with open(os.path.join(d, "test_" + module + ".py"), "w") as f:
                f.write("".join(test_lines))
            with open(os.path.join(d, "README.md"), "w") as f:
                f.write("# Holdout Task %s\n\n%s\n" % (task_id, READMES[(idx - 1) // 4]))
            # verify: EXACTLY one failing test function, others green
            r = subprocess.run(
                ["python3", "-m", "pytest", "test_" + module + ".py", "-q"],
                cwd=d,
                capture_output=True,
                text=True,
                timeout=60,
            )
            out = r.stdout + r.stderr
            failed_count = out.count("FAILED test_")
            ok = failed_count == 1 and "passed" in out
            if not ok:
                print(
                    "TASK %s VERIFY-FAIL: %s"
                    % (task_id, out.splitlines()[-2] if out.splitlines() else "?")
                )
                return 1
            for a in ("__pycache__", ".pytest_cache", ".benchmarks", ".deepeval"):
                q = os.path.join(d, a)
                if os.path.isdir(q):
                    shutil.rmtree(q)
            h = hashlib.sha256()
            for fn_name in sorted(os.listdir(d)):
                pth = os.path.join(d, fn_name)
                if os.path.isfile(pth):
                    with open(pth, "rb") as f:
                        h.update(fn_name.encode() + f.read())
            manifest["tasks"][task_id] = {
                "module": module,
                "fn": fn,
                "variant": variant,
                "sha256": h.hexdigest(),
            }
    manifest["generated"] = idx
    with open(MANIFEST, "w") as f:
        json.dump(manifest, f, indent=2, sort_keys=True)
    print("GENERATED %d holdout tasks (alle: genau 1 failed, 5 passed)" % idx)
    print("MANIFEST sealed -> %s" % MANIFEST)
    return 0


if __name__ == "__main__":
    sys.exit(main())
