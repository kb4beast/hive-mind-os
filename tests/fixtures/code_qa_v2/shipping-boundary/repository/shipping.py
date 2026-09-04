def shipping_tier(weight: int) -> str:
    return "parcel" if weight < 5 else "freight"
