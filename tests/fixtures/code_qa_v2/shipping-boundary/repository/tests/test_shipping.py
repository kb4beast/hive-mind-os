from shipping import shipping_tier


def check() -> None:
    assert shipping_tier(5) == "parcel"


if __name__ == "__main__":
    check()
