"""CI check: the built packages (sdist and wheel) contain every shipped
fixture file and GUI asset. Run from the repository root after `uv build`:

    python .github/check_package_data.py dist
"""

import sys
import tarfile
import zipfile
from pathlib import Path

DATA   = Path('src/pylzr/fixtures/data')
ASSETS = Path('src/pylzr/gui/assets')


def main(dist: Path) -> int:
    expected = set()
    for folder, pattern in ((DATA, '*.json'), (ASSETS, '*')):
        found = {path.relative_to('src').as_posix() for path in folder.rglob(pattern) if path.is_file()}
        if not found:
            print(f'no files found under {folder}')
            return 1
        expected |= found
    wheels, sdists = list(dist.glob('*.whl')), list(dist.glob('*.tar.gz'))
    if len(wheels) != 1 or len(sdists) != 1:
        print(f'expected one wheel and one sdist in {dist}, found {wheels + sdists}')
        return 1
    with zipfile.ZipFile(wheels[0]) as wheel:
        in_wheel = set(wheel.namelist())
    with tarfile.open(sdists[0]) as sdist:              # names look like pylzr-0.5.0/src/pylzr/…
        in_sdist = {name.split('/', 1)[1].removeprefix('src/') for name in sdist.getnames() if '/' in name}
    missing = {'wheel': sorted(expected - in_wheel), 'sdist': sorted(expected - in_sdist)}
    for kind, files in missing.items():
        for name in files:
            print(f'missing from the {kind}: {name}')
    if any(missing.values()):
        return 1
    print(f'{len(expected)} fixture and asset file(s) in both the wheel and the sdist')
    return 0


if __name__ == '__main__':
    sys.exit(main(Path(sys.argv[1] if len(sys.argv) > 1 else 'dist')))
