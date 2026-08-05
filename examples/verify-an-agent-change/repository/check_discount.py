from discounts import checkout_total

assert checkout_total(1_250, nonprofit=True) == 1_000
assert checkout_total(1_250, nonprofit=False) == 1_250
