from pathlib import Path
from unittest.mock import MagicMock, mock_open, patch

import pytest

from unused_pkg_remover.scanner import (
    SAFE_PACKAGES,
    _get_orphan_names,
    get_all_cache_packages,
    get_aur_build_deps,
    get_aur_cache_packages,
    get_aur_packages,
    get_broken_packages,
    get_cache_packages,
    get_dependents,
    get_explicitly_installed_packages,
    get_ignored_packages,
    get_obsolete_steam_runtimes,
    get_orphaned_proton_prefixes,
    get_stale_launcher_runners,
    get_unused_flatpaks,
    get_unused_packages,
)


class TestGetIgnoredPackages:
    def test_no_ignore_files_exist(self):
        with patch("unused_pkg_remover.scanner.Path.home") as mock_home:
            with patch("unused_pkg_remover.scanner.Path.cwd") as mock_cwd:
                mock_home.return_value = Path("/home/user")
                mock_cwd.return_value = Path("/some/proj")
                with patch.object(Path, "exists", return_value=False):
                    result = get_ignored_packages()
                    assert result == set()

    def test_reads_ignore_files_and_skips_comments_and_blanks(self):
        content = "package1\npackage2\n# comment\n  \npackage3\n"
        with patch("unused_pkg_remover.scanner.Path.home") as mock_home:
            with patch("unused_pkg_remover.scanner.Path.cwd") as mock_cwd:
                mock_home.return_value = Path("/home/user")
                mock_cwd.return_value = Path("/some/proj")
                with patch.object(Path, "exists", return_value=True):
                    with patch("builtins.open", mock_open(read_data=content)):
                        result = get_ignored_packages()
                        assert result == {"package1", "package2", "package3"}

    def test_lowercases_packages(self):
        content = "PackageName\nOtherPkg\n"
        with patch("unused_pkg_remover.scanner.Path.home") as mock_home:
            with patch("unused_pkg_remover.scanner.Path.cwd") as mock_cwd:
                mock_home.return_value = Path("/home/user")
                mock_cwd.return_value = Path("/some/proj")
                with patch.object(Path, "exists", return_value=True):
                    with patch("builtins.open", mock_open(read_data=content)):
                        result = get_ignored_packages()
                        assert result == {"packagename", "otherpkg"}

    def test_checks_all_three_paths(self):
        with patch("unused_pkg_remover.scanner.Path.home") as mock_home:
            with patch("unused_pkg_remover.scanner.Path.cwd") as mock_cwd:
                mock_home.return_value = Path("/home/user")
                mock_cwd.return_value = Path("/some/proj")
                with patch.object(Path, "exists", return_value=True) as mock_exists:
                    with patch("builtins.open", mock_open(read_data="pkg\n")):
                        get_ignored_packages()
                        assert mock_exists.call_count == 3


class TestGetAurPackages:
    def test_returns_packages(self):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "aur-pkg1\naur-pkg2\n"
        with patch("unused_pkg_remover.scanner.subprocess.run", return_value=mock_result):
            result = get_aur_packages()
            assert result == {"aur-pkg1", "aur-pkg2"}

    def test_returns_empty_on_failure(self):
        mock_result = MagicMock()
        mock_result.returncode = 1
        with patch("unused_pkg_remover.scanner.subprocess.run", return_value=mock_result):
            result = get_aur_packages()
            assert result == set()

    def test_lowercases_packages(self):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "Aur-Pkg\n"
        with patch("unused_pkg_remover.scanner.subprocess.run", return_value=mock_result):
            result = get_aur_packages()
            assert result == {"aur-pkg"}


class TestGetExplicitlyInstalledPackages:
    def test_returns_packages(self):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "pkg1\npkg2\n"
        with patch("unused_pkg_remover.scanner.subprocess.run", return_value=mock_result):
            result = get_explicitly_installed_packages()
            assert result == {"pkg1", "pkg2"}

    def test_returns_empty_on_failure(self):
        mock_result = MagicMock()
        mock_result.returncode = 1
        with patch("unused_pkg_remover.scanner.subprocess.run", return_value=mock_result):
            result = get_explicitly_installed_packages()
            assert result == set()


