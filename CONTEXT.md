# zotero-sync

Syncs a Zotero library into an Obsidian vault as an interconnected Markdown note graph: one note per bibliographic item, plus index notes for collections, authors, and tags, all cross-linked.

## Language

**Reference**:
A top-level bibliographic item from Zotero (article, book, webpage, report, etc.) synced into its own note. Not every item is a paper, so "Reference" is the umbrella term regardless of Zotero's `itemType`.
_Avoid_: Paper, Item

**Annotation**:
Any markup a user makes on a PDF in Zotero — highlight, note, underline, or image. Only highlight-type annotations are currently extracted and rendered; the others are a known gap, not a deliberate exclusion.
_Avoid_: Highlight (too narrow — a Highlight is one kind of Annotation, not the whole concept)

**Citekey**:
The stable identifier Better BibTeX assigns to a Reference. Used as the Reference note's filename and as the anchor other notes link to.

**Reference note**:
The per-Reference Markdown file. Has a generated region (frontmatter, links, annotations) rewritten on every sync, and a freeform region below it left untouched.

**Freeform region**:
The part of a Reference note below the generated blocks. Never touched by sync — this is where a user's own notes on a Reference live.

**Index note**:
The note for a Collection, Author, or Tag. Fully regenerated on every sync — frontmatter only, no freeform region. Membership (which References belong to it) isn't listed explicitly; it's read via Obsidian's backlinks panel from the References that link to it.

**Retire**:
What happens to a Reference note when its source item disappears from the synced scope (deleted in Zotero, or moved out of a collection that's the sync's current scope). It moves to `.trash/` rather than being deleted outright.

**Vault**:
The Obsidian vault being synced into.

**Collection**:
Zotero's grouping construct for References. Can nest under a parent Collection; mirrored 1:1 as an index note, with the parent relationship preserved.

**Tag**:
A keyword attached to a Reference in Zotero, either applied by hand or automatically derived. Automatic tags are excluded from Tag index notes by default (`include_auto_tags` config).
_Avoid_: Keyword

**Library**:
The full set of References being synced — either the whole Zotero library, or a single Collection when the sync is scoped to one.

## Sources

zotero-sync reads from three places, each authoritative for something the others don't have:

- **Local API**: Zotero's own local HTTP API — Reference metadata, Collections, Tags.
- **Better BibTeX (BBT)**: a Zotero plugin's local JSON-RPC endpoint — Citekeys, the one fact BBT owns.
- **zotero.sqlite copy**: a temporary copy of Zotero's database — Annotations, since neither API exposes them.
