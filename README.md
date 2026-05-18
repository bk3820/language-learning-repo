# 🇫🇷 French Learning Journal

A repo that automatically processes daily French notes using **AI via GitHub Actions** (powered by [GitHub Models](https://docs.github.com/en/github-models) — free, no API key needed).

## How it works

1. Each day, create a file in `inbox/` named `YYYY-MM-DD.md` (or anything ending in `.md`).
2. Paste what you learned today using the simple format below.
3. Commit & push. A GitHub Action runs, calls AI, and:
   - Conjugates every **verb** into _présent / passé composé / imparfait / futur simple_ → [data/verbs.md](data/verbs.md).
   - Adds **vocabulary** with English meaning + gender/plural → [data/vocabulary.md](data/vocabulary.md).
   - Adds **connectors** with meaning + example sentence (FR/EN) → [data/connectors.md](data/connectors.md).
   - Adds **adjectives** with masc/fem/plural forms + meaning → [data/adjectives.md](data/adjectives.md).
   - **Dedup**: any word already present in `data/*.md` is skipped automatically (safe to re-paste).
   - Moves processed files to `inbox/processed/`.

## Inbox file format

```markdown
## Verbs
manger
finir
aller

## Vocabulary
la pomme
le chien
la maison

## Connectors
donc
parce que
cependant

## Adjectives
grand
heureux
beau
```

Section headers are case-insensitive. Empty sections are fine. One item per line.

## ChatGPT prompt to generate a daily list

Paste this into ChatGPT (or any LLM), tweak the topic/level, and copy the output straight into a new `inbox/YYYY-MM-DD.md` file.

````text
You are helping me build a French learning journal. Output a daily study list in the EXACT Markdown format below — nothing else, no commentary, no code fences.

Topic: <e.g. "at the restaurant" / "describing people" / "common B1 vocab">
Level: B1 (intermediate)
Counts: 5 verbs, 10 vocabulary words, 5 connectors, 5 adjectives

Rules:
- One item per line, no bullets, no numbering, no translations, no parentheses.
- Verbs: infinitive only (e.g. "manger", not "to eat" or "je mange").
- Vocabulary: include the definite article ("le", "la", "l'", "les") before each noun.
- Connectors: French only (e.g. "donc", "parce que", "cependant").
- Adjectives: masculine singular form only (e.g. "grand", not "grande/grands").
- No duplicates with these already-learned words: <paste current list here, or "none">.
- Keep section headers EXACTLY as shown (## Verbs, ## Vocabulary, ## Connectors, ## Adjectives).

Output this and only this:

## Verbs
<verb 1>
<verb 2>
<verb 3>
<verb 4>
<verb 5>

## Vocabulary
<article + noun 1>
<article + noun 2>
<article + noun 3>
<article + noun 4>
<article + noun 5>
<article + noun 6>
<article + noun 7>
<article + noun 8>
<article + noun 9>
<article + noun 10>

## Connectors
<connector 1>
<connector 2>
<connector 3>
<connector 4>
<connector 5>

## Adjectives
<adjective 1>
<adjective 2>
<adjective 3>
<adjective 4>
<adjective 5>
````

## Running locally (optional)

```bash
export GITHUB_TOKEN=ghp_xxx   # any token with `models:read` scope
python3 scripts/process.py
```

## Setup

1. Create a new GitHub repo and push this code.
2. In repo **Settings → Actions → General → Workflow permissions**, enable **Read and write permissions**.
3. Done — every push to `inbox/*.md` triggers the AI processing.
