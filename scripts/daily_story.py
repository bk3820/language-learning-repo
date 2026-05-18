#!/usr/bin/env python3
"""
Generate a daily French story (~150 words) and append it to data/stories.md.

Usage:
  python3 scripts/daily_story.py

Environment variables:
  GITHUB_TOKEN  — required (models:read permission)
  AI_MODEL      — optional, defaults to openai/gpt-4o-mini
  ADD_TO_VOCAB  — set to "true" to also write an inbox file and run process.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
INBOX = ROOT / "inbox"
STORIES_MD = DATA / "stories.md"

MODELS_ENDPOINT = "https://models.github.ai/inference/chat/completions"
MODEL = os.environ.get("AI_MODEL", "openai/gpt-4o-mini")
TOKEN = os.environ.get("GITHUB_TOKEN")
ADD_TO_VOCAB = os.environ.get("ADD_TO_VOCAB", "false").lower() == "true"

if not TOKEN:
    print("ERROR: GITHUB_TOKEN env var not set.", file=sys.stderr)
    sys.exit(1)


# ---------- AI call -----------------------------------------------------------

SYSTEM_PROMPT = (
    "You are a French language teacher creating engaging daily stories for intermediate learners. "
    "Return ONLY valid JSON — no prose, no markdown fences."
)

USER_TEMPLATE = """Create a French learning story for today ({today}).

Return this exact JSON schema:
{{
  "title": "Une Journée à Paris",
  "story": "The full ~150-word story text in French at A2-B1 level.",
  "vocabulary": [
    {{"word": "matin", "article": "le", "gender": "m", "english": "morning"}},
    {{"word": "fenêtre", "article": "la", "gender": "f", "english": "window"}}
  ],
  "verbs": ["partir", "arriver", "manger"],
  "english_summary": "A 2-sentence English summary of the story."
}}

Requirements:
- Story must be 140-160 words
- 8-12 vocabulary words with correct articles and English meanings
- 3-6 notable verbs (infinitive form) used in the story
- Engaging, culturally relevant to everyday French life
- A2-B1 level French (intermediate beginner)
- Do NOT use the pipe character | anywhere in any string value
- Each run should produce a DIFFERENT story (vary the topic, characters, setting)
"""


def call_ai() -> dict:
    today = date.today().isoformat()
    payload = {
        "model": MODEL,
        "temperature": 0.8,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": USER_TEMPLATE.format(today=today)},
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

def _esc(s: str) -> str:
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def render_story_card(data: dict, today: str, completed: bool = False) -> str:
    title   = _esc(data.get("title", "Histoire du jour"))
    story   = _esc(data.get("story", "")).replace("\n", "<br>")
    summary = _esc(data.get("english_summary", ""))
    vocab   = data.get("vocabulary", [])
    verbs   = data.get("verbs", [])

    completed_attr  = "true" if completed else "false"
    completed_badge = (
        '\n    <span class="story-badge-completed">✅ Added to vocabulary</span>'
        if completed else ""
    )

    vocab_rows = "\n".join(
        f"          <tr>"
        f"<td>{_esc(v.get('article',''))} {_esc(v.get('word',''))}</td>"
        f"<td><em>{_esc(v.get('gender',''))}</em></td>"
        f"<td>{_esc(v.get('english',''))}</td>"
        f"</tr>"
        for v in vocab
    )

    verb_list = ", ".join(f"<strong>{_esc(v)}</strong>" for v in verbs)
    verb_line = (
        f'\n      <p class="story-verbs"><strong>Verbs in this story:</strong> {verb_list}</p>'
        if verbs else ""
    )

    return f"""
<div class="story-card" data-date="{today}" data-completed="{completed_attr}">
  <div class="story-header">
    <h2>📖 {title} <span class="story-date">{today}</span></h2>{completed_badge}
  </div>
  <div class="story-body">
    <p>{story}</p>
    <p class="story-summary">📝 {summary}</p>
  </div>
  <div class="story-vocab-section">
    <button class="toggle-vocab-btn" onclick="toggleVocab(this)">👁️ Show Vocabulary</button>
    <div class="story-vocab hidden">
      <table>
        <thead><tr><th>French</th><th>Gender</th><th>English</th></tr></thead>
        <tbody>
{vocab_rows}
        </tbody>
      </table>{verb_line}
    </div>
  </div>
