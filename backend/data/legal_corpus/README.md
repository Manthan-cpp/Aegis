# Aegis legal corpus

This is an India-scoped, source-grounded legal information corpus. It is not a
court database, a substitute for a lawyer, or legal advice. Every document
records its official source URL so retrieved answers can show a traceable
citation.

The corpus currently covers:

- complete official texts for the current BNS and BNSS;
- the IPC as a clearly marked historical reference only;
- the Protection of Women from Domestic Violence Act, Legal Services
  Authorities Act, POSH Act, POCSO Act and Dowry Prohibition Act;
- official India support routes including ERSS 112, Women Helpline 181 and
  NALSA legal aid.

The `official-*.md` files are generated from the official PDFs in
`backend/data/legal_sources/` by `scripts/fetch_official_legal_corpus.py`.
Update them only by checking the official source, then rerun the ingestion
script after MongoDB is available. Do not add blog posts or uncited summaries.
