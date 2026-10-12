# English Shakespeare corpus

## Coverage

This reader data contains 39 plays and seven poetry collections: the 37 plays on MIT Shakespeare, *The Two Noble Kinsmen*, *King Edward III*, all 154 Sonnets, *A Lover’s Complaint*, *The Rape of Lucrece*, *Venus and Adonis*, *The Passionate Pilgrim*, *Sonnets to Sundry Notes of Music*, and *The Phoenix and the Turtle*.

The 46 work records contain 988 source-derived sections, 40,327 blocks, and 929,366 whitespace-delimited body words. Counts include stage directions and dedicatory/front matter; they are not scholarly word-count claims.

## Provenance and rights

- The principal source is [MIT Shakespeare](https://shakespeare.mit.edu/), whose index identifies the Complete Moby Shakespeare as its electronic source and places the HTML play texts in the public domain. The current MIT site identifies [TheMITTech/shakespeare](https://github.com/TheMITTech/shakespeare) as its upstream. This import pins commit [`6b82db852c7322dd33e95db347f0ddfc812c6409`](https://github.com/TheMITTech/shakespeare/tree/6b82db852c7322dd33e95db347f0ddfc812c6409).
- `sources/mit-shakespeare-6b82db852c7322dd33e95db347f0ddfc812c6409.zip` contains the exact upstream bytes used: the index, 37 complete-play HTML files, 154 sonnet HTML files, three long-poem HTML files, and the `Poetry/various` plain-text collection. The source archive is a deterministic ZIP; it is a bounded textual subset, not a copy of the entire repository.
- [The Two Noble Kinsmen, Project Gutenberg #1506](https://www.gutenberg.org/ebooks/1506) is credited to William Shakespeare and John Fletcher. Snapshot source: <https://www.gutenberg.org/files/1506/1506-h/1506-h.htm>.
- [King Edward III, Project Gutenberg #1770](https://www.gutenberg.org/ebooks/1770) states that the play is attributed in part to William Shakespeare. This attribution is qualified in the reader metadata. Snapshot source: <https://www.gutenberg.org/cache/epub/1770/pg1770.html>.
- Project Gutenberg labels both ebooks public domain in the USA; other jurisdictions may differ. The complete downloaded HTML files, including their Project Gutenberg notices and full licence text, are preserved under `sources/`. See the [Project Gutenberg licence](https://www.gutenberg.org/policy/license.html). Reader extraction excludes web/ebook navigation and the licence boilerplate; redistribution retains the full source and notice files alongside it.
- The source retrieval/verification date is 2026-10-12. `sources/manifest.json` records archive and individual-source SHA-256 digests. The importer checks pinned archive and Gutenberg snapshot checksums before generating output.

## Editorial and alignment limits

- This is a faithful extraction of these historical electronic editions, not a new critical edition. Spelling, punctuation, source line breaks, and source textual anomalies are retained. No modern translation or paraphrase is generated.
- MIT act/scene headings are used as supplied. Some sections are irregular: *Pericles* has act-opening passages and scene divisions absent from explicit HTML headings; some prologues/epilogues occur inside numbered text rather than as separate headings. Those passages remain in source order. We do not invent missing headings or imply correspondence with another edition’s sections.
- Empty act-heading containers are omitted from the navigation. The two induction scenes of *The Taming of the Shrew* use act `0`; the source’s numbered line anchors use that act value.
- MIT Sonnet CLIV ends with complete verse but omits closing HTML tags. The parser preserves the final stanza at EOF; all 154 poems, including its 14 lines, are present.
- Apparent line and stanza counts may differ from editorial norms because the source HTML includes wrapped verse lines or combined stanzas. Source wording is not adjusted to force a standard count.
- The historical *Passionate Pilgrim* and *Sundry Notes* collections include work by other writers. The MIT plain-text source divides them as I–XV and XVI–XXI, respectively. They are retained as anthology units with this qualification; they are not represented as wholly Shakespeare-authored.
- The MIT-linked *Funeral Elegy by W.S.* is not imported. Its presence on the old MIT index is not a reason to attribute it to Shakespeare or to add it to the user’s collection.
- This data contains English only. No bilingual paragraph alignment is asserted. Pairing by work and independently selecting each edition’s sections is intentional.

## Reader API

`catalog.js` assigns `window.SHAKESPEARE_ENGLISH_CATALOG` to a summary array. `catalog.json` contains the same data. Each summary has `id`, `title`, `kind`, `sourceLabel`, `sourceUrl`, `file`, counts, and section metadata.

Each `{id}.js` file initializes `window.SHAKESPEARE_ENGLISH` if needed and assigns one work under its stable ID. Each work has `sections`, and each section has `id`, `label`, optional `act`/`scene`, and `blocks`. Blocks have stable `id`, `text`, `kind`, and optional `speaker`/source anchor. Line breaks inside `text` are significant. Render all strings with textContent, not innerHTML.

The 37 original play IDs are MIT directory names. The additional IDs are `two_noble_kinsmen`, `edwardiii`, `sonnets`, `lovers_complaint`, `rape_of_lucrece`, `venus_and_adonis`, `passionate_pilgrim`, `sundry_notes_of_music`, and `phoenix_and_turtle`.

The Chinese volume’s final mixed-poetry unit can pair at work level with `lovers_complaint`, `passionate_pilgrim`, `sundry_notes_of_music`, and `phoenix_and_turtle`. Their internal numbering is specific to this English source.

## Rebuild and checks

Run from the repository root with Python 3; no third-party modules or network are needed:

```sh
python3 scripts/import_english.py
```

For an initial source acquisition, clone the verified upstream, check out the pinned commit, and run:

```sh
python3 scripts/import_english.py --mit-source /path/to/shakespeare
```

That option verifies the checkout commit and the resulting deterministic archive checksum. The two preserved Gutenberg snapshots are also required. Updating sources is an explicit editorial change, requiring a new revision and checksum review rather than silently pulling current website content.

The importer checks 37 MIT plays, act coverage 1–5, no unparsed non-navigation MIT body text, complete numbered-line extraction, 154 contiguous sonnets, nonempty sections/blocks, unique section IDs, and source checksums. All output JavaScript was evaluated in an isolated Node VM, loading the catalog and every lazy payload. The imported *Hamlet* 1.1 body and all 72 blocks match the repository’s prior English scene exactly.
