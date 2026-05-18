#!/usr/bin/env python3
"""
Process new inbox/*.md files:
  - Parse Verbs / Vocabulary / Connectors / Adjectives sections
  - Skip words already present in data/*.md (dedup)
  - Call GitHub Models AI to generate conjugations, translations & examples
  - Append to data/*.md
  - Move processed inbox files into inbox/processed/
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INBOX = ROOT / "inbox"
PROCESSED = INBOX / "processed"
DATA = ROOT / "data"

# GitHub Models — OpenAI-compatible endpoint. Free with GITHUB_TOKEN (models:read).
# https://docs.github.com/en/github-models/use-github-models/prototyping-with-ai-models
MODELS_ENDPOINT = "https://models.github.ai/inference/chat/completions"
MODEL = os.environ.get("AI_MODEL", "openai/gpt-4o-mini")
TOKEN = os.environ.get("GITHUB_TOKEN")

if not TOKEN:
    print("ERROR: GITHUB_TOKEN env var not set.", file=sys.stderr)
    sys.exit(1)


# ---------- Parsing -----------------------------------------------------------

SECTION_RE = re.compile(r"^\s*#{1,6}\s*(verbs?|vocabulary|vocab|connectors?|conn|adjectives?|adj)\s*$", re.I)

def parse_inbox_file(path: Path) -> dict[str, list[str]]:
    buckets = {"verbs": [], "vocabulary": [], "connectors": [], "adjectives": []}
    current = None
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        m = SECTION_RE.match(line)
        if m:
            tag = m.group(1).lower()
            if tag.startswith("verb"):
                current = "verbs"
            elif tag.startswith("vocab"):
                current = "vocabulary"
            elif tag.startswith("conn"):
                current = "connectors"
            elif tag.startswith("adj"):
                current = "adjectives"
            continue
        if current and not line.startswith("#"):
            # strip leading list markers
            item = re.sub(r"^[-*\d.\)]+\s*", "", line).strip()
            # GitHub Issue Forms render empty textareas as "_No response_"
            if item and item.lower().strip("_ ") != "no response":
                buckets[current].append(item)
    return buckets


# ---------- Dedup -------------------------------------------------------------

_ARTICLES = ("l'", "l’", "le ", "la ", "les ", "un ", "une ", "des ", "du ", "de la ", "de l'", "de l’")

def _norm(s: str) -> str:
    s = s.strip().lower()
    for a in _ARTICLES:
        if s.startswith(a):
            return s[len(a):].strip()
    return s

def load_existing() -> dict[str, set[str]]:
    """Return a set of already-known normalized words per bucket."""
    known: dict[str, set[str]] = {"verbs": set(), "vocabulary": set(), "connectors": set(), "adjectives": set()}

    verbs_md = DATA / "verbs.md"
    if verbs_md.exists():
        for line in verbs_md.read_text(encoding="utf-8").splitlines():
            m = re.match(r"^\s*##\s+([^\s—-]+)\s*[—-]", line)
            if m:
                known["verbs"].add(_norm(m.group(1)))

    for bucket, fname in [("vocabulary", "vocabulary.md"), ("connectors", "connectors.md"), ("adjectives", "adjectives.md")]:
        f = DATA / fname
        if not f.exists():
            continue
        for line in f.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line.startswith("|") or set(line) <= set("|-: "):
                continue
            cells = [c.strip() for c in line.strip("|").split("|")]
            if not cells:
                continue
            head = cells[0].lower()
            if head in {"word", "masculine", "connector", "pronoun"}:
                continue
            known[bucket].add(_norm(cells[0]))
    return known


def dedup_buckets(buckets: dict[str, list[str]], known: dict[str, set[str]]) -> tuple[dict[str, list[str]], list[str]]:
    """Drop inbox items already present in data/. Returns (filtered, skipped_log)."""
    skipped: list[str] = []
    out: dict[str, list[str]] = {}
    for bucket, items in buckets.items():
        kept: list[str] = []
        seen_now: set[str] = set()
        for item in items:
            key = _norm(item)
            if key in known.get(bucket, set()) or key in seen_now:
                skipped.append(f"{bucket}: {item}")
                continue
            seen_now.add(key)
            kept.append(item)
        out[bucket] = kept
    return out, skipped


# ---------- AI call -----------------------------------------------------------

SYSTEM_PROMPT = """You are a precise French linguistics assistant.
Return ONLY valid JSON matching the schema the user provides — no prose, no markdown fences."""

USER_TEMPLATE = """For the following French words, return a JSON object with this exact schema:

