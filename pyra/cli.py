"""Command-line runner and custom Windows builder for Pyra."""

import argparse
import code
import hashlib
import importlib.metadata
import os
import runpy
import site
import shutil
import subprocess
import sys
import tempfile
import tokenize
import zipfile
from pathlib import Path

from . import __version__
from .runtime import install_importer


def _compile_file(filename: str) -> tuple[Path, object]:
    path = Path(filename).resolve()
    with tokenize.open(path) as source_file:
        source = source_file.read()
    return path, compile(source, str(path), "exec", dont_inherit=True)


def _execute_file(filename: str, arguments: list[str]) -> None:
    path, compiled = _compile_file(filename)
    install_importer()
    sys.argv = [str(path), *arguments]
    sys.path[0] = str(path.parent)
    namespace = {
        "__name__": "__main__",
        "__file__": str(path),
        "__package__": None,
        "__cached__": None,
    }
    exec(compiled, namespace)


def _check_file(filename: str) -> None:
    path, _ = _compile_file(filename)
    print(f"Синтаксис OK: {path.name}")


def _execute_command(source: str, arguments: list[str]) -> None:
    install_importer()
    sys.argv = ["-c", *arguments]
    sys.path[0] = ""
    namespace = {"__name__": "__main__", "__package__": None}
    exec(compile(source, "<string>", "exec", dont_inherit=True), namespace)


def _install_packages(packages: list[str]) -> int:
    if not packages:
        print("Использование: pyra install <пакет>", file=sys.stderr)
        return 2

    package_directory = _package_directory()
    package_directory.mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable,
        "-m",
        "pip",
        "install",
        "--disable-pip-version-check",
        "--upgrade",
        "--target",
        str(package_directory),
    ]
    command.extend(packages)
    return subprocess.run(command, check=False).returncode


def _package_directory() -> Path:
    virtual_environment = os.environ.get("VIRTUAL_ENV")
    if virtual_environment:
        return Path(virtual_environment) / "Lib" / "site-packages"
    configured_directory = os.environ.get("PYRA_PACKAGE_DIR")
    if configured_directory:
        return Path(configured_directory)
    project_environment = _find_project_environment(Path.cwd())
    if project_environment is not None:
        return project_environment / "Lib" / "site-packages"
    return Path(site.getusersitepackages())


def _find_project_environment(directory: Path) -> Path | None:
    for parent in (directory, *directory.parents):
        environment = parent / ".venv"
        if (environment / "Scripts" / "python.exe").is_file():
            return environment
    return None


def _list_packages() -> int:
    package_directory = _package_directory()
    if not package_directory.is_dir():
        print("Библиотеки Pyra не установлены.")
        return 0
    return subprocess.run(
        [sys.executable, "-m", "pip", "list", "--path", str(package_directory)],
        check=False,
    ).returncode


def _uninstall_packages(packages: list[str]) -> int:
    if not packages:
        print("Использование: pyra uninstall <пакет>", file=sys.stderr)
        return 2

    package_directory = _package_directory().resolve()
    if not package_directory.is_dir():
        print("Библиотеки Pyra не установлены.")
        return 0

    def normalize(name: str) -> str:
        return "-".join(name.lower().replace("_", "-").replace(".", "-").split("-"))

    result_code = 0
    distributions = list(importlib.metadata.distributions(path=[str(package_directory)]))
    for package in packages:
        matches = [
            distribution
            for distribution in distributions
            if distribution.metadata.get("Name")
            and normalize(distribution.metadata["Name"]) == normalize(package)
        ]
        if not matches:
            print(f"Пакет не найден в среде Pyra: {package}", file=sys.stderr)
            result_code = 1
            continue

        for distribution in matches:
            removable_paths = set()
            for entry in distribution.files or ():
                file_path = Path(distribution.locate_file(entry)).resolve()
                try:
                    file_path.relative_to(package_directory)
                except ValueError:
                    continue
                if file_path.is_file() or file_path.is_symlink():
                    removable_paths.add(file_path)

            for file_path in removable_paths:
                file_path.unlink(missing_ok=True)
            for directory in sorted(
                {parent for path in removable_paths for parent in path.parents if parent != package_directory},
                key=lambda path: len(path.parts),
                reverse=True,
            ):
                try:
                    directory.rmdir()
                except OSError:
                    pass
        print(f"Удалён пакет: {package}")
    return result_code


