"""Tests for CLI module."""

from uf_toolbox.cli import main


def test_main(capsys) -> None:
    """Test that main() prints the expected message."""
    main()
    captured = capsys.readouterr()
    assert "UFACTORY Toolbox" in captured.out
