import subprocess
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, mock_open, patch

import pytest

from unused_pkg_remover.services import (
    RemovalError,
    add_to_ignore,
    log_removal,
    remove_all_cache_packages,
    remove_aur_cache_packages,
    remove_aur_deps,
    remove_cache_packages,
    remove_flatpak_packages,
    remove_obsolete_steam_runtimes,
    remove_orphaned_proton_prefixes,
    remove_packages_batch,
    remove_stale_launcher_runners,
)


class TestRemovePackagesBatch:
    def _mock_proc(self, returncode=0, stdout="", stderr=""):
        proc = MagicMock()
        proc.returncode = returncode
        proc.communicate.return_value = (stdout, stderr)
        return patch("unused_pkg_remover.services.subprocess.Popen", return_value=proc)

    def test_runs_subprocess_without_force(self):
        with self._mock_proc() as mock_popen:
            remove_packages_batch(["pkg1", "pkg2"])
            args, kwargs = mock_popen.call_args
            assert args[0] == ["pkexec", "pacman", "-Rns", "--noconfirm", "pkg1", "pkg2"]
            assert kwargs["env"]["LANG"] == "C"

    def test_runs_subprocess_with_force(self):
        with self._mock_proc() as mock_popen:
            remove_packages_batch(["pkg1"], force=True)
            args, kwargs = mock_popen.call_args
            assert args[0] == ["pkexec", "pacman", "-Rns", "--nodeps", "--noconfirm", "pkg1"]
            assert kwargs["env"]["LANG"] == "C"

    def test_propagates_subprocess_error(self):
        with self._mock_proc(returncode=1, stderr="fail"):
            with pytest.raises(RemovalError, match="fail"):
                remove_packages_batch(["pkg1"])


class TestLogRemoval:
    def test_writes_history_file(self):
        packages = [
            {"name": "orphan1", "size": 1000},
            {"name": "orphan2", "size": 50000000},
        ]
        with patch("unused_pkg_remover.services.HISTORY_DIR") as mock_dir:
            mock_dir.mkdir = MagicMock()
            m = mock_open()
            with patch("builtins.open", m):
                log_removal(packages)
                mock_dir.mkdir.assert_called_once_with(parents=True, exist_ok=True)
                handle = m()
                calls = [c[0][0] for c in handle.write.call_args_list]
                assert any("orphan1 | 1000.0 B" in c for c in calls)
                assert any("orphan2 | 47.7 MB" in c for c in calls)


class TestAddToIgnore:
    def test_writes_package_names(self):
        m = mock_open()
        with patch("builtins.open", m):
            add_to_ignore(Path("/some/ignore-file"), ["pkg1", "pkg2"])
            handle = m()
            handle.write.assert_any_call("pkg1\n")
            handle.write.assert_any_call("pkg2\n")

    def test_uses_provided_path(self):
        m = mock_open()
        with patch("builtins.open", m):
            add_to_ignore(Path("/custom/path"), ["pkg"])
            m.assert_called_once_with(Path("/custom/path"), "a")


