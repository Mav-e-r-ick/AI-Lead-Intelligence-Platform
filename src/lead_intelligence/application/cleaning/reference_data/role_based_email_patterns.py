"""Role-based email local-part prefixes for CLN-020."""

DEFAULT_ROLE_BASED_PREFIXES: frozenset[str] = frozenset(
    {
        "info",
        "sales",
        "support",
        "noreply",
        "no-reply",
        "admin",
        "contact",
        "hello",
        "help",
        "office",
        "team",
        "marketing",
        "hr",
        "careers",
        "billing",
    }
)

#: Domains excluded from CLN-066's company-domain mismatch check, since a
#: mismatch there is expected, not a signal.
DEFAULT_GENERIC_EMAIL_DOMAINS: frozenset[str] = frozenset(
    {"gmail.com", "yahoo.com", "outlook.com", "hotmail.com", "icloud.com", "aol.com"}
)
