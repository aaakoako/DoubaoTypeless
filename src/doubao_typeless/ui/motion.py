"""Small input feedback, painted at the border without intercepting input."""
import math
import time
from PySide6.QtCore import Qt,QEvent,QTimer,QRectF,QObject
from PySide6.QtGui import QColor,QPainter,QPainterPath,QPen,QLinearGradient
from PySide6.QtWidgets import QWidget,QApplication,QAbstractButton,QTabBar


class InputFeedback(QWidget):
    def __init__(self,target,clock=time.monotonic):
        super().__init__(target.parentWidget() or target)
        self.target=target;self.margin=10
        self._clock=clock;self.enabled=True;self.tone='';self.activity_until=0.;self.fire_until=0.
        self.setAttribute(Qt.WA_TransparentForMouseEvents,True)
        self.setAttribute(Qt.WA_NoSystemBackground,True)
        self.setFocusPolicy(Qt.NoFocus)
        target.installEventFilter(self)
        self.timer=QTimer(self);self.timer.setInterval(33);self.timer.timeout.connect(self._refresh)
        self._position();self.hide()

    def _position(self):
        parent=self.target.parentWidget() or self.target
        if self.parentWidget()!=parent:self.setParent(parent)
        rect=self.target.geometry() if parent!=self.target else self.target.rect()
        self.setGeometry(rect.adjusted(-self.margin,-self.margin,self.margin,self.margin))

    def eventFilter(self,target,event):
        if event.type() in {QEvent.Resize,QEvent.Move,QEvent.ParentChange}:self._position()
        elif event.type()==QEvent.Show:self._refresh()
        elif event.type()==QEvent.Hide:self.timer.stop();self.hide()
        return False

    def configure(self,enabled):
        self.enabled=bool(enabled);self._refresh()

    def set_tone(self,tone):
        if tone!=self.tone:
            self.tone=tone
            self.fire_until=self._clock()+4 if tone in {'angry','furious'} else 0.
        self._refresh()

    def pulse(self):
        self.activity_until=self._clock()+1.4;self._refresh()

    def _refresh(self):
        now=self._clock()
        visible=self.enabled and self.target.isVisible() and (
            self.tone in {'angry','furious'} or now<self.activity_until)
        self.setVisible(visible)
        moving=visible and (now<self.fire_until or now<self.activity_until)
        if moving and not self.timer.isActive():self.timer.start()
        if not moving:self.timer.stop()
        if visible:self.raise_();self.update()

    def paintEvent(self,event):
        painter=QPainter(self);painter.setRenderHint(QPainter.Antialiasing)
        now=self._clock();fire=self.tone in {'angry','furious'}
        phase=now*3.8 if now<self.fire_until or not fire else 0.
        color=QColor('#e86735' if fire else '#7161ef')
        color.setAlpha(115+int(35*math.sin(phase)) if self.timer.isActive() else 90)
        painter.setPen(QPen(color,2));painter.setBrush(Qt.NoBrush)
        m=self.margin
        painter.drawRoundedRect(QRectF(m-1,m-1,self.width()-2*m+2,self.height()-2*m+2),8,8)
        if not fire:return
        # Limit all flame pixels to the outer rail: the editable center remains clear.
        outer=QPainterPath();outer.addRect(QRectF(self.rect()))
        inner=QPainterPath();inner.addRect(QRectF(m,m,max(0,self.width()-2*m),max(0,self.height()-2*m)))
        painter.setClipPath(outer.subtracted(inner))
        gradient=QLinearGradient(0,self.height(),0,self.height()-15)
        gradient.setColorAt(0,QColor('#e65b35'));gradient.setColorAt(1,QColor('#ffc278'))
        painter.setBrush(gradient);painter.setPen(Qt.NoPen)
        count=max(4,self.width()//38)
        for i in range(count):
            x=12+i*(self.width()-24)/max(1,count-1)
            h=(6 if self.tone=='angry' else 8)+2*math.sin(phase+i*2.3)
            y=self.height()-1;lean=2*math.sin(phase*1.2+i)
            path=QPainterPath();path.moveTo(x-3,y)
            path.cubicTo(x-6,y-h*.4,x-2,y-h*.48,x+lean,y-h)
            path.cubicTo(x+4+lean,y-h*.5,x,y-h*.6,x+3,y-h*.2)
            path.cubicTo(x+4,y,x+1,y+1,x-3,y)
            painter.setBrush(gradient);painter.drawPath(path)
            core=QPainterPath();core.moveTo(x-1.5,y)
            core.quadTo(x-2,y-h*.25,x+.5,y-h*.55)
            core.quadTo(x+3,y-1,x+1.5,y);core.closeSubpath()
            painter.setBrush(QColor('#ffe6a3'));painter.drawPath(core)


class SurfacePulse(QWidget):
    """A short visual overlay: no layout changes, mouse capture or focus changes."""
    def __init__(self,target,point=None):
        super().__init__(target)
        self.setAttribute(Qt.WA_TransparentForMouseEvents,True)
        self.setAttribute(Qt.WA_NoSystemBackground,True)
        self.setFocusPolicy(Qt.NoFocus)
        self.started=time.monotonic();self.point=point
        self.duration=.42 if point is not None else .5
        target.installEventFilter(self)
        self.setGeometry(target.rect());self.show();self.raise_()
        self.timer=QTimer(self);self.timer.setInterval(16);self.timer.timeout.connect(self.tick);self.timer.start()

    def eventFilter(self, target, event):
        if event.type() == QEvent.Resize:
            self.setGeometry(target.rect())
        return False

    def tick(self):
        if time.monotonic()-self.started>=self.duration or not self.isVisible():
            self.finish();return
        self.update()

    def finish(self):
        self.timer.stop();self.hide();self.deleteLater()

    def paintEvent(self,event):
        t=min(1,(time.monotonic()-self.started)/self.duration)
        painter=QPainter(self);painter.setRenderHint(QPainter.Antialiasing)
        clip=QPainterPath();clip.addRoundedRect(QRectF(self.rect()),8,8);painter.setClipPath(clip)
        if self.point is not None:
            color=QColor('#a99cff');color.setAlpha(int(68*(1-t)))
            painter.setPen(Qt.NoPen);painter.setBrush(color)
            radius=max(self.width(),self.height())*(1-(1-t)**3)
            painter.drawEllipse(self.point,radius,radius)
        else:
            # Light travels along the frame; the content never fades or moves.
            gradient=QLinearGradient(-self.width()+t*self.width()*3,0,t*self.width()*3,self.height())
            clear=QColor('#8975ff');clear.setAlpha(0)
            bright=QColor('#8975ff');bright.setAlpha(int(150*(1-t)))
            gradient.setColorAt(0,clear);gradient.setColorAt(.5,bright);gradient.setColorAt(1,clear)
            painter.setPen(QPen(gradient,3));painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(QRectF(self.rect()).adjusted(2,2,-2,-2),9,9)


class InterfaceMotion(QObject):
    def __init__(self,app):
        super().__init__(app);self.enabled=True;app.installEventFilter(self)

    def configure(self,enabled):
        self.enabled=bool(enabled)
        if not self.enabled:
            for widget in QApplication.allWidgets():
                if isinstance(widget,SurfacePulse):widget.finish()

    def eventFilter(self,target,event):
        if not self.enabled or not isinstance(target,QWidget):return False
        if event.type()==QEvent.MouseButtonPress and event.button()==Qt.LeftButton:
            if isinstance(target,(QAbstractButton,QTabBar)) and target.isEnabled():
                for child in target.findChildren(SurfacePulse):child.finish()
                SurfacePulse(target,event.position())
        elif event.type()==QEvent.Show and target.objectName() in {'hudWindow','appWindow'}:
            SurfacePulse(target)
        return False


def interface_motion():
    app=QApplication.instance()
    if not hasattr(app,'_interface_motion'):app._interface_motion=InterfaceMotion(app)
    return app._interface_motion


class ActivityIndicator(QWidget):
    def __init__(self,parent=None):
        super().__init__(parent);self.setFixedSize(26,18)
        self.setToolTip('文字正在输入或同步；不代表正在录音。')
        self.active=False;self.enabled=True
        self.hide()
        self.timer=QTimer(self);self.timer.setInterval(40);self.timer.timeout.connect(self.update)
    def set_active(self,active,enabled=True):
        self.active=bool(active);self.enabled=bool(enabled)
        self.setVisible(self.active)
        if self.active and self.enabled and self.isVisible():self.timer.start()
        else:self.timer.stop()
        self.update()
    def hideEvent(self,event):self.timer.stop();super().hideEvent(event)
    def paintEvent(self,event):
        painter=QPainter(self);painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen);painter.setBrush(QColor('#7161ef'))
        phase=time.monotonic()*5 if self.enabled else 0
        for i in range(4):
            height=5+(1+math.sin(phase+i*.9))*4
            painter.drawRoundedRect(QRectF(2+i*6,(18-height)/2,3,height),1.5,1.5)
