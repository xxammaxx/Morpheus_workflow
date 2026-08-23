#!/usr/bin/env python3
"""Opt-in provider catalog maintenance command."""

import json

from .catalog import ProviderCatalog


def main():
    catalog = ProviderCatalog()
    result = catalog.refresh()
    catalog.health_refresh()
    print(
        json.dumps(
            {
                "catalog": result,
                "credentials": catalog.credential_inventory(),
                "entries": len(catalog.entries),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
