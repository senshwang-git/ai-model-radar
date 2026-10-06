from . import github_releases, huggingface, news, papers, providers

# name -> module exposing collect(cfg: dict) -> list[Item]
SOURCES = {
    "huggingface": huggingface,
    "providers": providers,
    "github_releases": github_releases,
    "papers": papers,
    "news": news,
}
