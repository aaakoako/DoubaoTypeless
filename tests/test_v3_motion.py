import pytest
pytest.importorskip('PySide6')
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication,QPlainTextEdit,QWidget,QPushButton
from doubao_typeless.ui.motion import InputFeedback,SurfacePulse,interface_motion
QT=None


def test_fire_does_not_intercept_editing_and_settles(monkeypatch):
    global QT
    QT=QApplication.instance() or QApplication([])
    now=[10.];host=QWidget();host.resize(420,190);editor=QPlainTextEdit(host);editor.setGeometry(10,10,400,170);host.show()
    feedback=InputFeedback(editor,clock=lambda:now[0]);feedback.set_tone('furious');QTest.qWait(30)
    try:
        assert feedback.isVisible() and feedback.timer.isActive()
        assert feedback.testAttribute(Qt.WA_TransparentForMouseEvents)
        QTest.mouseClick(editor.viewport(),Qt.LeftButton)
        QTest.keyClicks(editor,'still editable')
        assert editor.toPlainText()=='still editable'
        first=feedback.grab().toImage();now[0]+=.4;feedback._refresh();QTest.qWait(20)
        assert feedback.grab().toImage()!=first
        now[0]+=5;feedback._refresh();assert not feedback.timer.isActive()
        feedback.configure(False);assert not feedback.isVisible()
    finally:host.close();host.deleteLater();QTest.qWait(10)


def test_in_app_motion_switch_controls_the_easter_egg(monkeypatch):
    global QT
    QT=QApplication.instance() or QApplication([])
    host=QWidget();editor=QPlainTextEdit(host);host.show();feedback=InputFeedback(editor)
    try:
        feedback.configure(True);feedback.set_tone('angry');feedback.pulse()
        assert feedback.isVisible() and feedback.timer.isActive()
        feedback.configure(False)
        assert not feedback.isVisible() and not feedback.timer.isActive()
    finally:host.close();host.deleteLater();QTest.qWait(10)


def test_button_ripple_preserves_clicks_and_stops_when_disabled():
    global QT
    QT=QApplication.instance() or QApplication([])
    motion=interface_motion();motion.configure(True)
    host=QWidget();button=QPushButton('插入并复制',host);host.show();clicked=[]
    button.clicked.connect(lambda:clicked.append(True));QTest.qWait(20)
    try:
        original=button.geometry()
        QTest.mouseClick(button,Qt.LeftButton);QTest.mouseClick(button,Qt.LeftButton)
        assert len(clicked)==2 and button.geometry()==original
        pulses=button.findChildren(SurfacePulse)
        assert any(p.isVisible() for p in pulses)
        assert all(p.testAttribute(Qt.WA_TransparentForMouseEvents) for p in pulses)
        motion.configure(False)
        assert all(not p.isVisible() and not p.timer.isActive() for p in pulses)
        QTest.mouseClick(button,Qt.LeftButton);assert len(clicked)==3
    finally:
        host.close();host.deleteLater();QTest.qWait(10);motion.configure(True)
