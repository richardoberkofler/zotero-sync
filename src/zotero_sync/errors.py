class ZoteroSyncError(Exception):
    """Base error for zotero-sync; message is shown to the user as-is."""


class PreconditionError(ZoteroSyncError):
    """Raised when Zotero/Better BibTeX isn't reachable before a sync starts."""


class SchemaDriftError(ZoteroSyncError):
    """Raised when zotero.sqlite's schema no longer matches what we expect."""
