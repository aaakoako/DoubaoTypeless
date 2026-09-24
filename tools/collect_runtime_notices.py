"""Collect notices for discovered frozen modules, without embedding user settings."""
from importlib import metadata
import json
from pathlib import Path
import shutil
import sys
import re


def qt_binary_allowed(destination):
    name = Path(destination).name.lower()
    if name in {'qtvirtualkeyboardplugin.dll', 'qpdf.dll'}:
        return False
    if 'virtualkeyboard' in name or name in {'libqpdf.so', 'libqpdf.dylib'}:
        return False
    allowed = {'core', 'gui', 'widgets', 'network', 'svg', 'opengl', 'dbus', 'xcbqpa',
               'waylandclient', 'waylandeglclienthw'}
    match = re.match(r'libqt6(\w+)\.so(?:\.|$)', name)
    if match:
        return match[1] in allowed
    framework = re.search(r'/Qt(\w+)\.framework(?:/|$)', '/' + destination.replace('\\', '/'))
    if framework:
        return framework[1].lower() in allowed
    alias = re.fullmatch(r'Qt([A-Z]\w+)', Path(destination).name)
    if alias:
        return alias[1].lower() in allowed
    if name.startswith('qt6') and name.endswith('.dll'):
        return name in {'qt6core.dll','qt6gui.dll','qt6widgets.dll','qt6network.dll','qt6svg.dll','qt6opengl.dll'}
    return True


def collect(module_names, binary_destinations, root, output):
    output.mkdir(parents=True, exist_ok=True)
    mapping = metadata.packages_distributions()
    packages = {'PySide6','PySide6_Essentials','PySide6_Addons','shiboken6','pyinstaller'}
    for name in module_names:
        packages.update(mapping.get(name.split('.')[0], []))
    for name in binary_destinations:
        packages.update(mapping.get(name.replace('\\','/').split('/')[0], []))
    rows = []
    for name in sorted(packages, key=str.lower):
        dist = metadata.distribution(name)
        saved = []
        for item in dist.files or []:
            if not Path(item).name.upper().startswith(('LICENSE','COPYING','NOTICE')) or Path(item).suffix in {'.py','.pyc'}:
                continue
            source = Path(dist.locate_file(item))
            if not source.is_file():
                continue
            # Preserve the relative upstream paths, including vendored notices.
            relative = Path(name) / str(item).replace('../','').replace('..\\','')
            destination = output / relative
            if not destination.resolve().is_relative_to(output.resolve()):
                raise ValueError('Unsafe notice path')
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination); saved.append(relative.as_posix())
        rows.append({'name':name,'version':dist.version,
                     'license':dist.metadata.get('License-Expression') or dist.metadata.get('License'),
                     'project_urls':dist.metadata.get_all('Project-URL') or [],
                     'source_index':f'https://pypi.org/project/{name}/{dist.version}/#files',
                     'notices':saved})
    konva = root/'web/node_modules/konva'
    if konva.is_dir():
        info = json.loads((konva/'package.json').read_text(encoding='utf-8'))
        (output/'konva').mkdir(exist_ok=True)
        shutil.copy2(konva/'LICENSE',output/'konva/LICENSE')
        rows.append({'name':'konva','version':info['version'],'license':info['license'],
                     'source_index':'https://github.com/konvajs/konva','notices':['konva/LICENSE']})
    python_license = Path(sys.base_prefix)/'LICENSE.txt'
    if python_license.exists(): shutil.copy2(python_license,output/'PYTHON-LICENSE.txt')
    shutil.copytree(root/'docs/legal/licenses',output/'Qt-open-source',dirs_exist_ok=True)
    shutil.copy2(root/'THIRD_PARTY_NOTICES.md',output/'THIRD_PARTY_NOTICES.md')
    (output/'components.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
    return [(str(Path('licenses')/p.relative_to(output)),str(p),'DATA') for p in sorted(output.rglob('*')) if p.is_file()]
