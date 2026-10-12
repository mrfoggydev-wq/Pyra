import subprocess
import csv
import os
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from pyra.cli import (
    _add_python_runtime,
    _create_build_archive,
    _create_virtual_environment,
    _install_packages,
    _package_directory,
    _uninstall_packages,
    _prepare_icon,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class PyraCliTests(unittest.TestCase):
    def run_pyra(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-m", "pyra", *arguments],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_runs_python_syntax_from_fm_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            script = Path(temporary_directory) / "program.fm"
            script.write_text("print(sum(value * value for value in range(4)))\n", encoding="utf-8")

            result = self.run_pyra(str(script))

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "14")

    def test_imports_fm_module(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            (directory / "helper.fm").write_text("answer = 42\n", encoding="utf-8")
            script = directory / "program.fm"
            script.write_text("import helper\nprint(helper.answer)\n", encoding="utf-8")

            result = self.run_pyra(str(script))

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "42")

    def test_runs_inline_command(self) -> None:
        result = self.run_pyra("-c", "print(6 * 7)")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "42")

    @patch("pyra.cli.subprocess.run")
    def test_install_uses_pip_and_user_site_target(self, run_process: object) -> None:
        run_process.return_value.returncode = 0

        with tempfile.TemporaryDirectory() as temporary_directory, patch(
            "pyra.cli.Path.cwd", return_value=Path(temporary_directory)
        ):
            result = _install_packages(["requests==2.32.0"])

        self.assertEqual(result, 0)
        run_process.assert_called_once_with(
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                "--disable-pip-version-check",
                "--upgrade",
                "--target",
                str(Path.home() / "AppData" / "Roaming" / "Python" / f"Python{sys.version_info.major}{sys.version_info.minor}" / "site-packages"),
                "requests==2.32.0",
            ],
            check=False,
        )

    def test_package_directory_auto_detects_project_venv(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            project = Path(temporary_directory)
            environment = project / ".venv"
            (environment / "Scripts").mkdir(parents=True)
            (environment / "Scripts" / "python.exe").touch()
            expected_directory = environment / "Lib" / "site-packages"

            with patch("pyra.cli.Path.cwd", return_value=project), patch.dict(
                os.environ, {"VIRTUAL_ENV": "", "PYRA_PACKAGE_DIR": ""}, clear=False
            ):
                package_directory = _package_directory()

        self.assertEqual(package_directory, expected_directory)

    @patch("pyra.cli.subprocess.run")
    def test_install_embedded_uses_persistent_package_directory(self, run_process: object) -> None:
        run_process.return_value.returncode = 0
        with tempfile.TemporaryDirectory() as temporary_directory, patch.dict(
            "os.environ", {"PYRA_PACKAGE_DIR": temporary_directory}
        ):
            result = _install_packages(["requests"])

        self.assertEqual(result, 0)
        run_process.assert_called_once_with(
            [sys.executable, "-m", "pip", "install", "--disable-pip-version-check", "--upgrade", "--target", temporary_directory, "requests"],
            check=False,
        )

    def test_uninstall_removes_only_files_listed_for_selected_distribution(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            package_directory = Path(temporary_directory)
            dist_info = package_directory / "demo_package-1.0.dist-info"
            dist_info.mkdir()
            package_file = package_directory / "demo_package.py"
            package_file.write_text("value = 1\n", encoding="utf-8")
            metadata_file = dist_info / "METADATA"
            metadata_file.write_text(
                "Metadata-Version: 2.1\nName: demo-package\nVersion: 1.0\n",
                encoding="utf-8",
            )
            record_file = dist_info / "RECORD"
            with record_file.open("w", newline="", encoding="utf-8") as file:
                writer = csv.writer(file)
                writer.writerow(["demo_package.py", "", ""])
                writer.writerow(["demo_package-1.0.dist-info/METADATA", "", ""])
                writer.writerow(["demo_package-1.0.dist-info/RECORD", "", ""])
            unrelated_file = package_directory / "unrelated.py"
            unrelated_file.write_text("value = 2\n", encoding="utf-8")

            with patch.dict(os.environ, {"PYRA_PACKAGE_DIR": temporary_directory}):
                result = _uninstall_packages(["demo_package"])

            self.assertEqual(result, 0)
            self.assertFalse(package_file.exists())
            self.assertTrue(unrelated_file.exists())

    @patch("pyra.cli.subprocess.run")
    def test_venv_creates_default_dot_venv_without_inheriting_python_paths(self, run_process: object) -> None:
        run_process.return_value.returncode = 0
        with patch.dict(
            os.environ,
            {
                "PYTHONHOME": "runtime",
                "PYTHONPATH": "packages",
                "PYRA_PACKAGE_DIR": "packages",
                "PYRA_EMBEDDED_RUNTIME": "1",
            },
        ):
            result = _create_virtual_environment([".venv"])

        self.assertEqual(result, 0)
        arguments = run_process.call_args.args[0]
        self.assertEqual(arguments[:3], [sys.executable, "-m", "venv"])
        environment = run_process.call_args.kwargs["env"]
        self.assertNotIn("PYTHONHOME", environment)
        self.assertNotIn("PYTHONPATH", environment)
        self.assertNotIn("PYRA_PACKAGE_DIR", environment)

    def test_check_does_not_execute_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            script = Path(temporary_directory) / "program.fm"
            script.write_text("print('this must not run')\n", encoding="utf-8")

            result = self.run_pyra("--check", str(script))

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Синтаксис OK", result.stdout)
        self.assertNotIn("this must not run", result.stdout)

    def test_build_help_lists_custom_options(self) -> None:
        result = self.run_pyra("build", "--help")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--icon", result.stdout)
        self.assertIn("--add-data", result.stdout)
        self.assertIn("--sdk", result.stdout)

    def test_build_archive_contains_source_modules_and_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            source = directory / "main.fm"
            source.write_text("import helper\n", encoding="utf-8")
            (directory / "helper.fm").write_text("value = 42\n", encoding="utf-8")
            bundle = directory / "app.zip"

            _create_build_archive(bundle, source, PROJECT_ROOT / "pyra", [])

            with zipfile.ZipFile(bundle) as archive:
                names = archive.namelist()

        self.assertIn("app/main.fm", names)
        self.assertIn("app/helper.fm", names)
        self.assertIn("app/pyra/runtime.py", names)
        self.assertIn("app/_pyra_bootstrap.py", names)

    def test_sdk_archive_contains_cli_and_icon(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            bundle = directory / "sdk.zip"
            icon = PROJECT_ROOT / "icon.ico"

            _create_build_archive(
                bundle,
                None,
                PROJECT_ROOT / "pyra",
                [],
                sdk_mode=True,
                icon=icon,
            )

            with zipfile.ZipFile(bundle) as archive:
                names = archive.namelist()

        self.assertIn("app/_pyra_cli.py", names)
        self.assertIn("app/icon.ico", names)
        self.assertIn("app/pyra/launcher.cs", names)

    def test_prepare_icon_converts_png_named_ico(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            mislabeled_icon = directory / "icon.ico"
            Image.new("RGBA", (32, 32), (20, 120, 220, 255)).save(mislabeled_icon, format="PNG")

            converted = _prepare_icon(mislabeled_icon, directory)
            self.assertEqual(converted.suffix, ".ico")
            self.assertEqual(converted.read_bytes()[:4], b"\x00\x00\x01\x00")

    def test_python_runtime_archive_contains_interpreter_stdlib_and_packages(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "DLLs").mkdir()
            (root / "Lib" / "site-packages").mkdir(parents=True)
            (root / "python.exe").write_bytes(b"python")
            (root / "python314.dll").write_bytes(b"dll")
            (root / "DLLs" / "_test.pyd").write_bytes(b"extension")
            (root / "Lib" / "os.py").write_text("", encoding="utf-8")
            (root / "Lib" / "site-packages" / "base_package.py").write_text("", encoding="utf-8")
            user_site = root / "user-site"
            user_site.mkdir()
            (user_site / "user_package.py").write_text("", encoding="utf-8")
            bundle_path = root / "bundle.zip"

            with zipfile.ZipFile(bundle_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                _add_python_runtime(archive, root, [user_site])
            with zipfile.ZipFile(bundle_path) as archive:
                names = archive.namelist()

        self.assertIn("runtime/python.exe", names)
        self.assertIn("runtime/python314.dll", names)
        self.assertIn("runtime/DLLs/_test.pyd", names)
        self.assertIn("runtime/Lib/os.py", names)
        self.assertIn("runtime/Lib/site-packages/base_package.py", names)
        self.assertIn("runtime/Lib/site-packages/user_package.py", names)

if __name__ == "__main__":
    unittest.main()
