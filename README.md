# bibsleuth

Citation verification and analysis for LaTeX papers. Given `.tex` + `.bib` files, bibsleuth checks whether citations exist, detects mis-citations, suggests relevant papers for uncited claims, and surfaces contradicting evidence.

## Install

```bash
uv pip install bibsleuth           # core (existence checking)
uv pip install 'bibsleuth[llm]'    # with LLM features (mis-citation, suggestions, contradictions)
```

Or as a tool:

```bash
uvx bibsleuth check paper.tex
```

## Usage

```bash
bibsleuth check paper.tex                    # auto-discovers .bib
bibsleuth check paper.tex --bib refs.bib     # explicit .bib
bibsleuth check refs.bib                     # bib-only mode
bibsleuth check paper.tex --no-llm           # existence checking only
bibsleuth check paper.tex -o report          # write report.json + report.md
```

### System library

```bash
bibsleuth library add refs.bib       # add verified entries to ~/.bibsleuth/library.bib
bibsleuth library search "networks"  # search your accumulated citations
```

## Quick start: checking your paper before submission

You have a LaTeX paper (`paper.tex`) and its bibliography (`refs.bib`) and want to make sure all references are real and correctly used before submitting.

**Step 1. Check that all cited papers exist.**

```bash
bibsleuth check paper.tex --no-llm
```

This parses your `.bib` file, queries 6 academic databases, and reports which entries are verified, likely matches, or not found. Each result includes a clickable DOI/URL so you can verify yourself. A not-found result doesn't necessarily mean the paper is fake — it may just be missing from the databases — but it's worth double-checking.

**Step 2. Look at the report.**

```bash
bibsleuth check paper.tex --no-llm -o report
```

This writes `report.json` (machine-readable) and `report.md` (human-readable). Open `report.md` to see a summary table and per-entry details. Any entries marked `unverified` or `likely` deserve a closer look. The report also suggests patches — missing DOIs or URLs that bibsleuth found in the databases.

**Step 3. Run the full analysis (requires LLM).**

```bash
export ANTHROPIC_API_KEY=sk-...   # or OPENAI_API_KEY
bibsleuth check paper.tex -o report
```

This adds three LLM-powered checks on top of existence verification:
- **Mis-citation detection**: for each `\cite{}`, does the cited paper's abstract actually support the claim you're making? Flags cases where a citation doesn't match the surrounding text.
- **Missing citation suggestions**: finds claims that could use stronger citations and suggests real papers (verified against databases, not hallucinated).
- **Contradicting evidence**: surfaces well-known papers that argue the opposite of your claims — better to address these proactively than have a reviewer bring them up.

**Step 4. Save verified references to your personal library.**

```bash
bibsleuth library add refs.bib
```

Over time this builds up a personal citation knowledge base at `~/.bibsleuth/library.bib` that you can search across projects:

```bash
bibsleuth library search "network centrality"
```

## Features

1. **Citation existence verification** — queries OpenAlex, Semantic Scholar, CrossRef, arXiv, DBLP, PubMed
2. **Mis-citation detection** (LLM) — checks if cited papers actually support the claims
3. **Missing citation suggestions** (LLM + DB) — suggests papers for uncited claims, verified against databases
4. **Contradicting evidence** (LLM + DB) — surfaces counterarguments from the literature
5. **System-wide BibTeX library** — accumulates verified citations across projects

## Design

LLM as scout, databases as ground truth. The LLM suggests directions (papers, contradictions); databases verify they exist. This avoids hallucinated references while leveraging broad literature knowledge.

## Acknowledgments

Citation existence checking patterns adapted from [CiteSleuth](https://github.com/uncrafted/CiteSleuth) (MIT). Title normalization and verification strategies inspired by [hallucinator](https://github.com/jstrieb/hallucinator).

## License

MIT
