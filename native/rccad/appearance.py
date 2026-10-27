"""Procedural artwork copied from RCCAD HTML: gradient and adaptive sketch grid."""
import numpy as np
import pyqtgraph as pg
import pyqtgraph.opengl as gl
from pyqtgraph.opengl import shaders
from pyqtgraph.opengl.GLGraphicsItem import GLGraphicsItem
from OpenGL import GL


class HtmlBackground(gl.GLMeshItem):
    def __init__(self):
        if 'rccad-background' not in shaders.ShaderProgram.names:
            shaders.ShaderProgram('rccad-background',[
                shaders.VertexShader('''attribute vec4 a_position; attribute vec4 a_color; varying vec4 v_color;
                void main(){v_color=a_color;gl_Position=vec4(a_position.xy,0.999999,1.0);}'''),
                shaders.FragmentShader('''#ifdef GL_ES
                precision mediump float;
                #endif
                varying vec4 v_color; void main(){gl_FragColor=v_color;}''')])
        top=np.array([249,251,254,255])/255;bottom=np.array([228,237,247,255])/255
        super().__init__(vertexes=np.array([[-1,-1,0],[1,-1,0],[1,1,0],[-1,1,0]],dtype=float),faces=np.array([[0,1,2],[0,2,3]]),vertexColors=np.array([bottom,bottom,top,top]),smooth=False,shader='rccad-background',computeNormals=False)
        self.setDepthValue(-1000000);self.setGLOptions({GL.GL_DEPTH_TEST:False,GL.GL_BLEND:False,GL.GL_CULL_FACE:False})
    def paint(self):
        GL.glDepthMask(False)
        try:super().paint()
        finally:GL.glDepthMask(True);GL.glEnable(GL.GL_DEPTH_TEST)


class HtmlGrid(GLGraphicsItem):
    def __init__(self):
        super().__init__();self.half=120;self.step=None
        self.major=gl.GLLinePlotItem(parentItem=self,mode='lines',color=pg.mkColor('#b3c7da'),width=1.1,antialias=True)
        self.minor=gl.GLLinePlotItem(parentItem=self,mode='lines',color=pg.mkColor('#d9e4ee'),width=.65,antialias=True)
        self.border=gl.GLLinePlotItem(parentItem=self,color=pg.mkColor('#9eb6cc'),width=1.2,antialias=True)
        self.rebuild(120,5)
    def rebuild(self,half,step):
        if half==self.half and step==self.step:return
        self.half,self.step=half,step;major=[];minor=[];count=min(600,int(round(half/step)))
        for i in range(-count,count+1):
            value=i*step;group=major if abs(value/10-round(value/10))<1e-6 else minor
            group.extend([(value,-half,0),(value,half,0),(-half,value,0),(half,value,0)])
        self.major.setData(pos=np.array(major,dtype=float).reshape(-1,3));self.minor.setData(pos=np.array(minor,dtype=float).reshape(-1,3))
        self.border.setData(pos=np.array([[-half,-half,0],[half,-half,0],[half,half,0],[-half,half,0],[-half,-half,0]],dtype=float))
