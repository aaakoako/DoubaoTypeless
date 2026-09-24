from tools.collect_runtime_notices import qt_binary_allowed


def test_unused_qt_plugins_do_not_enter_the_lgpl_runtime():
    for path in (
        'PySide6/Qt6VirtualKeyboard.dll',
        'PySide6/plugins/platforminputcontexts/qtvirtualkeyboardplugin.dll',
        'PySide6/plugins/imageformats/qpdf.dll',
        'PySide6/Qt6Pdf.dll', 'PySide6/Qt6Quick.dll', 'PySide6/Qt6Qml.dll',
    ):
        assert not qt_binary_allowed(path), path
    for path in (
        'PySide6/Qt6Core.dll', 'PySide6/Qt6Gui.dll', 'PySide6/Qt6Widgets.dll',
        'PySide6/Qt6Network.dll', 'PySide6/Qt6Svg.dll',
        'PySide6/plugins/platforms/qwindows.dll',
        'PySide6/plugins/imageformats/qjpeg.dll',
    ):
        assert qt_binary_allowed(path), path