class TestSafePackages:
    def test_is_non_empty_set(self):
        assert isinstance(SAFE_PACKAGES, set)
        assert len(SAFE_PACKAGES) > 0

    def test_contains_critical_packages(self):
        for pkg in ["glibc", "systemd", "linux", "pacman", "bash"]:
            assert pkg in SAFE_PACKAGES


class TestGetOrphanNames:
    def test_uses_yay_when_available(self):
        mock_yay = MagicMock()
        mock_yay.returncode = 0
        mock_yay.stdout = "orphan1\norphan2\n"
        with patch("unused_pkg_remover.scanner.shutil.which") as mock_which:
            mock_which.side_effect = ["/usr/bin/yay", None, None]
            with patch("unused_pkg_remover.scanner.subprocess.run", return_value=mock_yay):
                result = _get_orphan_names()
                assert result == ["orphan1", "orphan2"]

    def test_falls_back_to_paru_when_yay_fails(self):
        mock_yay = MagicMock()
        mock_yay.returncode = 1
        mock_yay.stdout = ""
        mock_paru = MagicMock()
        mock_paru.returncode = 0
        mock_paru.stdout = "paru-orphan\n"
        with patch("unused_pkg_remover.scanner.shutil.which") as mock_which:
            mock_which.side_effect = ["/usr/bin/yay", "/usr/bin/paru", None]
            with patch(
                "unused_pkg_remover.scanner.subprocess.run",
                side_effect=[mock_yay, mock_paru],
            ):
                result = _get_orphan_names()
                assert result == ["paru-orphan"]

    def test_falls_back_to_pacman_when_aur_helpers_fail(self):
        mock_yay = MagicMock()
        mock_yay.returncode = 1
        mock_paru = MagicMock()
        mock_paru.returncode = 1
        mock_pacman = MagicMock()
        mock_pacman.returncode = 0
        mock_pacman.stdout = "pacman-orphan\n"
        with patch("unused_pkg_remover.scanner.shutil.which") as mock_which:
            mock_which.side_effect = ["/usr/bin/yay", "/usr/bin/paru", "/usr/bin/pacman"]
            with patch(
                "unused_pkg_remover.scanner.subprocess.run",
                side_effect=[mock_yay, mock_paru, mock_pacman],
            ):
                result = _get_orphan_names()
                assert result == ["pacman-orphan"]

    def test_returns_empty_when_all_fail(self):
        mock_result = MagicMock()
        mock_result.returncode = 1
        with patch("unused_pkg_remover.scanner.shutil.which", return_value="/usr/bin/something"):
            with patch("unused_pkg_remover.scanner.subprocess.run", return_value=mock_result):
                result = _get_orphan_names()
                assert result == []

    def test_skips_unavailable_helpers(self):
        mock_pacman = MagicMock()
        mock_pacman.returncode = 0
        mock_pacman.stdout = "orphan\n"
        with patch("unused_pkg_remover.scanner.shutil.which") as mock_which:
            mock_which.side_effect = [None, None, "/usr/bin/pacman"]
            with patch("unused_pkg_remover.scanner.subprocess.run", return_value=mock_pacman):
                result = _get_orphan_names()
                assert result == ["orphan"]


