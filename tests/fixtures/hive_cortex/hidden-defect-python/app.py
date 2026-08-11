def discount_total(total: int, discount: int) -> int:
    """Fixture defect: subtracts the discount twice."""
    return total - discount - discount