class TestRemoveCachePackages:
    def _mock_proc(self, returncode=0, stdout="", stderr=""):
        proc = MagicMock()
        proc.returncode = returncode
        proc.communicate.return_value = (stdout, stderr)
        return patch("unused_pkg_remover.services.subprocess.Popen", return_value=proc)

    def test_runs_pkexec_rm_with_matching_files(self):
        f1 = MagicMock()
        f1.__str__.return_value = "/var/cache/pacman/pkg/old-pkg-1.0-1-x86_64.pkg.tar.zst"
        f1.name = "old-pkg-1.0-1-x86_64.pkg.tar.zst"
        f2 = MagicMock()
        f2.__str__.return_value = "/var/cache/pacman/pkg/other-pkg-2.0-1-x86_64.pkg.tar.zst"
        f2.name = "other-pkg-2.0-1-x86_64.pkg.tar.zst"

        with (
            patch("unused_pkg_remover.services.Path.iterdir", return_value=[f1, f2]),
            self._mock_proc() as mock_popen,
        ):
            remove_cache_packages(["old-pkg"])
            args = mock_popen.call_args[0][0]
            assert args == [
                "pkexec",
                "rm",
                "-f",
                "/var/cache/pacman/pkg/old-pkg-1.0-1-x86_64.pkg.tar.zst",
            ]

    def test_skips_when_no_matching_files(self):
        with (
            patch("unused_pkg_remover.services.Path.iterdir", return_value=[]),
            self._mock_proc() as mock_popen,
        ):
            remove_cache_packages(["old-pkg"])
            mock_popen.assert_not_called()

    def test_propagates_error(self):
        f1 = MagicMock()
        f1.__str__.return_value = "/var/cache/pacman/pkg/old-pkg-1.0-1-x86_64.pkg.tar.zst"
        f1.name = "old-pkg-1.0-1-x86_64.pkg.tar.zst"

        with (
            patch("unused_pkg_remover.services.Path.iterdir", return_value=[f1]),
            self._mock_proc(returncode=1, stderr="pkexec error"),
        ):
            with pytest.raises(RemovalError, match="pkexec error"):
                remove_cache_packages(["old-pkg"])


class TestRemoveFlatpakPackages:
    def test_runs_flatpak_uninstall(self):
        with patch("unused_pkg_remover.services.subprocess.run") as mock_run:
            remove_flatpak_packages(["runtime1", "runtime2"])
            mock_run.assert_called_once_with(
                ["flatpak", "uninstall", "-y", "runtime1", "runtime2"],
                check=True,
                capture_output=True,
                text=True,
            )

    def test_propagates_error(self):
        with patch("unused_pkg_remover.services.subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.CalledProcessError(
                1, ["flatpak"], stderr="flatpak error"
            )
            with pytest.raises(RemovalError, match="flatpak error"):
                remove_flatpak_packages(["pkg"])


