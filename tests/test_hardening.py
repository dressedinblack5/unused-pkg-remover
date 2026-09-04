import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from unused_pkg_remover.constants import format_size
from unused_pkg_remover.scanner import (
    _extract_cache_pkg_name,
    _parse_human_size,
    _query_expac,
    get_aur_build_deps,
    get_broken_packages,
    get_cache_packages,
    get_obsolete_steam_runtimes,
    get_ollama_models,
    get_orphaned_proton_prefixes,
    get_unused_flatpaks,
)
from unused_pkg_remover.services import (
    RemovalError,
    _sanitize_package_name,
    _sanitize_path_component,
    _validate_path_within_root,
)


class TestValidatePathWithinRoot:
    def test_child_allowed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "yay"
            root.mkdir()
            child = root / "pkg"
            child.mkdir()
            assert _validate_path_within_root(child, root) is True

    def test_sibling_prefix_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "yay"
            root.mkdir()
            evil = Path(tmp) / "yay-evil"
            evil.mkdir()
            assert _validate_path_within_root(evil / "p", root) is False

    def test_dotdot_traversal_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "yay"
            root.mkdir()
            assert _validate_path_within_root(root / ".." / "other", root) is False

    def test_nonexistent_target_inside_allowed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "root"
            root.mkdir()
            assert _validate_path_within_root(root / "new-pkg", root) is True


class TestSanitizePackageName:
    def test_accepts_normal(self):
        assert _sanitize_package_name("mesa") == "mesa"
        assert _sanitize_package_name("llama3.2:1b") == "llama3.2:1b"

    @pytest.mark.parametrize("bad", ["--help", "-Rns", "foo/bar", "../etc", "..", "", "a b"])
    def test_rejects(self, bad):
        with pytest.raises(RemovalError):
            _sanitize_package_name(bad)

    def test_allows_slash_only_when_opted_in(self):
        assert _sanitize_package_name("user/model:tag", allow_slash=True) == "user/model:tag"
        with pytest.raises(RemovalError):
            _sanitize_package_name("user/model:tag")


class TestSanitizePathComponent:
    def test_accepts_spaces_and_normal(self):
        assert _sanitize_path_component("Proton 8.0") == "Proton 8.0"
        assert _sanitize_path_component("wine-7.0") == "wine-7.0"

    @pytest.mark.parametrize("bad", [".", "..", "", "a/b", "a\\b", "a\x00b", " leading"])
    def test_rejects(self, bad):
        with pytest.raises(RemovalError):
            _sanitize_path_component(bad)


class TestExtractCachePkgName:
    def test_simple(self):
        assert _extract_cache_pkg_name("zlib-1.2.13-1-x86_64.pkg.tar.zst") == "zlib"

    def test_dashed_name(self):
        assert _extract_cache_pkg_name("some-pkg-name-2.0-1-x86_64.pkg.tar.zst") == (
            "some-pkg-name"
        )

    def test_pkgver_with_letters(self):
        assert _extract_cache_pkg_name("foo-1.2.r3.gabc-1-x86_64.pkg.tar.zst") == "foo"


class TestParseHumanSize:
    def test_binary_units(self):
        assert _parse_human_size("1.5 GiB") == 1610612736
        assert _parse_human_size("512 MiB") == 536870912
        assert _parse_human_size("10 KiB") == 10240

    def test_legacy_and_single_letter(self):
        assert _parse_human_size("214 MB") == 224395264
        assert _parse_human_size("500 K") == 512000
        assert _parse_human_size("4.1 GB") == int(4.1 * 1024**3)

    def test_invalid_is_zero(self):
        assert _parse_human_size("nonsense") == 0


class TestQueryExpac:
    def test_nonzero_returncode_gives_empty(self):
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        with patch("unused_pkg_remover.scanner.subprocess.run", return_value=mock_result):
            assert _query_expac(["pkg"]) == []

    def test_missing_binary_gives_empty(self):
        with patch("unused_pkg_remover.scanner.subprocess.run", side_effect=FileNotFoundError()):
            assert _query_expac(["pkg"]) == []


class TestAurBuildDeps:
    def test_os_error_gives_empty(self):
        with (
            patch("unused_pkg_remover.scanner._get_orphan_names", return_value=["p"]),
            patch("unused_pkg_remover.scanner.get_aur_packages", return_value={"p"}),
            patch("unused_pkg_remover.scanner._query_expac", side_effect=OSError()),
        ):
            assert get_aur_build_deps() == []


class TestBrokenPackages:
    def test_case_insensitive_and_short_expac(self):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "broken-pkg: 2 MISSING files\nfine-pkg: OK\n"

        mock_expac = MagicMock()
        mock_expac.returncode = 0
        mock_expac.stdout = ""

        with (
            patch("unused_pkg_remover.scanner.shutil.which", return_value="/usr/bin/pacman"),
            patch(
                "unused_pkg_remover.scanner.subprocess.run",
                side_effect=[mock_result, mock_expac],
            ),
        ):
            result = get_broken_packages()
            assert len(result) == 1
            assert result[0]["name"] == "broken-pkg"
            assert result[0]["size"] == 0


