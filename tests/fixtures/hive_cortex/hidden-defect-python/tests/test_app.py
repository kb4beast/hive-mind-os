def test_discount_total_expected_contract() -> None:
    from app import discount_total

    assert discount_total(100, 10) == 90