class TestGetDependents:
    def test_uses_pactree_success(self):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "dependent-pkg\n"
        with patch("unused_pkg_remover.scanner.shutil.which", return_value="/usr/bin/pactree"):
            with patch("unused_pkg_remover.scanner.subprocess.run", return_value=mock_result):
                result = get_dependents("test-pkg")
                assert result == ["dependent-pkg"]

    def test_falls_back_pactree_unflagged(self):
        mock_fail = MagicMock()
        mock_fail.returncode = 1
        mock_success = MagicMock()
        mock_success.returncode = 0
        mock_success.stdout = "dep\n"
        with patch("unused_pkg_remover.scanner.shutil.which", return_value="/usr/bin/pactree"):
            with patch(
                "unused_pkg_remover.scanner.subprocess.run", side_effect=[mock_fail, mock_success]
            ):
                result = get_dependents("test-pkg")
                assert result == ["dep"]

    def test_strips_tree_chars(self):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "├─dep1\n└─dep2\n"
        with patch("unused_pkg_remover.scanner.shutil.which", return_value="/usr/bin/pactree"):
            with patch("unused_pkg_remover.scanner.subprocess.run", return_value=mock_result):
                result = get_dependents("test-pkg")
                assert result == ["dep1", "dep2"]

    def test_excludes_self_name(self):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "test-pkg\ndep\n"
        with patch("unused_pkg_remover.scanner.shutil.which", return_value="/usr/bin/pactree"):
            with patch("unused_pkg_remover.scanner.subprocess.run", return_value=mock_result):
                result = get_dependents("test-pkg")
                assert result == ["dep"]

    def _mock_pacman_qi(self, stdout, returncode=0):
        mock_run = MagicMock()
        mock_run.returncode = returncode
        mock_run.stdout = stdout
        return mock_run

    def test_uses_pacman_qi_fallback(self):
        mock_result = self._mock_pacman_qi(
            "Name           : test-pkg\n"
            "Required By    : dep1  dep2\n"
            "Optional For   : opt-dep\n"
            "Optional Deps  : something\n"
        )
        sr = "unused_pkg_remover.scanner.subprocess.run"
        with patch("unused_pkg_remover.scanner.shutil.which", return_value=None):
            with patch(sr, return_value=mock_result) as mock_run:
                result = get_dependents("test-pkg")
                assert result == ["dep1  dep2", "opt-dep"]
                _, kwargs = mock_run.call_args
                assert kwargs.get("env", {}).get("LANG") == "C"

    def test_pacman_qi_skips_none(self):
        mock_result = self._mock_pacman_qi("Required By    : None\n")
        sr = "unused_pkg_remover.scanner.subprocess.run"
        with patch("unused_pkg_remover.scanner.shutil.which", return_value=None):
            with patch(sr, return_value=mock_result) as mock_run:
                result = get_dependents("test-pkg")
                assert result == []
                _, kwargs = mock_run.call_args
                assert kwargs.get("env", {}).get("LANG") == "C"

    def test_returns_empty_on_pacman_qi_failure(self):
        mock_result = self._mock_pacman_qi("", returncode=1)
        sr = "unused_pkg_remover.scanner.subprocess.run"
        with patch("unused_pkg_remover.scanner.shutil.which", return_value=None):
            with patch(sr, return_value=mock_result) as mock_run:
                result = get_dependents("test-pkg")
                assert result == []
                _, kwargs = mock_run.call_args
                assert kwargs.get("env", {}).get("LANG") == "C"


