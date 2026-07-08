"""Concrete EnrichmentProviderPort implementations.

Each sub-folder is one provider (e.g. `company_website/`), the same
one-adapter-per-source-technology convention `infrastructure/importers/`
uses for SourceReaderPort. The Enrichment Provider Framework itself
(`application/enrichment/`) never imports anything from here — providers
are wired in by whatever future orchestration layer constructs a
ProviderRegistry, keeping the framework unaware of which concrete
providers exist.
"""
