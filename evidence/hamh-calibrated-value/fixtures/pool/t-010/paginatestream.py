"""Paged API fetcher (task fixture t-010)."""


def fetch_all(fetch, page_size: int) -> list:
    """Collect all items from a paginated API (offset-based).

    fetch(offset, limit) -> (items, next_offset, has_more)
    """
    all_items = []
    offset = 0
    seen_pages = 0
    while seen_pages < 100:
        items, next_offset, has_more = fetch(offset, page_size)
        for item in items:
            all_items.append(item)
        if not has_more:
            break
        offset = next_offset
        seen_pages += 1
    return all_items