class TestGetUnusedPackages:
    def test_raises_if_expac_missing(self):
        with patch("unused_pkg_remover.scanner.shutil.which", return_value=None):
            with pytest.raises(RuntimeError, match="expac not found"):
                get_unused_packages()

    def test_returns_empty_when_no_orphans(self):
        mock_pacman = MagicMock()
        mock_pacman.returncode = 0
        mock_pacman.stdout = ""
        with patch("unused_pkg_remover.scanner.shutil.which", return_value="/usr/bin/expac"):
            with patch("unused_pkg_remover.scanner.subprocess.run", return_value=mock_pacman):
                result, filtered = get_unused_packages()
                assert result == []
                assert filtered == 0

    def test_filters_safe_and_ignored_packages(self):
        mock_pacman = MagicMock()
        mock_pacman.returncode = 0
        mock_pacman.stdout = "glibc\nsome-orphan\n"

        mock_expac = MagicMock()
        mock_expac.returncode = 0
        mock_expac.stdout = (
            "glibc|2024-01-01|GNU C Library|50000000\nsome-orphan|2024-01-02|Some orphan|1000000\n"
        )

        with patch("unused_pkg_remover.scanner.shutil.which", return_value="/usr/bin/expac"):
            with patch(
                "unused_pkg_remover.scanner.subprocess.run", side_effect=[mock_pacman, mock_expac]
            ):
                with patch("unused_pkg_remover.scanner.get_ignored_packages", return_value=set()):
                    with patch("unused_pkg_remover.scanner.get_aur_packages", return_value=set()):
                        with patch(
                            "unused_pkg_remover.scanner.get_explicitly_installed_packages",
                            return_value=set(),
                        ):
                            result, filtered = get_unused_packages()
                            assert len(result) == 1
                            assert result[0]["name"] == "some-orphan"
                            assert filtered == 1

    def test_full_pipeline_with_aur_and_sorting(self):
        mock_pacman = MagicMock()
        mock_pacman.returncode = 0
        mock_pacman.stdout = "small-pkg\nbig-pkg\n"

        mock_expac = MagicMock()
        mock_expac.returncode = 0
        mock_expac.stdout = (
            "small-pkg|2024-01-01|Small package|1000000\nbig-pkg|2024-01-02|Big package|50000000\n"
        )

        with patch("unused_pkg_remover.scanner.shutil.which", return_value="/usr/bin/expac"):
            with patch(
                "unused_pkg_remover.scanner.subprocess.run", side_effect=[mock_pacman, mock_expac]
            ):
                with patch("unused_pkg_remover.scanner.get_ignored_packages", return_value=set()):
                    with patch(
                        "unused_pkg_remover.scanner.get_aur_packages", return_value={"big-pkg"}
                    ):
                        with patch(
                            "unused_pkg_remover.scanner.get_explicitly_installed_packages",
                            return_value=set(),
                        ):
                            result, filtered = get_unused_packages()
                            assert len(result) == 2
                            assert result[0]["name"] == "big-pkg"
                            assert result[0]["is_aur"] is True
                            assert result[0]["size"] == 50000000
                            assert result[1]["name"] == "small-pkg"
                            assert result[1]["is_aur"] is False
                            assert result[1]["size"] == 1000000

    def test_malformed_expac_line_skipped(self):
        mock_pacman = MagicMock()
        mock_pacman.returncode = 0
        mock_pacman.stdout = "orphan1\n"

        mock_expac = MagicMock()
        mock_expac.returncode = 0
        mock_expac.stdout = "orphan1|2024-01-01|Only three parts\n"

        with patch("unused_pkg_remover.scanner.shutil.which", return_value="/usr/bin/expac"):
            with patch(
                "unused_pkg_remover.scanner.subprocess.run", side_effect=[mock_pacman, mock_expac]
            ):
                with patch("unused_pkg_remover.scanner.get_ignored_packages", return_value=set()):
                    with patch("unused_pkg_remover.scanner.get_aur_packages", return_value=set()):
                        with patch(
                            "unused_pkg_remover.scanner.get_explicitly_installed_packages",
                            return_value=set(),
                        ):
                            result, filtered = get_unused_packages()
                            assert result == []

    def test_handles_bad_size_string(self):
        mock_pacman = MagicMock()
        mock_pacman.returncode = 0
        mock_pacman.stdout = "orphan1\n"

        mock_expac = MagicMock()
        mock_expac.returncode = 0
        mock_expac.stdout = "orphan1|2024-01-01|Desc|not_a_number\n"

        with patch("unused_pkg_remover.scanner.shutil.which", return_value="/usr/bin/expac"):
            with patch(
                "unused_pkg_remover.scanner.subprocess.run", side_effect=[mock_pacman, mock_expac]
            ):
                with patch("unused_pkg_remover.scanner.get_ignored_packages", return_value=set()):
                    with patch("unused_pkg_remover.scanner.get_aur_packages", return_value=set()):
                        with patch(
                            "unused_pkg_remover.scanner.get_explicitly_installed_packages",
                            return_value=set(),
                        ):
                            result, filtered = get_unused_packages()
                            assert len(result) == 1
                            assert result[0]["size"] == 0

    def test_pacman_returns_nonzero(self):
        mock_result = MagicMock()
        mock_result.returncode = 1
        with patch("unused_pkg_remover.scanner.shutil.which", return_value="/usr/bin/expac"):
            with patch("unused_pkg_remover.scanner.subprocess.run", return_value=mock_result):
                result, filtered = get_unused_packages()
                assert result == []
                assert filtered == 0


