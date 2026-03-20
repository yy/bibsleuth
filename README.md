# bibsleuth

Citation verification and analysis for LaTeX papers. Given `.tex` + `.bib` files, bibsleuth checks whether citations exist, detects mis-citations, suggests relevant papers for uncited claims, and surfaces contradicting evidence.

## Install

```bash
pip install bibsleuth           # core (existence checking)
pip install 'bibsleuth[llm]'    # with LLM features (mis-citation, suggestions, contradictions)
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
