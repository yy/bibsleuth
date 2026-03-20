"""LLM client wrapper using litellm."""

from __future__ import annotations

from ..config import Config


def _check_litellm():
    try:
        import litellm  # noqa: F401
    except ImportError:
        raise ImportError(
            "LLM features require litellm. Install with: uv pip install 'bibsleuth[llm]' or uv sync --extra llm"
        )


async def complete(prompt: str, config: Config) -> str:
    """Send a completion request to the configured LLM."""
    _check_litellm()
    import litellm

    response = await litellm.acompletion(
        model=config.llm_model,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.choices[0].message.content
