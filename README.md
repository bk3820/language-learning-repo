# 🇫🇷 French Learning Journal

A repo that automatically processes daily French notes using **AI via GitHub Actions** (powered by [GitHub Models](https://docs.github.com/en/github-models) — free, no API key needed).

## How it works

1. Each day, create a file in `inbox/` named `YYYY-MM-DD.md` (or anything ending in `.md`).
2. Paste what you learned today using the simple format below.
3. Commit & push. A GitHub Action runs, calls AI, and:
   - Conjugates every **verb** into _présent / passé composé / imparfait / futur simple_ and appends to [data/verbs.md](data/verbs.md).
   - Adds **vocabulary** with English meanings + gender/plural to [data/vocabulary.md](data/vocabulary.md).
   - Adds **adjectives** with masc/fem/plural forms + meaning to [data/adjectives.md](data/adjectives.md).
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
maison

## Adjectives
grand
heureux
beau
```

Section headers are case-insensitive. Empty sections are fine. One item per line.

## Running locally (optional)

```bash
export GITHUB_TOKEN=ghp_xxx   # any token with `models:read` scope
python3 scripts/process.py
```

## Setup

1. Create a new GitHub repo and push this code.
2. In repo **Settings → Actions → General → Workflow permissions**, enable **Read and write permissions**.
3. Done — every push to `inbox/*.md` triggers the AI processing.