class TestGetCachePackages:
    def test_returns_empty_if_cache_dir_missing(self):
        with patch("unused_pkg_remover.scanner.Path.exists", return_value=False):
            assert get_cache_packages() == []

    def test_returns_cached_packages_not_installed(self):
        p1 = MagicMock()
        p1.name = "zlib-1.2.13-1-x86_64.pkg.tar.zst"
        p1.is_file.return_value = True
        p1.stat().st_size = 100000
        p2 = MagicMock()
        p2.name = "zlib-1.3.0-1-x86_64.pkg.tar.zst"
        p2.is_file.return_value = True
        p2.stat().st_size = 200000

        mock_pacman = MagicMock()
        mock_pacman.returncode = 0
        mock_pacman.stdout = "some-installed-pkg 1.0\n"

        with (
            patch("unused_pkg_remover.scanner.Path.exists", return_value=True),
            patch("unused_pkg_remover.scanner.Path.iterdir", return_value=[p1, p2]),
            patch("unused_pkg_remover.scanner.subprocess.run", return_value=mock_pacman),
        ):
            result = get_cache_packages()
            assert len(result) == 1
            assert result[0]["name"] == "zlib"
            assert result[0]["size"] == 300000
            assert result[0]["type_tag"] == "cache"

    def test_filters_installed_packages(self):
        p = MagicMock()
        p.name = "zstd-1.5.5-1-x86_64.pkg.tar.zst"
        p.is_file.return_value = True
        p.stat().st_size = 500000

        mock_pacman = MagicMock()
        mock_pacman.returncode = 0
        mock_pacman.stdout = "zstd 1.5.5\n"

        with (
            patch("unused_pkg_remover.scanner.Path.exists", return_value=True),
            patch("unused_pkg_remover.scanner.Path.iterdir", return_value=[p]),
            patch("unused_pkg_remover.scanner.subprocess.run", return_value=mock_pacman),
        ):
            result = get_cache_packages()
            assert result == []


class TestGetUnusedFlatpaks:
    def test_returns_empty_if_flatpak_not_installed(self):
        with patch("unused_pkg_remover.scanner.shutil.which", return_value=None):
            assert get_unused_flatpaks() == []

    def test_returns_empty_on_nonzero_exit(self):
        mock_result = MagicMock()
        mock_result.returncode = 1
        with (
            patch("unused_pkg_remover.scanner.shutil.which", return_value="/usr/bin/flatpak"),
            patch("unused_pkg_remover.scanner.subprocess.run", return_value=mock_result),
        ):
            assert get_unused_flatpaks() == []


class TestGetBrokenPackages:
    def test_returns_empty_if_pacman_not_installed(self):
        with patch("unused_pkg_remover.scanner.shutil.which", return_value=None):
            assert get_broken_packages() == []

    def test_returns_packages_with_missing_files(self):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "broken-pkg: 2 missing files\nfine-pkg: OK\n"

        mock_expac = MagicMock()
        mock_expac.returncode = 0
        mock_expac.stdout = "5000000"

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
            assert result[0]["size"] == 5000000
            assert result[0]["type_tag"] == "broken"

    def test_returns_empty_when_no_broken_packages(self):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "fine-pkg: OK\nall-good: OK\n"

        with (
            patch("unused_pkg_remover.scanner.shutil.which", return_value="/usr/bin/pacman"),
            patch("unused_pkg_remover.scanner.subprocess.run", return_value=mock_result),
        ):
            assert get_broken_packages() == []


