"""确定性去重：URL 规范化 + content_hash。"""
from __future__ import annotations

import hashlib
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

TRACKING_PARAMS = {
    "ref", "ref_src", "ref_url", "referrer", "fbclid", "gclid", "dclid", "msclkid", "yclid",
    "igshid", "mc_cid", "mc_eid", "spm", "cmpid", "ncid", "guccounter", "guce_referrer",
    "guce_referrer_sig", "_hsenc", "_hsmi", "mkt_tok", "share", "source", "gift",
}
TRACKING_PREFIXES = ("utm_", "pk_", "hsa_", "at_")


def canonicalize_url(url: str | None) -> str:
    if not url:
        return ""
    parts = urlsplit(url.strip())
    if not parts.netloc:
        return url.strip()
    host = parts.netloc.lower().removeprefix("www.")
    query = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if k.lower() not in TRACKING_PARAMS and not k.lower().startswith(TRACKING_PREFIXES)
    ]
    path = parts.path.rstrip("/") or ""
    return urlunsplit(("https", host, path, urlencode(sorted(query)), ""))


def normalize_title(title: str) -> str:
    return re.sub(r"[\W_]+", " ", title.lower()).strip()


def _sha(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def url_hash(canonical_url: str) -> str | None:
    """跨来源相同链接的指纹（HN 帖子指向的文章 == 媒体 RSS 里的同一篇）。"""
    return _sha(canonical_url) if canonical_url else None


def content_hash(source: str, title: str, canonical_url: str) -> str:
    """同一来源内的唯一键。

    有 URL 时只用 URL：标题经常被编辑（HN 版主改标题、媒体改稿），
    把标题也算进去会让同一篇文章重复入库。没有 URL 才退回标题。
    带上 source 是为了保留"多个独立来源都在提这件事"这个信号。
    """
    key = canonical_url or normalize_title(title)
    return _sha(f"{source}|{key}")
