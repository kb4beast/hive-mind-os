from tag_parser import parse_tags


def check() -> None:
    assert parse_tags("red, blue") == ["red", "blue"]


if __name__ == "__main__":
    check()
