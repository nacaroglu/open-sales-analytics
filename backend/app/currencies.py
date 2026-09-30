CURRENCIES = ("USD", "EUR", "GBP", "TRY", "CAD", "AUD", "JPY", "CHF", "SEK", "PLN")


def is_valid_currency(value: object) -> bool:
    """True only for an exact, upper-case member of ``CURRENCIES``."""
    return isinstance(value, str) and value in CURRENCIES
