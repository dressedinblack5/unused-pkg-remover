import sys
from unittest.mock import patch

import pytest

from unused_pkg_remover.main import main


class TestMain:
    def test_exits_if_no_display(self):
        with patch("unused_pkg_remover.main.os.environ.get", return_value=None):
            with patch("unused_pkg_remover.main.argparse.ArgumentParser.parse_args") as mock_args:
                mock_args.return_value.dry_run = False
                mock_args.return_value.no_deps = False
                with patch("unused_pkg_remover.main.sys.exit", side_effect=SystemExit) as mock_exit:
                    with pytest.raises(SystemExit):
                        main()
                    mock_exit.assert_called_once_with(1)

    def test_launches_gui_with_defaults(self):
        with patch("unused_pkg_remover.main.os.environ.get", return_value=":0"):
            with patch("unused_pkg_remover.main.argparse.ArgumentParser.parse_args") as mock_args:
                mock_args.return_value.dry_run = False
                mock_args.return_value.no_deps = False
                with patch("unused_pkg_remover.gui.run_gui") as mock_gui:
                    main()
                    mock_gui.assert_called_once_with(dry_run=False, force_remove=False)

    def test_passes_dry_run_and_no_deps(self):
        with patch("unused_pkg_remover.main.os.environ.get", return_value=":0"):
            with patch("unused_pkg_remover.main.argparse.ArgumentParser.parse_args") as mock_args:
                mock_args.return_value.dry_run = True
                mock_args.return_value.no_deps = True
                with patch("unused_pkg_remover.gui.run_gui") as mock_gui:
                    main()
                    mock_gui.assert_called_once_with(dry_run=True, force_remove=True)

    def test_parses_dry_run_flag_from_argv(self):
        with patch("unused_pkg_remover.main.os.environ.get", return_value=":0"):
            with patch.object(sys, "argv", ["prog", "--dry-run"]):
                with patch("unused_pkg_remover.gui.run_gui") as mock_gui:
                    main()
                    mock_gui.assert_called_once_with(dry_run=True, force_remove=False)

    def test_parses_no_deps_flag_from_argv(self):
        with patch("unused_pkg_remover.main.os.environ.get", return_value=":0"):
            with patch.object(sys, "argv", ["prog", "--no-deps"]):
                with patch("unused_pkg_remover.gui.run_gui") as mock_gui:
                    main()
                    mock_gui.assert_called_once_with(dry_run=False, force_remove=True)

    def test_handles_gui_import_error(self):
        with patch("unused_pkg_remover.main.os.environ.get", return_value=":0"):
            with patch("unused_pkg_remover.main.argparse.ArgumentParser.parse_args") as mock_args:
                mock_args.return_value.dry_run = False
                mock_args.return_value.no_deps = False
                with (
                    patch("unused_pkg_remover.gui.run_gui", side_effect=ImportError("no qt")),
                    patch("unused_pkg_remover.main.sys.exit") as mock_exit,
                ):
                    main()
                    mock_exit.assert_called_once_with(1)