class TestCachePackagesDesc:
    def test_mixed_group_not_flagged_not_installed(self):
        p1 = MagicMock()
        p1.name = "zlib-1.2.13-1-x86_64.pkg.tar.zst"
        p1.is_file.return_value = True
        p1.stat().st_size = 100
        p2 = MagicMock()
        p2.name = "zlib-1.3.0-1-x86_64.pkg.tar.zst"
        p2.is_file.return_value = True
        p2.stat().st_size = 200

        mock_pacman = MagicMock()
        mock_pacman.returncode = 0
        mock_pacman.stdout = "zlib 1.3.0\n"

        with (
            patch("unused_pkg_remover.scanner.Path.exists", return_value=True),
            patch("unused_pkg_remover.scanner.Path.iterdir", return_value=[p1, p2]),
            patch("unused_pkg_remover.scanner.subprocess.run", return_value=mock_pacman),
        ):
            result = get_cache_packages()
            assert len(result) == 1
            assert "not installed" not in result[0]["desc"]


class TestFlatpakIds:
    def test_columns_output_parsed_to_ids(self):
        mock_main = MagicMock()
        mock_main.returncode = 0
        mock_main.stdout = "org.foo.Bar\norg.baz.Qux\n"
        with (
            patch("unused_pkg_remover.scanner.shutil.which", return_value="/usr/bin/flatpak"),
            patch("unused_pkg_remover.scanner.subprocess.run", return_value=mock_main),
        ):
            result = get_unused_flatpaks()
            assert {p["name"] for p in result} == {"org.foo.Bar", "org.baz.Qux"}


class TestProtonPrefixes:
    def test_malformed_appid_line_does_not_hide_real_id(self):
        d1 = MagicMock()
        d1.name = "12345"
        d1.is_dir.return_value = True
        d1.rglob.return_value = []

        mf = MagicMock()
        mf.read_text.return_value = '"appid" "oops"\n"appid"\t\t"12345"\n'

        with (
            patch("unused_pkg_remover.scanner.Path.home", return_value=Path("/home/user")),
            patch("unused_pkg_remover.scanner.Path.exists", return_value=True),
            patch("unused_pkg_remover.scanner.Path.glob", return_value=[mf]),
            patch("unused_pkg_remover.scanner.Path.iterdir", return_value=[d1]),
        ):
            assert get_orphaned_proton_prefixes() == []


class TestSteamRuntimes:
    def _dir(self, name):
        d = MagicMock()
        d.name = name
        d.is_dir.return_value = True
        d.rglob.return_value = []
        return d

    def test_allowlist_keeps_runtimes_rejects_games(self):
        dirs = [self._dir("SteamLinuxRuntime"), self._dir("Proton 8.0"), self._dir("SDK Adventure")]
        with (
            patch("unused_pkg_remover.scanner.Path.home", return_value=Path("/home/user")),
            patch("unused_pkg_remover.scanner.Path.exists", return_value=True),
            patch("unused_pkg_remover.scanner.Path.glob", return_value=[]),
            patch("unused_pkg_remover.scanner.Path.iterdir", return_value=dirs),
            patch("unused_pkg_remover.scanner.sorted", side_effect=lambda x: x),
        ):
            result = get_obsolete_steam_runtimes()
            names = {p["name"] for p in result}
            assert "SteamLinuxRuntime" in names
            assert "Proton 8.0" in names
            assert "SDK Adventure" not in names


class TestOllamaModels:
    def test_gib_size_parsed(self):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = (
            "NAME    ID      SIZE    MODIFIED\nbig     abc     4.1 GiB 2 days ago\n"
        )
        with (
            patch("unused_pkg_remover.scanner.shutil.which", return_value="/usr/bin/ollama"),
            patch("unused_pkg_remover.scanner.subprocess.run", return_value=mock_result),
        ):
            result = get_ollama_models()
            assert len(result) == 1
            assert result[0]["size"] == int(4.1 * 1024**3)


class TestFormatSizeGuards:
    def test_none_and_negative(self):
        assert format_size(None) == "0.0 B"
        assert format_size(-5) == "0.0 B"


class TestIgnoreFile:
    def test_points_at_home(self):
        from unused_pkg_remover.gui.constants import get_ignore_file

        assert get_ignore_file() == Path.home() / ".unused-ignore"


class TestHeadlessDryRun:
    def test_lists_packages_without_display(self, capsys):
        import importlib
        import sys

        main_mod = importlib.import_module("unused_pkg_remover.main")

        with (
            patch.object(main_mod.os.environ, "get", return_value=None),
            patch.object(sys, "argv", ["prog", "--dry-run"]),
            patch(
                "unused_pkg_remover.scanner.get_unused_packages",
                return_value=([{"name": "p", "size": 1024}], 0),
            ),
        ):
            main_mod.main()
            out = capsys.readouterr().out
            assert "p" in out
