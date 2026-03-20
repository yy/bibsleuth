"""Academic database providers."""

from .arxiv import ArxivProvider
from .crossref import CrossRefProvider
from .dblp import DBLPProvider
from .openalex import OpenAlexProvider
from .pubmed import PubMedProvider
from .semantic_scholar import SemanticScholarProvider

ALL_PROVIDERS = {
    "openalex": OpenAlexProvider,
    "semantic_scholar": SemanticScholarProvider,
    "crossref": CrossRefProvider,
    "arxiv": ArxivProvider,
    "dblp": DBLPProvider,
    "pubmed": PubMedProvider,
}

__all__ = [
    "ALL_PROVIDERS",
    "ArxivProvider",
    "CrossRefProvider",
    "DBLPProvider",
    "OpenAlexProvider",
    "PubMedProvider",
    "SemanticScholarProvider",
]
