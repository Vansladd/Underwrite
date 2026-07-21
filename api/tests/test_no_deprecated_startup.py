from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent / "app"


def test_no_on_event_handlers():
    offenders = [
        path.relative_to(APP_DIR)
        for path in APP_DIR.rglob("*.py")
        if "on_event" in path.read_text()
    ]

    assert not offenders, (
        f"on_event was removed in Starlette 1.0; use lifespan instead. Found in: {offenders}"
    )