{{
  "verbs": [
    {{
      "infinitive": "manger",
      "english": "to eat",
      "present":   {{"je":"mange","tu":"manges","il":"mange","nous":"mangeons","vous":"mangez","ils":"mangent"}},
      "passe_compose": {{"je":"ai mangé","tu":"as mangé","il":"a mangé","nous":"avons mangé","vous":"avez mangé","ils":"ont mangé"}},
      "imparfait": {{"je":"mangeais","tu":"mangeais","il":"mangeait","nous":"mangions","vous":"mangiez","ils":"mangeaient"}},
      "futur_simple": {{"je":"mangerai","tu":"mangeras","il":"mangera","nous":"mangerons","vous":"mangerez","ils":"mangeront"}}
    }}
  ],
  "vocabulary": [
    {{"word":"pomme","article":"la","gender":"f","plural":"pommes","english":"apple"}}
  ],
  "connectors": [
    {{"connector":"donc","english":"therefore/so","example_fr":"Il pleut, donc je reste à la maison.","example_en":"It is raining, so I am staying home."}}
  ],
  "adjectives": [
    {{"masc":"grand","fem":"grande","masc_pl":"grands","fem_pl":"grandes","english":"big/tall"}}
  ]
}}

Rules:
- Use correct French elision (j' instead of je) where appropriate inside the conjugation strings.
- For passé composé, include the auxiliary (avoir/être) and past participle with correct agreement for "il" form (masc sing).
- If a word is already given with an article (e.g. "la pomme"), keep it but normalize the article field.
- For connectors, give one short natural example sentence in French and its English translation. Do NOT use the pipe character `|` inside any string.
- Omit any word you cannot confidently produce; do not invent.
- Return ONLY the JSON object, no commentary.

Input:
VERBS: {verbs}
VOCABULARY: {vocab}
CONNECTORS: {connectors}
ADJECTIVES: {adjectives}
"""

def call_ai(buckets: dict[str, list[str]]) -> dict:
    payload = {
        "model": MODEL,
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": USER_TEMPLATE.format(
                verbs=json.dumps(buckets["verbs"], ensure_ascii=False),
                vocab=json.dumps(buckets["vocabulary"], ensure_ascii=False),
                connectors=json.dumps(buckets.get("connectors", []), ensure_ascii=False),
                adjectives=json.dumps(buckets["adjectives"], ensure_ascii=False),
            )},
        ],
    }
    req = urllib.request.Request(
        MODELS_ENDPOINT,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code}: {e.read().decode('utf-8', errors='replace')}", file=sys.stderr)
        raise
    content = body["choices"][0]["message"]["content"]
    return json.loads(content)


# ---------- Rendering ---------------------------------------------------------

def render_verbs(verbs: list[dict], source: str) -> str:
    out = []
    today = date.today().isoformat()
    for v in verbs:
        inf = v.get("infinitive", "?")
        eng = v.get("english", "")
        out.append(f"\n## {inf} — _{eng}_\n")
        out.append(f"<sub>added {today} from `{source}`</sub>\n")
        out.append("| Pronoun | Présent | Passé composé | Imparfait | Futur simple |")
        out.append("|---|---|---|---|---|")
        for p, label in [("je","je"),("tu","tu"),("il","il/elle"),("nous","nous"),("vous","vous"),("ils","ils/elles")]:
            row = [
                label,
                v.get("present",{}).get(p,""),
                v.get("passe_compose",{}).get(p,""),
                v.get("imparfait",{}).get(p,""),
                v.get("futur_simple",{}).get(p,""),
            ]
            out.append("| " + " | ".join(row) + " |")
        out.append("")
    return "\n".join(out)


def render_vocab_rows(vocab: list[dict]) -> str:
    today = date.today().isoformat()
    rows = []
    for w in vocab:
        article = w.get("article", "").strip()
        word = w.get("word", "").strip()
        # Guard against AI returning article already embedded in word (e.g. word="le matin", article="le")
        word_lower = word.lower()
        article_lower = article.lower()
        if article and (word_lower.startswith(article_lower + " ") or word_lower.startswith(article_lower + "'")):
            display = word
        else:
            display = f"{article} {word}".strip()
        rows.append(f"| {display} | {w.get('gender','')} | {w.get('plural','')} | {w.get('english','')} | {today} |")
    return "\n".join(rows) + ("\n" if rows else "")


def render_adj_rows(adjs: list[dict]) -> str:
    today = date.today().isoformat()
    rows = []
    for a in adjs:
        rows.append(f"| {a.get('masc','')} | {a.get('fem','')} | {a.get('masc_pl','')} | {a.get('fem_pl','')} | {a.get('english','')} | {today} |")
    return "\n".join(rows) + ("\n" if rows else "")


def _escape_cell(s: str) -> str:
    return s.replace("|", "\\|").replace("\n", " ").strip()


def render_connector_rows(conns: list[dict]) -> str:
    today = date.today().isoformat()
    rows = []
    for c in conns:
        rows.append(
            "| " + " | ".join([
                _escape_cell(c.get("connector", "")),
                _escape_cell(c.get("english", "")),
                _escape_cell(c.get("example_fr", "")),
                _escape_cell(c.get("example_en", "")),
                today,
            ]) + " |"
        )
    return "\n".join(rows) + ("\n" if rows else "")


def append_file(path: Path, content: str, table: bool = False):
    """Append content to a file.

    When ``table`` is True we keep rows flush against the existing table —
    i.e. no blank line between the separator/last row and the new rows
    (a blank line would terminate the GitHub-Flavored-Markdown table).
    Otherwise we insert a blank line for readability (verbs use H2 sections).
    """
    if not content.strip():
        return
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    existing = existing.rstrip() + "\n"  # exactly one trailing newline
    body = content.lstrip("\n")
    if not table:
        body = "\n" + body  # blank line separator for prose/section files
    if not body.endswith("\n"):
        body += "\n"
    path.write_text(existing + body, encoding="utf-8")


# ---------- Main --------------------------------------------------------------

def main() -> int:
    PROCESSED.mkdir(parents=True, exist_ok=True)
    DATA.mkdir(parents=True, exist_ok=True)

    files = sorted(
        p for p in INBOX.glob("*.md")
        if p.name not in {"EXAMPLE.md"} and not p.name.startswith(".")
    )
    if not files:
        print("No inbox files to process.")
        return 0

    any_changes = False
    for f in files:
        print(f"Processing {f.name} …")
        buckets = parse_inbox_file(f)
        known = load_existing()
        buckets, skipped = dedup_buckets(buckets, known)
        if skipped:
            print(f"  skipped {len(skipped)} duplicate(s): {', '.join(skipped)}")
        total = sum(len(v) for v in buckets.values())
        if total == 0:
            print(f"  (nothing new, skipping)")
            f.rename(PROCESSED / f.name)
            continue

        result = call_ai(buckets)

        append_file(DATA / "verbs.md",      render_verbs(result.get("verbs", []), f.name))
        append_file(DATA / "vocabulary.md", render_vocab_rows(result.get("vocabulary", [])), table=True)
        append_file(DATA / "connectors.md", render_connector_rows(result.get("connectors", [])), table=True)
        append_file(DATA / "adjectives.md", render_adj_rows(result.get("adjectives", [])), table=True)

        f.rename(PROCESSED / f.name)
        any_changes = True
        print(f"  ✓ done")

    if not any_changes:
        print("Nothing to commit.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