def _create_virtual_environment(arguments: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="pyra venv", description="Создать виртуальную среду Python для Pyra.")
    parser.add_argument("path", nargs="?", type=Path, default=Path(".venv"), help="папка; по умолчанию .venv")
    parser.add_argument(
        "--system-site-packages",
        action="store_true",
        help="разрешить доступ к системным пакетам",
    )
    options = parser.parse_args(arguments)
    command = [sys.executable, "-m", "venv"]
    if options.system_site_packages:
        command.append("--system-site-packages")
    path = options.path.expanduser().resolve()
    command.append(str(path))

    environment = os.environ.copy()
    for name in ("PYTHONHOME", "PYTHONPATH", "PYRA_PACKAGE_DIR", "PYRA_EMBEDDED_RUNTIME"):
        environment.pop(name, None)
    result = subprocess.run(command, env=environment, check=False)
    if result.returncode == 0:
        print(f"Создана виртуальная среда: {path}")
        activation_script = path / "Scripts" / "Activate.ps1"
        print(f"Активация PowerShell: & '{activation_script}'")
    return result.returncode


def _create_project(arguments: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="pyra new", description="Создать стартовый проект Pyra.")
    parser.add_argument("name", help="имя папки проекта")
    options = parser.parse_args(arguments)

    name = options.name
    if (
        not name.isascii()
        or not name[0].isalnum()
        or any(not (character.isalnum() or character in "-_ ") for character in name)
        or name != name.strip()
    ):
        parser.error("имя проекта может содержать только латинские буквы, цифры, пробел, дефис и подчёркивание")

    project_directory = (Path.cwd() / name).resolve()
    if project_directory.exists():
        parser.error(f"папка уже существует: {project_directory}")

    package_name = name.lower().replace("_", "-").replace(" ", "-")
    project_directory.mkdir(parents=True)
    (project_directory / "main.fm").write_text(
        "def main() -> None:\n"
        f"    print(\"Привет из проекта {name}!\")\n"
        "\n\n"
        "if __name__ == \"__main__\":\n"
        "    main()\n",
        encoding="utf-8",
    )
    (project_directory / "README.md").write_text(
        f"# {name}\n\n"
        "Проект на языке Pyra.\n\n"
        "## Запуск\n\n"
        "```powershell\n"
        "pyra main.fm\n"
        "```\n\n"
        "## Зависимости\n\n"
        "Установить пакет из PyPI: `pyra install имя-пакета`.\n\n"
        "## Сборка\n\n"
        "```powershell\n"
        "pyra build main.fm\n"
        "```\n",
        encoding="utf-8",
    )
    (project_directory / ".gitignore").write_text(
        ".venv/\n__pycache__/\n*.py[cod]\nbuild/\ndist/\n.pyra-cache/\n",
        encoding="utf-8",
    )
    (project_directory / "pyproject.toml").write_text(
        f"[project]\nname = \"{package_name}\"\nversion = \"0.1.0\"\n"
        "requires-python = \">=3.10\"\n\n"
        "[tool.pyra]\nentrypoint = \"main.fm\"\n",
        encoding="utf-8",
    )

    print(f"Создан проект: {project_directory}")
    print(f"Запуск: pyra {name}/main.fm")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pyra",
        description="Запускает и проверяет Python-совместимые программы .fm.",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("-c", "--command", help="выполнить исходный код")
    mode.add_argument("-m", "--module", help="запустить модуль как программу")
    mode.add_argument("--check", metavar="FILE", help="проверить синтаксис файла, не запуская его")
    parser.add_argument("-V", "--version", action="version", version=f"Pyra {__version__}")
    parser.add_argument("script", nargs="?", help="путь к файлу .fm")
    parser.add_argument("args", nargs=argparse.REMAINDER, help="аргументы программы")
    return parser


