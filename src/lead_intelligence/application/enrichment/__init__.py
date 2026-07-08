"""The Enrichment Provider Framework.

Public entry points: EnrichmentCoordinator (coordinator.py),
ProviderRegistry (provider_registry.py), EnrichmentProfile /
default_profile (config.py), and ProviderHealthTracker
(provider_health.py). See README.md in this folder for how the pieces fit
together.

Version 1 scope only: this package implements the framework — provider
interface, request/response shapes, registry, priority ordering, refresh
policy, health tracking, and coordination. It implements no concrete
provider (no web scraping, no external API calls, no LinkedIn, no AI) —
those are future tasks, each a new class implementing
application/ports/enrichment_provider_port.py.
"""
