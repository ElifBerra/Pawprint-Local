# Pawprint-Local

An offline pet health assistant. Ask a question in plain language and get an
answer drawn from a local document collection, with the source passages shown.
No internet connection, no cloud account, no API key — the language model runs
on the machine you are sitting at.

Built with [Microsoft Foundry Local](https://learn.microsoft.com/en-us/azure/foundry-local/what-is-foundry-local)
and the retrieval-augmented generation (RAG) pattern.

```
you > My cat is straining in the litter box, is that urgent?

Yes, your cat straining in the litter box with little or no urine production
could indicate a urethral obstruction, which is a medical emergency,
especially in male cats. Contact an emergency veterinary clinic right away.

Sources: emergency-signs.md
[10.6s]
This is not veterinary advice. See a vet for anything urgent.
```

## Why this exists

Ask a general-purpose model a specific question and it will often answer
confidently and wrongly. Before this project had a retrieval layer, we asked
`phi-3.5-mini` what RAG stands for and it replied:

> "RAG stands for Restart, Adapt, and Growth, a strategy often used by
> companies, particularly in the energy sector..."

Fluent, formatted, entirely invented, and nothing in the answer signals that.
RAG addresses this by retrieving relevant passages from a trusted collection
and requiring the model to answer from those passages, citing them. When
nothing relevant is found, the assistant says so instead of guessing.

## How it works

```
                    ┌──────────────────────────────────────┐
   question  ─────► │  1. embed the question               │
                    │     qwen3-embedding-0.6b  (1024-dim) │
                    └──────────────┬───────────────────────┘
                                   ▼
                    ┌──────────────────────────────────────┐
                    │  2. cosine similarity vs every chunk │
                    │     SQLite, float32 BLOBs            │
                    └──────────────┬───────────────────────┘
                                   ▼
                        best score ≥ 0.48 ?
                          │                │
                       no │                │ yes
                          ▼                ▼
              "I don't have that   ┌───────────────────────────┐
               information in my   │  3. build prompt from     │
               documents."         │     top 3 chunks          │
                  (0.5s, model     └───────────┬───────────────┘
                   never called)               ▼
                                   ┌───────────────────────────┐
                                   │  4. generate              │
                                   │     phi-3.5-mini, on CPU  │
                                   └───────────┬───────────────┘
                                               ▼
                                    answer + source citations
```

The similarity threshold in step 2 does real work: out-of-scope questions never
reach the model, which makes them both correct and fast (0.5s instead of 15s).

Ingestion runs the same embedding model over the documents once, ahead of time:
split into heading-bounded chunks → embed → store in SQLite.

## Requirements

- Windows, macOS, or Linux
- Python 3.10 or newer (developed on 3.12)
- About 4 GB of disk space for the models
- No GPU required — everything runs on CPU

The Foundry Local SDK bundles its own runtime, so the `foundry` CLI is not
needed.

## Setup

```powershell
git clone https://github.com/ElifBerra/Pawprint-Local.git
cd Pawprint-Local

py -3.12 -m venv venv
.\venv\Scripts\Activate.ps1
```

On macOS or Linux use `python3 -m venv venv` and `source venv/bin/activate`.

If PowerShell blocks activation:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\venv\Scripts\Activate.ps1
```

Your prompt should now start with `(venv)`. Then:

```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Check the environment before going further. This prints your Python version,
the installed packages, and the full list of model aliases available on your
machine:

```powershell
python scripts/check_env.py
```

Download the models. First run only; roughly 4 GB, and it prints progress so a
stalled download is visible:

```powershell
python -m scripts.download_models
```

Build the knowledge base from `data/docs`:

```powershell
python -m src.ingest
```

Expected output ends with something like:

```
  chunks   : 44
  sources  : 6
  avg chars: 472
```

## Usage

Command line:

```powershell
python -m src.cli
```

Answers stream as they are generated. Commands: `/sources` shows the passages
behind the last answer with their similarity scores, `/help`, `/exit`.

Web interface:

```powershell
streamlit run src/app.py
```

The sidebar exposes the number of retrieved chunks and the relevance threshold
as live controls, so you can watch a question cross the decision boundary.

## Using your own documents

Replace the files in `data/docs` with your own `.md` or `.txt` files and
rebuild:

```powershell
python -m src.ingest --rebuild
```

Two things matter for retrieval quality. Use Markdown headings — chunks never
cross one, so headings decide where passages begin and end. And keep each
section on a single subject, because a section covering two topics produces a
chunk that matches both weakly.

## Configuration

Everything tunable lives in `src/config.py`:

| Setting | Default | What it does |
|---|---|---|
| `CHUNK_SIZE` | 200 | Target words per chunk |
| `CHUNK_OVERLAP` | 30 | Words repeated between consecutive chunks |
| `TOP_K` | 3 | Chunks placed in the prompt |
| `SIM_THRESHOLD` | 0.48 | Below this, the question is out of scope |
| `MAX_TOKENS` | 256 | Cap on answer length |
| `CHAT_MODEL_ALIAS` | `phi-3.5-mini` | Generation model |
| `EMBEDDING_MODEL_ALIAS` | `qwen3-embedding-0.6b` | Embedding model |

These are not arbitrary. Each was measured; see
[docs/EVALUATION.md](docs/EVALUATION.md).

## Results

Graded on 23 questions: 17 answerable from the documents, 6 not. Four of the
six negatives are pet-health questions that the documents simply do not cover,
which is a harder test of the threshold than an obviously unrelated question.

| Metric | Result |
|---|---|
| Retrieval accuracy (correct document in top 3) | 17/17 |
| Answered when it should | 17/17 |
| Declined when it should | 6/6 |
| Median latency | 13.9s |
| Out-of-scope latency | 0.5s |

Tuning reduced median latency from 33.3s to 13.3s on the development set with
no loss of accuracy, by changing chunking and retrieval settings only — the
model and the hardware stayed the same.

## Testing

```powershell
pytest                                          # 26 unit tests, no models needed
python -m scripts.bench                         # 8-question latency check
python -m tests.run_eval --save docs/eval-results.md   # full graded run
```

## Project layout

```
src/
  config.py       every tunable setting
  foundry.py      the only module that talks to the Foundry Local SDK
  chunking.py     heading-bounded document splitting
  embeddings.py   text to vectors
  db.py           SQLite storage
  ingest.py       documents -> chunks -> embeddings -> database
  retrieve.py     cosine similarity search and the relevance threshold
  llm.py          chat client wrapper
  rag.py          the pipeline
  cli.py          terminal interface
  app.py          Streamlit interface
  models.py       shared data types

data/docs/        the knowledge base
tests/            unit tests and the evaluation set
scripts/          diagnostics and benchmarks
docs/             evaluation, architecture, known issues
```

## Limitations

- **Not veterinary advice.** The assistant is limited to a small document
  collection and cannot examine an animal. Anything urgent needs a vet.
- Retrieval compares the query against every chunk. Fine for hundreds of
  chunks, wrong approach for hundreds of thousands.
- English documents only; the embedding model supports other languages but
  nothing here has been measured with them.
- Single-turn. The assistant does not remember earlier questions, so follow-ups
  like "and for cats?" will not work.
- Answers vary slightly between runs. Retrieval is deterministic; generation is
  not.

## Troubleshooting

Common problems and how to diagnose them are in
[docs/KNOWN_ISSUES.md](docs/KNOWN_ISSUES.md) — start there if a script appears
to hang.

## Documentation

- [docs/EVALUATION.md](docs/EVALUATION.md) — every tuning run, what was
  measured, what was reverted and why
- [docs/KNOWN_ISSUES.md](docs/KNOWN_ISSUES.md) — troubleshooting
- [docs/COLLABORATION.md](docs/COLLABORATION.md) — how the two of us worked on
  one machine

## Authors

Elif Berra Çelik and Burak Deniz Kaymak.
Microsoft AI Innovators summer program, 2026.