def _csharp_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _create_build_archive(
    bundle: Path,
    source: Path | None,
    runtime_root: Path,
    additional_data: list[Path],
    sdk_mode: bool = False,
    icon: Path | None = None,
) -> None:
    source_root = source.parent if source is not None else runtime_root.parent
    with zipfile.ZipFile(bundle, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for file_path in source_root.rglob("*"):
            if file_path.is_file() and file_path.suffix.lower() in {".fm", ".pyra"}:
                archive.write(file_path, (Path("app") / file_path.relative_to(source_root)).as_posix())

        for file_path in runtime_root.glob("*.py"):
            archive.write(file_path, (Path("app") / "pyra" / file_path.name).as_posix())
        archive.write(runtime_root / "launcher.cs", "app/pyra/launcher.cs")

        if sdk_mode:
            archive.writestr(
                "app/_pyra_cli.py",
                "import sys\n"
                "from pathlib import Path\n"
                "sys.path.insert(0, str(Path(__file__).resolve().parent))\n"
                "from pyra.cli import main\n"
                "raise SystemExit(main())\n",
            )
            if icon is not None:
                archive.write(icon, "app/icon.ico")

        archive.writestr(
            "app/_pyra_bootstrap.py",
            "import sys, tokenize\n"
            "from pathlib import Path\n"
            "from pyra.runtime import install_importer\n"
            "app_root = Path(__file__).resolve().parent\n"
            "source_name, *arguments = sys.argv[1:]\n"
            "program = (app_root / source_name).resolve()\n"
            "sys.path.insert(0, str(program.parent))\n"
            "install_importer()\n"
            "sys.argv = [str(program), *arguments]\n"
            "with tokenize.open(program) as source_file:\n"
            "    source_code = source_file.read()\n"
            "namespace = {'__name__': '__main__', '__file__': str(program), '__package__': None, '__cached__': None}\n"
            "exec(compile(source_code, str(program), 'exec', dont_inherit=True), namespace)\n",
        )

        for index, data_path in enumerate(additional_data):
            resolved_path = data_path.resolve()
            target = Path("app") / "_data" / str(index) / resolved_path.name
            if resolved_path.is_file():
                archive.write(resolved_path, target.as_posix())
            else:
                for file_path in resolved_path.rglob("*"):
                    if file_path.is_file():
                        relative_path = file_path.relative_to(resolved_path)
                        archive.write(file_path, (target / relative_path).as_posix())


def _add_python_runtime(
    archive: zipfile.ZipFile,
    python_root: Path,
    user_site_packages: list[Path],
) -> None:
    for file_path in python_root.iterdir():
        if not file_path.is_file():
            continue
        if file_path.suffix.lower() == ".dll" or file_path.name in {"python.exe", "pythonw.exe", "LICENSE.txt"}:
            archive.write(file_path, (Path("runtime") / file_path.name).as_posix())
        elif file_path.suffix.lower() == ".zip" and file_path.name.lower().startswith("python"):
            archive.write(file_path, (Path("runtime") / file_path.name).as_posix())

    for directory_name in ("DLLs", "Lib", "tcl"):
        directory = python_root / directory_name
        if not directory.is_dir():
            continue
        for file_path in directory.rglob("*"):
            if not file_path.is_file() or file_path.suffix.lower() == ".pyc":
                continue
            relative_path = file_path.relative_to(directory)
            if "__pycache__" in relative_path.parts:
                continue
            if directory_name == "Lib" and relative_path.parts[0].lower() == "site-packages":
                continue
            archive_name = Path("runtime") / directory_name / relative_path
            archive.write(file_path, archive_name.as_posix())

    package_files: dict[str, Path] = {}
    package_directories = [python_root / "Lib" / "site-packages", *user_site_packages]
    for package_directory in package_directories:
        if not package_directory.is_dir():
            continue
        for file_path in package_directory.rglob("*"):
            if file_path.is_file() and "__pycache__" not in file_path.parts:
                package_files[file_path.relative_to(package_directory).as_posix()] = file_path
    for relative_path, file_path in package_files.items():
        archive.write(file_path, f"runtime/Lib/site-packages/{relative_path}")


def _prepare_icon(icon: Path, temporary_path: Path) -> Path:
    with icon.open("rb") as icon_file:
        signature = icon_file.read(8)
    if signature[:4] == b"\x00\x00\x01\x00":
        return icon
    if signature != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"Неизвестный формат иконки: {icon}")

    from PIL import Image

    converted_icon = temporary_path / "converted-icon.ico"
    with Image.open(icon) as image:
        image.convert("RGBA").save(
            converted_icon,
            format="ICO",
            sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
        )
    return converted_icon


