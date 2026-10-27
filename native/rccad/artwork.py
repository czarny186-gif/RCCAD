"""Original HTML artwork rendered natively by Qt, including hover/active states."""
import json
from pathlib import Path
from PySide6.QtCore import Qt,QSize,QVariantAnimation,QEasingCurve
from PySide6.QtGui import QIcon,QPixmap,QPainter,QColor,QImage,QFont
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QToolButton,QGraphicsDropShadowEffect

ROOT=Path(__file__).parent/'assets'/'html'
CATALOG=json.loads((ROOT/'catalog.json').read_text(encoding='utf-8'))


def icon(name,color='#344e69',active=False):
    if name=='fileTool' and color=='#344e69':color='#222222'
    info=CATALOG['buttons'].get(name)
    if not info:return QIcon()
    if 'glyph' in info:
        image=QPixmap(96,96);image.fill(Qt.transparent);painter=QPainter(image);painter.setRenderHint(QPainter.Antialiasing)
        painter.setFont(QFont('Segoe UI',46));painter.setPen(QColor('white' if active else color));painter.drawText(image.rect(),Qt.AlignCenter,info['glyph']);painter.end();return QIcon(image)
    path=ROOT/info['file']
    if path.suffix=='.svg':
        svg=path.read_text().replace('currentColor','#ffffff' if active else color)
        image=QPixmap(96,96);image.fill(Qt.transparent);painter=QPainter(image)
        QSvgRenderer(svg.encode()).render(painter);painter.end()
    else:
        image=QPixmap(str(path))
        if name=='planesToggle':
            painter=QPainter(image);painter.setCompositionMode(QPainter.CompositionMode_SourceIn);painter.fillRect(image.rect(),QColor('white' if active else '#e53935'));painter.end()
            return QIcon(image)
        if active and name in ('boolTool','modTool','mirrorTool'):
            import numpy as np
            data=image.toImage().convertToFormat(QImage.Format_RGBA8888)
            pixels=np.frombuffer(data.bits(),dtype=np.uint8).reshape(data.height(),data.bytesPerLine())[:,:data.width()*4].reshape(data.height(),data.width(),4)
            gray=pixels[:,:,:3]@np.array([.2126,.7152,.0722]);value=np.clip(((255-gray)*2.6-127.5)*1.2+127.5,0,255).astype(np.uint8)
            pixels[:,:,:3]=value[:,:,None];return QIcon(QPixmap.fromImage(data))
        if active:
            data=image.toImage().convertToFormat(QImage.Format_ARGB32)
            data.invertPixels(QImage.InvertRgb);image=QPixmap.fromImage(data)
    return QIcon(image)


class HtmlButton(QToolButton):
    """HTML's 170 ms icon hover and 1.8 s active shadow pulse, using native Qt."""
    def __init__(self,name,parent=None,size=52):
        super().__init__(parent);self.artwork=name;self.is_small=size<=45;self.base_size=34 if name=='fileTool' else 36 if name=='mirrorTool' else 29 if name=='planesToggle' else 38 if size>45 else 27
        self.setFixedSize(size,size);self.setIconSize(QSize(self.base_size,self.base_size));self.setIcon(icon(name))
        if self.is_small:self.setStyleSheet('QToolButton:hover {background:#080808;color:white;border-color:#080808;}')
        self.setToolTip(CATALOG['buttons'].get(name,{}).get('title',name))
        self.shadow=QGraphicsDropShadowEffect(self);self.shadow.setOffset(0,3);self.shadow.setBlurRadius(12);self.shadow.setColor(QColor(56,81,107,36));self.setGraphicsEffect(self.shadow)
        self.hover_animation=QVariantAnimation(self);self.hover_animation.setDuration(150 if self.is_small else 170);self.hover_animation.setEasingCurve(QEasingCurve.OutCubic)
        self.hover_animation.valueChanged.connect(lambda v:self.setIconSize(QSize(round(v),round(v))))
        self.pulse=QVariantAnimation(self);self.pulse.setDuration(1800);self.pulse.setStartValue(12.);self.pulse.setKeyValueAt(.5,23.);self.pulse.setEndValue(12.);self.pulse.setLoopCount(-1)
        self.pulse.valueChanged.connect(self.shadow.setBlurRadius)
        self.toggled.connect(self.update_state)

    def update_state(self,checked):
        self.setIcon(icon(self.artwork,active=checked))
        if checked and self.isVisible() and self.artwork in ('newSketch','extrudeTool','boolTool'):self.pulse.start()
        else:self.pulse.stop();self.shadow.setBlurRadius(12)

    def enterEvent(self,event):
        self.hover_animation.stop();self.hover_animation.setStartValue(float(self.iconSize().width()));self.hover_animation.setEndValue(self.base_size*1.09);self.hover_animation.start()
        if not self.isChecked() and self.is_small:self.setIcon(icon(self.artwork,active=True))
        super().enterEvent(event)

    def leaveEvent(self,event):
        self.hover_animation.stop();self.hover_animation.setStartValue(float(self.iconSize().width()));self.hover_animation.setEndValue(float(self.base_size));self.hover_animation.start();self.setIcon(icon(self.artwork,active=self.isChecked()))
        super().leaveEvent(event)