class TestRemoveAurDeps:
    def test_runs_yay_with_noconfirm(self):
        with patch("unused_pkg_remover.services.subprocess.run") as mock_run:
            remove_aur_deps()
            mock_run.assert_called_once_with(
                ["yay", "-Yc", "--noconfirm"],
                check=True,
                capture_output=True,
                text=True,
            )

    def test_propagates_error(self):
        with patch("unused_pkg_remover.services.subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.CalledProcessError(1, ["yay"], stderr="yay error")
            with pytest.raises(RemovalError, match="yay error"):
                remove_aur_deps()


class TestRemoveAllCachePackages:
    def _mock_proc(self, returncode=0, stdout="", stderr=""):
        proc = MagicMock()
        proc.returncode = returncode
        proc.communicate.return_value = (stdout, stderr)
        return patch("unused_pkg_remover.services.subprocess.Popen", return_value=proc)

    def test_removes_specific_files_by_key(self):
        mock_f = MagicMock()
        mock_f.exists.return_value = True
        mock_f.__str__.return_value = "/var/cache/pacman/pkg/firefox-134.0-1-x86_64.pkg.tar.zst"

        with (
            patch("unused_pkg_remover.services.Path.__truediv__", return_value=mock_f),
            self._mock_proc() as mock_popen,
        ):
            remove_all_cache_packages(["firefox-134.0-1-x86_64"])
            args = mock_popen.call_args[0][0]
            assert "pkexec" in args
            assert "rm" in args
            assert "-f" in args
            assert any("firefox-134.0-1-x86_64" in a for a in args)

    def test_skips_when_no_files_found(self):
        mock_f = MagicMock()
        mock_f.exists.return_value = False

        with (
            patch("unused_pkg_remover.services.Path.__truediv__", return_value=mock_f),
            self._mock_proc() as mock_popen,
        ):
            remove_all_cache_packages(["no-such-pkg"])
            mock_popen.assert_not_called()


class TestRemoveAurCachePackages:
    def test_removes_aur_build_dirs(self):
        with tempfile.TemporaryDirectory() as tmp:
            yay_pkg = Path(tmp) / ".cache" / "yay" / "aur-pkg-1"
            yay_pkg.mkdir(parents=True)
            with (
                patch("unused_pkg_remover.services.Path.home", return_value=Path(tmp)),
                patch("shutil.rmtree") as mock_rmtree,
            ):
                remove_aur_cache_packages(["aur-pkg-1"])
                mock_rmtree.assert_called_once_with(yay_pkg)

    def test_skips_if_dir_not_found(self):
        with (
            patch("unused_pkg_remover.services.Path.home", return_value=Path("/tmp/no-cache")),
            patch("shutil.rmtree") as mock_rmtree,
        ):
            remove_aur_cache_packages(["no-such-pkg"])
            mock_rmtree.assert_not_called()


class TestRemoveOrphanedProtonPrefixes:
    def test_removes_compatdata_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            prefix_dir = Path(tmp) / ".steam" / "steam" / "steamapps" / "compatdata" / "12345"
            prefix_dir.mkdir(parents=True)
            with patch("unused_pkg_remover.services.Path.home", return_value=Path(tmp)):
                remove_orphaned_proton_prefixes(["12345"])
                assert not prefix_dir.exists()

    def test_skips_non_existent(self):
        with patch("unused_pkg_remover.services.Path.home", return_value=Path("/tmp/no-steam")):
            remove_orphaned_proton_prefixes(["12345"])  # should not raise


class TestRemoveObsoleteSteamRuntimes:
    def test_removes_runtime_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime_dir = (
                Path(tmp) / ".steam" / "steam" / "steamapps" / "common" / "SteamLinuxRuntime"
            )
            runtime_dir.mkdir(parents=True)
            with patch("unused_pkg_remover.services.Path.home", return_value=Path(tmp)):
                remove_obsolete_steam_runtimes(["SteamLinuxRuntime"])
                assert not runtime_dir.exists()

    def test_skips_non_existent(self):
        with patch("unused_pkg_remover.services.Path.home", return_value=Path("/tmp/no-steam")):
            remove_obsolete_steam_runtimes(["NoSuchRuntime"])  # should not raise


class TestRemoveStaleLauncherRunners:
    def test_removes_lutris_runner(self):
        with tempfile.TemporaryDirectory() as tmp:
            runner_dir = Path(tmp) / ".local" / "share" / "lutris" / "runners" / "wine-7.0"
            runner_dir.mkdir(parents=True)
            with patch("unused_pkg_remover.services.Path.home", return_value=Path(tmp)):
                remove_stale_launcher_runners(["lutris:wine-7.0"])
                assert not runner_dir.exists()

    def test_removes_heroic_runner(self):
        with tempfile.TemporaryDirectory() as tmp:
            runner_dir = (
                Path(tmp) / ".config" / "heroic" / "tools" / "runners" / "proton" / "GE-Proton8"
            )
            runner_dir.mkdir(parents=True)
            with patch("unused_pkg_remover.services.Path.home", return_value=Path(tmp)):
                remove_stale_launcher_runners(["heroic:proton/GE-Proton8"])
                assert not runner_dir.exists()

    def test_removes_bottles_runner(self):
        with tempfile.TemporaryDirectory() as tmp:
            runner_dir = Path(tmp) / ".local" / "share" / "bottles" / "runners" / "wine-8.0"
            runner_dir.mkdir(parents=True)
            with patch("unused_pkg_remover.services.Path.home", return_value=Path(tmp)):
                remove_stale_launcher_runners(["bottles:wine-8.0"])
                assert not runner_dir.exists()

    def test_skips_unknown_prefix(self):
        with patch("shutil.rmtree") as mock_rmtree:
            remove_stale_launcher_runners(["unknown:foo"])
            mock_rmtree.assert_not_called()
