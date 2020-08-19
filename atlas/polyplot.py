import os, sys
import numpy as np
from stl import mesh
import mpl_toolkits.mplot3d as a3
from matplotlib import pyplot
import matplotlib.colors as colors
import pylab as pl
import scipy as sp

ax = a3.Axes3D(pl.figure())
for i in range(10):
    vtx = np.random.rand(14,3)
    tri = a3.art3d.Poly3DCollection([vtx])
    tri.set_color(colors.rgb2hex(np.random.rand(3)))
    tri.set_edgecolor('k')
    ax.add_collection3d(tri)
pl.show()
