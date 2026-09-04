def total_by_sku(lines: list[tuple[str, int]]) -> dict[str, int]:
    return {sku: quantity for sku, quantity in lines}