class TestGetAurBuildDeps:
    def test_returns_empty_no_orphans(self):
        with (
            patch("unused_pkg_remover.scanner._get_orphan_names", return_value=[]),
            patch("unused_pkg_remover.scanner.get_aur_packages", return_value={"pkg1"}),
        ):
            assert get_aur_build_deps() == []

    def test_returns_empty_no_aur_packages(self):
        with (
            patch("unused_pkg_remover.scanner._get_orphan_names", return_value=["orphan1"]),
            patch("unused_pkg_remover.scanner.get_aur_packages", return_value=set()),
            patch("unused_pkg_remover.scanner.subprocess.run") as mock_run,
        ):
            result = get_aur_build_deps()
            assert result == []
            mock_run.assert_not_called()

    def test_filters_orphans_to_aur_only(self):
        mock_expac = MagicMock()
        mock_expac.returncode = 0
        mock_expac.stdout = "aur-orphan||desc1|50000\nrepo-orphan||desc2|20000\n"

        with (
            patch(
                "unused_pkg_remover.scanner._get_orphan_names",
                return_value=["aur-orphan", "repo-orphan"],
            ),
            patch(
                "unused_pkg_remover.scanner.get_aur_packages",
                return_value={"aur-orphan"},
            ),
            patch("unused_pkg_remover.scanner.subprocess.run", return_value=mock_expac),
        ):
            result = get_aur_build_deps()
            assert len(result) == 1
            assert result[0]["name"] == "aur-orphan"
            assert result[0]["size"] == 50000
            assert result[0]["type_tag"] == "aur-dep"

    def test_handles_malformed_expac_line(self):
        mock_expac = MagicMock()
        mock_expac.returncode = 0
        mock_expac.stdout = "bad|line\n"

        with (
            patch(
                "unused_pkg_remover.scanner._get_orphan_names",
                return_value=["pkg1"],
            ),
            patch(
                "unused_pkg_remover.scanner.get_aur_packages",
                return_value={"pkg1"},
            ),
            patch("unused_pkg_remover.scanner.subprocess.run", return_value=mock_expac),
        ):
            result = get_aur_build_deps()
            assert result == []

    def test_sorts_by_size_descending(self):
        mock_expac = MagicMock()
        mock_expac.returncode = 0
        mock_expac.stdout = "small||desc1|10\nbig||desc2|1000\nmedium||desc3|100\n"

        with (
            patch(
                "unused_pkg_remover.scanner._get_orphan_names",
                return_value=["small", "big", "medium"],
            ),
            patch(
                "unused_pkg_remover.scanner.get_aur_packages",
                return_value={"small", "big", "medium"},
            ),
            patch("unused_pkg_remover.scanner.subprocess.run", return_value=mock_expac),
        ):
            result = get_aur_build_deps()
            assert [p["name"] for p in result] == ["big", "medium", "small"]


class TestGetAllCachePackages:
    def test_returns_empty_if_dir_missing(self):
        with patch("unused_pkg_remover.scanner.Path.exists", return_value=False):
            assert get_all_cache_packages() == []

    def test_lists_all_cache_files(self):
        mock_f1 = MagicMock()
        mock_f1.name = "pkg-a-1.0-1-x86_64.pkg.tar.zst"
        mock_f1.is_file.return_value = True
        mock_f1.stat.return_value.st_size = 5000
        mock_f2 = MagicMock()
        mock_f2.name = "pkg-b-2.0-1-any.pkg.tar.zst"
        mock_f2.is_file.return_value = True
        mock_f2.stat.return_value.st_size = 3000
        mock_f3 = MagicMock()
        mock_f3.name = "not-a-pkg.sig"
        mock_f3.is_file.return_value = True
        mock_f3.stat.return_value.st_size = 100

        with (
            patch("unused_pkg_remover.scanner.Path.exists", return_value=True),
            patch(
                "unused_pkg_remover.scanner.Path.iterdir",
                return_value=[mock_f1, mock_f2, mock_f3],
            ),
            patch("unused_pkg_remover.scanner.subprocess.run") as mock_run,
        ):
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = "pkg-a 1.0\n"
            result = get_all_cache_packages()
            assert len(result) == 2
            names = [p["name"] for p in result]
            assert "pkg-a-1.0-1-x86_64" in names
            assert "pkg-b-2.0-1-any" in names