def _build_executable(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="pyra build",
        description="Создаёт собственный exe-пакет программы Pyra без PyInstaller.",
    )
    parser.add_argument("source", type=Path, nargs="?", help="исходный файл .fm")
    parser.add_argument("--name", help="имя приложения")
    parser.add_argument("--sdk", action="store_true", help="собрать автономный Pyra.exe для запуска .fm без Python")
    parser.add_argument("--icon", type=Path, help="файл .ico; по умолчанию icon.ico из корня проекта")
    parser.add_argument("--output-dir", type=Path, help="папка результата; по умолчанию dist")
    parser.add_argument("--add-data", action="append", type=Path, default=[], help="добавить файл или папку в пакет")
    options = parser.parse_args(argv)

    source = options.source.resolve() if options.source is not None else None
    if options.sdk and source is not None:
        parser.error("не указывайте исходный файл вместе с --sdk")
    if not options.sdk and source is None:
        parser.error("укажите .fm файл или используйте --sdk")
    if source is not None and not source.is_file():
        parser.error(f"файл не найден: {source}")
    if source is not None and source.suffix.lower() not in {".fm", ".pyra"}:
        parser.error("исходный файл должен иметь расширение .fm или .pyra")
    if sys.platform != "win32":
        print("Собственная сборка exe сейчас поддерживается только в Windows.", file=sys.stderr)
        return 1

    name = options.name or ("Pyra" if options.sdk else source.stem)
    if any(character in name for character in '<>:\\"/|?*') or name in {"", ".", ".."}:
        parser.error("имя приложения содержит недопустимые символы")

    project_root = Path(__file__).resolve().parents[1]
    runtime_root = Path(__file__).resolve().parent
    default_icon = Path.cwd() / "icon.ico"
    if not default_icon.is_file():
        default_icon = project_root / "icon.ico"
    icon = (options.icon or default_icon).resolve()
    if not icon.is_file():
        parser.error(f"файл иконки не найден: {icon}")
    if icon.suffix.lower() != ".ico":
        parser.error("иконка должна быть в формате .ico")
    for data_path in options.add_data:
        if not data_path.exists():
            parser.error(f"дополнительный файл не найден: {data_path}")

    windows_dir = Path(os.environ.get("WINDIR", r"C:\Windows"))
    compiler_candidates = [
        windows_dir / "Microsoft.NET" / "Framework64" / "v4.0.30319" / "csc.exe",
        windows_dir / "Microsoft.NET" / "Framework" / "v4.0.30319" / "csc.exe",
    ]
    compiler = next((path for path in compiler_candidates if path.is_file()), None)
    if compiler is None:
        print("Не найден встроенный компилятор Windows csc.exe.", file=sys.stderr)
        return 1

    output_dir = (options.output_dir or Path.cwd() / "dist").resolve()
    output_path = output_dir / f"{name}.exe"

    with tempfile.TemporaryDirectory(prefix="pyra-build-") as temporary_directory:
        temporary_path = Path(temporary_directory)
        build_icon = _prepare_icon(icon, temporary_path)
        bundle = temporary_path / "app.zip"
        _create_build_archive(
            bundle,
            source,
            runtime_root,
            options.add_data,
            sdk_mode=options.sdk,
            icon=build_icon if options.sdk else None,
        )
        user_site = Path(site.getusersitepackages())
        with zipfile.ZipFile(bundle, "a", compression=zipfile.ZIP_DEFLATED) as archive:
            virtual_environment = os.environ.get("VIRTUAL_ENV")
            package_directory = os.environ.get("PYRA_PACKAGE_DIR")
            user_sites = []
            if virtual_environment:
                user_sites.append(Path(virtual_environment) / "Lib" / "site-packages")
            elif source is not None:
                project_environment = _find_project_environment(source.parent)
                if project_environment is not None:
                    user_sites.append(project_environment / "Lib" / "site-packages")
            elif package_directory:
                user_sites.append(Path(package_directory))
            if package_directory and Path(package_directory) not in user_sites:
                user_sites.append(Path(package_directory))
            if os.environ.get("PYRA_EMBEDDED_RUNTIME") != "1":
                user_sites.append(user_site)
            _add_python_runtime(archive, Path(sys.base_prefix), user_sites)
        bundle_hash = hashlib.sha256()
        with bundle.open("rb") as bundle_file:
            for chunk in iter(lambda: bundle_file.read(1024 * 1024), b""):
                bundle_hash.update(chunk)
        bundle_id = bundle_hash.hexdigest()[:16]
        launcher_template = (runtime_root / "launcher.cs").read_text(encoding="utf-8")
        launcher_source = temporary_path / "launcher.cs"
        launcher_source.write_text(
            launcher_template.replace("@@APP_NAME@@", _csharp_string(name))
            .replace("@@BUNDLE_ID@@", _csharp_string(bundle_id))
            .replace("@@SOURCE_FILENAME@@", _csharp_string(source.name if source is not None else ""))
            .replace("@@SDK_MODE@@", "true" if options.sdk else "false"),
            encoding="utf-8-sig",
        )
        temporary_exe = temporary_path / f"{name}.exe"
        command = [
            str(compiler),
            "/nologo",
            f"/out:{temporary_exe}",
            f"/win32icon:{build_icon}",
            f"/resource:{bundle},PyraBundle",
            "/reference:System.IO.Compression.dll",
            str(launcher_source),
        ]
        result = subprocess.run(command, check=False)
        if result.returncode != 0:
            return result.returncode

        output_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(temporary_exe, output_path)

    print(f"Готово: {output_path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    arguments_list = list(sys.argv[1:] if argv is None else argv)
    if arguments_list and arguments_list[0] == "new":
        return _create_project(arguments_list[1:])
    if arguments_list and arguments_list[0] == "list":
        if len(arguments_list) > 1:
            print("Использование: pyra list", file=sys.stderr)
            return 2
        return _list_packages()
    if arguments_list and arguments_list[0] == "uninstall":
        return _uninstall_packages(arguments_list[1:])
    if arguments_list and arguments_list[0] == "venv":
        return _create_virtual_environment(arguments_list[1:])
    if arguments_list and arguments_list[0] == "install":
        return _install_packages(arguments_list[1:])
    if arguments_list and arguments_list[0] == "build":
        return _build_executable(arguments_list[1:])

    options = _build_parser().parse_args(arguments_list)
    arguments = options.args
    if arguments and arguments[0] == "--":
        arguments = arguments[1:]

    if options.command is not None:
        _execute_command(options.command, arguments)
    elif options.module is not None:
        install_importer()
        sys.argv = [options.module, *arguments]
        runpy.run_module(options.module, run_name="__main__", alter_sys=True)
    elif options.check is not None:
        _check_file(options.check)
    elif options.script is not None:
        _execute_file(options.script, arguments)
    else:
        code.interact(
            banner=f"Pyra {__version__} на Python {sys.version.split()[0]}\nВведите help() для справки.",
            exitmsg="До встречи!",
        )
    return 0
