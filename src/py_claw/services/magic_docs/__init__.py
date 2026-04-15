"""
MagicDocs service.

Automatically maintains markdown files marked with # MAGIC DOC: header.
"""
from py_claw.services.magic_docs.config import (
    MAGIC_DOC_HEADER,
    MagicDocsConfig,
    get_magic_docs_config,
    set_magic_docs_config,
)
from py_claw.services.magic_docs.service import (
    get_magic_docs_stats,
    is_magic_doc,
    parse_magic_doc,
    scan_for_magic_docs,
    update_magic_doc,
)
from py_claw.services.magic_docs.types import MagicDoc, MagicDocStats, MagicDocUpdate


__all__ = [
    "MagicDocsConfig",
    "MagicDoc",
    "MagicDocStats",
    "MagicDocUpdate",
    "MAGIC_DOC_HEADER",
    "get_magic_docs_config",
    "set_magic_docs_config",
    "scan_for_magic_docs",
    "parse_magic_doc",
    "is_magic_doc",
    "update_magic_doc",
    "get_magic_docs_stats",
]
