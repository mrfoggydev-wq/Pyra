![Python](https://img.shields.io/badge/python-3.10+-blue)
![Tests](https://github.com/mrfoggydev-wq/Pyra/actions/workflows/tests.yml/badge.svg)
![License](https://img.shields.io/badge/license-MIT-green)
![Platform](https://img.shields.io/badge/platform-Windows-lightgrey)

# Pyra

Pyra — язык с файлами `.fm` и полной совместимостью с Python. Он использует CPython для выполнения кода, поэтому поддерживает синтаксис Python, классы, функции, исключения, асинхронность, стандартную библиотеку и установленные пакеты.

Это не переписанный с нуля Python: отдельный слой Pyra добавляет команду `pyra` и импорт модулей `.fm`, а сам код выполняется стандартным Python runtime. Расширение `.pyra` тоже поддерживается для совместимости.

## Зачем Pyra

Pyra предназначена для тех, кто хочет писать Python-совместимый код в файлах `.fm` и пользоваться одной командой для повседневных задач: создания проекта, управления зависимостями, виртуальными средами и сборки Windows-приложений. Автономный SDK позволяет запускать Pyra и собранные приложения без отдельной установки Python на целевом компьютере.

Pyra не заменяет Python runtime и не обещает иной производительности: это проектный CLI, загрузчик `.fm`-модулей и собственная упаковка вокруг CPython.

## Отличия от Python

- Исходники Pyra обычно имеют расширение `.fm`; синтаксис и семантика кода остаются Python.
- Команда `pyra` добавляет `new`, `run`, `fmt`, `doc`, `init`, `clean`, `doctor`, `version`, `upgrade`, `install`, `list`, `uninstall`, `venv` и `build`.
- Pyra загружает модули `.fm` и умеет упаковывать проект вместе с CPython runtime.
- Обычный Python использует `.py` и стандартные инструменты `python`/`pip`; код Pyra выполняется CPython и совместим с его библиотеками.

Создать и запустить новый проект:

```powershell
pyra new my-project
cd my-project
pyra main.fm
```

## Требования

- Для разработки и запуска исходников: Python 3.10+.
- Для запуска опубликованного автономного `Pyra.exe` Python не требуется.
- Для сборки Windows exe и установщика: Windows, Pillow и системный C# compiler `csc.exe`.

## Разработка

После клонирования репозитория создай среду и установи Pyra в editable-режиме:

```powershell
py -3.10 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
```

Теперь команда `pyra` доступна в этой среде. Запусти тесты перед отправкой изменений:

```powershell
python -m unittest discover -s tests -v
```

GitHub Actions автоматически запускает тесты на Windows с Python 3.10–3.14 при push и pull request.

## Запуск из папки проекта

```powershell
pyra --version
pyra examples/hello.fm
pyra run examples/hello.fm
pyra --check examples/hello.fm
pyra -c "print('Привет из Pyra')"
pyra -m http.server 8000
```

## Инструменты проекта

```powershell
pyra fmt app.fm
pyra doc app.fm
pyra init
pyra doctor
pyra version
pyra clean
pyra upgrade
```

`fmt` использует Black; `doc` генерирует `docs/app.md` из docstrings функций и классов. `init` создаёт `pyra.toml` и не перезаписывает существующий. `doctor` проверяет Python, pip, Black, компилятор и место под кэш. `version` показывает версию, интерпретатор и расположение Pyra.

`clean` сначала перечисляет файлы и спрашивает подтверждение; он удаляет только локальные `.venv` и кэши проекта. `pyra clean --yes` пропускает подтверждение. `upgrade` делает `git pull --ff-only` в чистом checkout либо устанавливает актуальный SDK из GitHub в standalone-установке.

## Команды проекта

```powershell
pyra init                 # создать pyra.toml
pyra fmt app.fm           # форматировать код через Black
pyra doc app.fm           # создать docs/app.md из docstrings
pyra doctor               # проверить окружение
pyra version              # показать версию и пути установки
pyra clean                # спросить подтверждение и очистить .venv/кэш
pyra upgrade              # обновить чистый checkout или standalone SDK
```

`pyra clean --yes` выполняет очистку без вопроса. Команда не удаляет кэш вне проекта. `pyra upgrade` в исходном репозитории требует чистого Git checkout; standalone SDK скачивает актуальные исходники с GitHub для следующего запуска.

## Сборка приложения

Сборщик Pyra самостоятельно упаковывает `.fm`-файлы и компилирует Windows-загрузчик; PyInstaller не используется. Для сборки нужен Windows с `csc.exe` и установленный Pillow:

```powershell
pyra build examples/hello.fm
```

Результат появится в `dist/hello.exe`. Если `--icon` не указан, используется `icon.ico` из корня проекта. Допустимы `--name`, `--output-dir`, `--add-data` и `--icon`.

Загрузчик распаковывает приложение и встроенный CPython runtime в кэш на диске с достаточным местом. На компьютере запуска устанавливать Python не нужно. В exe входят стандартная библиотека и пакеты из активной `.venv` или среды сборки.

## Автономный Pyra

Чтобы создать версию Pyra, которой можно пользоваться без установленного Python:

```powershell
python -m pyra build --sdk
```

Команда создаст `dist/Pyra.exe`. В этом workspace VS Code добавляет `dist` в `PATH` новых терминалов. Закрой и открой терминал, затем используй команды:

```powershell
pyra --version
pyra examples\hello.fm
pyra install requests
pyra build examples\hello.fm
```

SDK содержит Python runtime и установленные на компьютере сборки пакеты. Команда `pyra install requests` устанавливает библиотеки с PyPI в `%LOCALAPPDATA%/Pyra/packages`; этот каталог используется при запуске программ и включается в новые сборки. Python нужен только для первоначальной команды создания SDK.

Для изоляции зависимостей проекта создай и активируй виртуальную среду:

```powershell
pyra venv
.\.venv\Scripts\Activate.ps1
pyra install requests
pyra list
pyra uninstall requests
```

`pyra list` показывает пакеты только в активной среде. `pyra uninstall` удаляет файлы выбранного пакета из этой среды, не затрагивая другие библиотеки.

## Установщик Windows

Собранные exe находятся в `dist`, которая исключена из Git. Для публикации установщик `PyraSetup-Toolkit.exe` и SDK `Pyra.exe` прикрепляются к GitHub Release. Сам актуальный `Pyra.exe` встроен в установщик, поэтому ссылка на скачивание и интернет для установки не нужны. Установщик копирует Pyra в `Program Files/Pyra` и добавляет каталог в системный `PATH`; запускать его нужно от имени администратора.

Для пересборки установщика используй Windows C# compiler:

```powershell
$csc = "$env:WINDIR\Microsoft.NET\Framework64\v4.0.30319\csc.exe"
$source = (Resolve-Path .\pyra\installer.cs).Path
$pyra = (Resolve-Path .\dist\Pyra.exe).Path
& $csc /nologo /target:winexe /out:dist/PyraSetup-Toolkit.exe "/resource:$pyra,PyraExecutable" /reference:System.Windows.Forms.dll /reference:System.Drawing.dll $source
```

После установки открой новый терминал и проверь команду `pyra --version`.

Передача аргументов программе:

```powershell
pyra examples/hello.fm первый второй
```

## Установка команды `pyra`

Для разработки самого CLI из исходников:

```powershell
python -m pip install -e .
```

Без аргументов запускается интерактивный режим. Внутри `.fm` можно использовать обычные импорты Python; другие файлы `.fm` импортируются как модули, в том числе пакеты с `__init__.fm`.

Команда `pyra --check program.fm` проверяет синтаксис, не выполняя программу. Файлы `.fm` в этом проекте распознаются VS Code как Python-код для подсветки синтаксиса.

## Пример

```python
def square(number: int) -> int:
    return number ** 2


values = [square(number) for number in range(5)]
print(values)
```

Сохраните код, например, в `program.fm` и запустите `pyra program.fm`.