class TestGetAurCachePackages:
    def test_returns_empty_if_no_cache_dirs(self):
        with patch("unused_pkg_remover.scanner.Path.exists", return_value=False):
            assert get_aur_cache_packages() == []

    def test_lists_aur_build_dirs(self):
        mock_d1 = MagicMock()
        mock_d1.name = "aur-pkg-1"
        mock_d1.is_dir.return_value = True
        mock_d1.rglob.return_value = []
        mock_d2 = MagicMock()
        mock_d2.name = "aur-pkg-2"
        mock_d2.is_dir.return_value = True
        mock_d2.rglob.return_value = [MagicMock()]
        mock_d2.rglob.return_value[0].is_file.return_value = True
        mock_d2.rglob.return_value[0].stat.return_value.st_size = 1000

        call_n = [0]

        def mock_exists():
            call_n[0] += 1
            return call_n[0] == 1  # only yay exists

        with (
            patch(
                "unused_pkg_remover.scanner.Path.home",
                return_value=Path("/home/user"),
            ),
            patch("unused_pkg_remover.scanner.Path.exists", side_effect=mock_exists),
            patch(
                "unused_pkg_remover.scanner.Path.iterdir",
                return_value=[mock_d1, mock_d2],
            ),
            patch("unused_pkg_remover.scanner.sorted", side_effect=lambda x: x),
        ):
            result = get_aur_cache_packages()
            assert len(result) == 2
            assert result[0]["name"] == "aur-pkg-2"  # larger first


class TestGetOrphanedProtonPrefixes:
    def test_returns_empty_if_compatdata_missing(self):
        with patch("unused_pkg_remover.scanner.Path.home", return_value=Path("/no/steam")):
            with patch("unused_pkg_remover.scanner.Path.exists", return_value=False):
                assert get_orphaned_proton_prefixes() == []

    def test_lists_uninstalled_prefixes(self):
        d1 = MagicMock()
        d1.name = "12345"
        d1.is_dir.return_value = True
        d1.rglob.return_value = []

        d2 = MagicMock()
        d2.name = "99999"
        d2.is_dir.return_value = True
        d2.rglob.return_value = []

        with (
            patch("unused_pkg_remover.scanner.Path.home", return_value=Path("/home/user")),
            patch("unused_pkg_remover.scanner.Path.exists", return_value=True),
            patch("unused_pkg_remover.scanner.Path.glob", return_value=[]),
            patch("unused_pkg_remover.scanner.Path.iterdir", return_value=[d1, d2]),
        ):
            result = get_orphaned_proton_prefixes()
            assert len(result) == 2
            appids = {p["name"] for p in result}
            assert appids == {"12345", "99999"}

    def test_excludes_installed_appids(self):
        d1 = MagicMock()
        d1.name = "12345"
        d1.is_dir.return_value = True
        d1.rglob.return_value = []

        mf = MagicMock()
        mf.read_text.return_value = '"appid"\t\t"12345"\n'

        with (
            patch("unused_pkg_remover.scanner.Path.home", return_value=Path("/home/user")),
            patch("unused_pkg_remover.scanner.Path.exists", return_value=True),
            patch("unused_pkg_remover.scanner.Path.glob", return_value=[mf]),
            patch("unused_pkg_remover.scanner.Path.iterdir", return_value=[d1]),
        ):
            result = get_orphaned_proton_prefixes()
            assert len(result) == 0


