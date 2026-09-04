from src.inventory.totals import total_by_sku


def check() -> None:
    assert total_by_sku([("A", 1), ("A", 2)]) == {"A": 3}


if __name__ == "__main__":
    check()
