"""Package native preview artifacts, checksums and source-bound metadata."""
import hashlib
import json
import platform
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    info = json.loads((ROOT / 'build-info.json').read_text())
    sha = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    if info['source_sha'] != sha or subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True).strip():
        raise RuntimeError('Package must match a clean source commit')
    system = 'macos' if sys.platform == 'darwin' else 'linux'
    arch = {'x86_64': 'x64', 'arm64': 'arm64', 'aarch64': 'arm64'}[platform.machine()]
    output = ROOT / 'release-posix'
    output.mkdir(exist_ok=True)
    name = f'PocketComposer_{info["version"]}_{system}_{arch}'
    payload_root = ROOT / ('dist/Pocket Composer.app' if system == 'macos' else 'dist/PocketComposer')
    broken = [str(p.relative_to(payload_root)) for p in payload_root.rglob('*') if p.is_symlink() and not p.exists()]
    if broken:
        raise RuntimeError('Broken packaged library links: ' + ', '.join(broken))
    if system == 'macos':
        app = ROOT / 'dist/Pocket Composer.app'
        stage = ROOT / 'build/dmg'
        stage.mkdir(parents=True, exist_ok=True)
        subprocess.run(['ditto', str(app), str(stage / app.name)], check=True)
        (stage / 'Applications').symlink_to('/Applications', target_is_directory=True)
        shutil.copy2(ROOT / 'docs/release/CROSS_PLATFORM.md', stage / 'README.md')
        subprocess.run(['hdiutil', 'create', '-volname', 'Pocket Composer', '-srcfolder', str(stage),
                        '-ov', '-format', 'UDZO', str(output / (name + '.dmg'))], check=True)
    else:
        payload = ROOT / 'dist/PocketComposer'
        shutil.copy2(ROOT / 'docs/release/CROSS_PLATFORM.md', payload / 'README.md')
        with tarfile.open(output / (name + '.tar.gz'), 'w:gz') as archive:
            archive.add(payload, arcname='PocketComposer')
        deb = ROOT / 'build/deb'
        target = deb / 'opt/pocket-composer'
        shutil.copytree(payload, target, symlinks=True)
        control = deb / 'DEBIAN'
        control.mkdir()
        (control / 'control').write_text(f'''Package: pocket-composer
Version: {info['version']}
Architecture: amd64
Maintainer: Pocket Composer contributors
Depends: libatspi2.0-0, libegl1, libgl1, libxcb-cursor0, libxkbcommon-x11-0, libxcb-icccm4, libxcb-image0, libxcb-keysyms1, libxcb-render-util0, libxcb-xinerama0, libxcb-randr0, libxcb-shape0, libxcb-xfixes0, libxcb-sync1
Recommends: gnome-keyring, at-spi2-core
Description: Phone-to-desktop text and image composer (X11 preview)
''')
        launchers = deb / 'usr/share/applications'
        launchers.mkdir(parents=True)
        (launchers / 'pocket-composer.desktop').write_text('''[Desktop Entry]
Type=Application
Name=Pocket Composer
Comment=Compose on your phone, insert on your desktop
Exec=/opt/pocket-composer/PocketComposer
Icon=/opt/pocket-composer/_internal/assets/icon.png
Terminal=false
Categories=Utility;
''')
        subprocess.run(['dpkg-deb', '--root-owner-group', '--build', str(deb), str(output / (name + '.deb'))], check=True)
    artifacts = []
    for path in sorted(output.iterdir()):
        if path.suffix not in {'.dmg', '.gz', '.deb'}:
            continue
        artifacts.append({'name': path.name, 'size': path.stat().st_size,
                          'sha256': hashlib.file_digest(path.open('rb'), 'sha256').hexdigest()})
    (output / 'SHA256SUMS.txt').write_text(''.join(f'{a["sha256"]}  {a["name"]}\n' for a in artifacts))
    (output / 'build.json').write_text(json.dumps({**info, 'os': system, 'arch': arch,
        'signed_by_developer': False, 'artifacts': artifacts}, indent=2))


if __name__ == '__main__':
    main()