class TestGetObsoleteSteamRuntimes:
    def test_returns_empty_if_common_missing(self):
        with patch("unused_pkg_remover.scanner.Path.home", return_value=Path("/no/steam")):
            with patch("unused_pkg_remover.scanner.Path.exists", return_value=False):
                assert get_obsolete_steam_runtimes() == []

    def test_lists_uninstalled_runtimes(self):
        d1 = MagicMock()
        d1.name = "SteamLinuxRuntime"
        d1.is_dir.return_value = True
        d1.rglob.return_value = []

        d2 = MagicMock()
        d2.name = "Proton 8.0"
        d2.is_dir.return_value = True
        d2.rglob.return_value = []

        with (
            patch("unused_pkg_remover.scanner.Path.home", return_value=Path("/home/user")),
            patch("unused_pkg_remover.scanner.Path.exists", return_value=True),
            patch("unused_pkg_remover.scanner.Path.glob", return_value=[]),
            patch("unused_pkg_remover.scanner.Path.iterdir", return_value=[d1, d2]),
            patch("unused_pkg_remover.scanner.sorted", side_effect=lambda x: x),
        ):
            result = get_obsolete_steam_runtimes()
            assert len(result) == 2

    def test_skips_runtimes_matching_installed_game(self):
        d1 = MagicMock()
        d1.name = "SteamLinuxRuntime"
        d1.is_dir.return_value = True
        d1.rglob.return_value = []

        mf = MagicMock()
        mf.read_text.return_value = '"installdir"\t\t"SteamLinuxRuntime"\n'

        with (
            patch("unused_pkg_remover.scanner.Path.home", return_value=Path("/home/user")),
            patch("unused_pkg_remover.scanner.Path.exists", return_value=True),
            patch("unused_pkg_remover.scanner.Path.glob", return_value=[mf]),
            patch("unused_pkg_remover.scanner.Path.iterdir", return_value=[d1]),
            patch("unused_pkg_remover.scanner.sorted", side_effect=lambda x: x),
        ):
            result = get_obsolete_steam_runtimes()
            assert len(result) == 0


class TestGetStaleLauncherRunners:
    def test_returns_empty_if_no_runner_dirs(self):
        with patch("unused_pkg_remover.scanner.Path.home", return_value=Path("/home/user")):
            with patch("unused_pkg_remover.scanner.Path.exists", return_value=False):
                assert get_stale_launcher_runners() == []

    def test_lists_lutris_runners(self):
        d1 = MagicMock()
        d1.name = "wine-7.0"
        d1.is_dir.return_value = True
        d1.rglob.return_value = []

        with (
            patch("unused_pkg_remover.scanner.Path.home", return_value=Path("/home/user")),
            patch("unused_pkg_remover.scanner.Path.exists", return_value=True),
            patch(
                "unused_pkg_remover.scanner.Path.iterdir",
                return_value=[d1],
            ),
        ):
            result = get_stale_launcher_runners()
            assert any("lutris:wine-7.0" in p["name"] for p in result)

    def test_lists_heroic_runners(self):
        d1 = MagicMock()
        d1.name = "GE-Proton8-1"
        d1.is_dir.return_value = True
        d1.rglob.return_value = []

        with (
            patch("unused_pkg_remover.scanner.Path.home", return_value=Path("/home/user")),
            patch("unused_pkg_remover.scanner.Path.exists", return_value=True),
            patch(
                "unused_pkg_remover.scanner.Path.iterdir",
                return_value=[d1],
            ),
        ):
            result = get_stale_launcher_runners()
            assert any("heroic:proton/GE-Proton8-1" in p["name"] for p in result)

    def test_lists_bottles_runners(self):
        d1 = MagicMock()
        d1.name = "wine-8.0"
        d1.is_dir.return_value = True
        d1.rglob.return_value = []

        with (
            patch("unused_pkg_remover.scanner.Path.home", return_value=Path("/home/user")),
            patch("unused_pkg_remover.scanner.Path.exists", return_value=True),
            patch(
                "unused_pkg_remover.scanner.Path.iterdir",
                return_value=[d1],
            ),
        ):
            result = get_stale_launcher_runners()
            assert any("bottles:wine-8.0" in p["name"] for p in result)
