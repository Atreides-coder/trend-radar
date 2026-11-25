from . import github, hackernews, rss  # noqa: F401  导入即注册
from .base import FETCHERS, BaseFetcher, RawItem

__all__ = ["FETCHERS", "BaseFetcher", "RawItem"]
