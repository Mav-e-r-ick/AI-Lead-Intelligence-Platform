"""The Search Layer.

Public entry points: SearchCoordinator (coordinator.py),
SearchProviderRegistry (provider_registry.py), SearchProfile /
default_profile (config.py). Reuses ProviderHealthTracker
(application/enrichment/provider_health.py) unmodified — health tracking
is already provider-family-agnostic. See README.md in this folder for how
the pieces fit together, and the approved Search Layer RFC for why this
package exists as a sibling to application/enrichment/ rather than folded
into it.

Version 1 scope only: this package implements the framework — provider
interface (application/ports/search_provider_port.py), request/response
shapes (application/dto/search_models.py), registry, priority ordering,
and coordination. It implements no concrete provider itself — that's
infrastructure/search/browser/ (BrowserSearchProvider, the first concrete
provider) and any future one (Bing, Brave, SerpAPI, Tavily, SearchAPI,
Exa), each a new class implementing SearchProviderPort.

Not yet wired into ExecutiveProcessingOrchestrator — see this package's
README.md for why that's a deliberate, separate follow-up, not an
oversight.
"""