</div>
"""


# ---------- Inbox file (optional) --------------------------------------------

def create_inbox_file(data: dict, today: str) -> Path:
    """Write an inbox .md file so process.py can add vocab/verbs to data files."""
    INBOX.mkdir(parents=True, exist_ok=True)
    inbox_path = INBOX / f"{today}-story.md"

    vocab = data.get("vocabulary", [])
    verbs = data.get("verbs", [])

    lines = ["# Verbs"]
    lines += [f"- {v}" for v in verbs]
    lines += ["", "# Vocabulary"]
    for v in vocab:
        article = v.get("article", "").strip()
        word = v.get("word", "").strip()
        # Avoid double-article: only prepend article if word doesn't already start with it
        if article and word.lower().startswith(article.lower() + " "):
            display = word
        else:
            display = f"{article} {word}".strip()
        lines.append(f"- {display}")

    inbox_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"  Created inbox file: {inbox_path.name}")
    return inbox_path


def mark_story_completed(today: str):
    """Rewrite the last story card for today with data-completed=true."""
    if not STORIES_MD.exists():
        return
    text = STORIES_MD.read_text(encoding="utf-8")
    updated = text.replace(
        f'data-date="{today}" data-completed="false"',
        f'data-date="{today}" data-completed="true"',
    )
    if updated != text:
        STORIES_MD.write_text(updated, encoding="utf-8")
        # Also insert the completed badge after the h2 if not already there
        badge = '\n    <span class="story-badge-completed">✅ Added to vocabulary</span>'
        # Find the story card for today and add badge if missing
        import re
        pattern = (
            rf'(<div class="story-card" data-date="{today}" data-completed="true">\s*'
            rf'<div class="story-header">\s*<h2>[^<]*</h2>)(\s*</div>)'
        )
        replacement = r'\1' + badge + r'\2'
        text2 = STORIES_MD.read_text(encoding="utf-8")
        text2 = re.sub(pattern, replacement, text2)
        STORIES_MD.write_text(text2, encoding="utf-8")
        print("  ✓ Marked story as completed in data/stories.md")


# ---------- Main --------------------------------------------------------------

def main() -> int:
    today = date.today().isoformat()
    print(f"Generating story for {today}…")

    data = call_ai()
    title = data.get("title", "Histoire du jour")
    vocab_count = len(data.get("vocabulary", []))
    verb_count  = len(data.get("verbs", []))
    print(f"  Story: {title} ({vocab_count} vocab words, {verb_count} verbs)")

    card = render_story_card(data, today, completed=ADD_TO_VOCAB)

    # Ensure stories.md exists with correct header
    if not STORIES_MD.exists():
        STORIES_MD.write_text(
            "---\ntitle: 📖 Daily Stories\n---\n\n"
            "# 📖 Daily French Stories\n\n"
            "A new story is added each day. "
            "Click **Show Vocabulary** to reveal the word list and English meanings.\n\n",
            encoding="utf-8",
        )

    existing = STORIES_MD.read_text(encoding="utf-8").rstrip()
    STORIES_MD.write_text(existing + "\n" + card, encoding="utf-8")
    print("  ✓ Appended story to data/stories.md")

    if ADD_TO_VOCAB:
        create_inbox_file(data, today)
        print("  Running process.py to add vocabulary to data files…")
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "process.py")],
            env=os.environ.copy(),
            capture_output=True,
            text=True,
        )
        print(result.stdout)
        if result.stderr:
            print(result.stderr, file=sys.stderr)
        if result.returncode != 0:
            return result.returncode
        mark_story_completed(today)

    return 0


if __name__ == "__main__":
    sys.exit(main())
