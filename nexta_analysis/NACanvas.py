# Exposure Timing - NEXTA Analysis
# Copyright (C) 2024 Russell Valentine
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
import threading
import tkinter
import typing
from tkinter import Canvas

import numpy as np
from PIL import Image, ImageTk

WORKING_COLOR = "#00FF00"
WORKING_WIDTH = 2
POLY_COLOR = WORKING_COLOR
POLY_WIDTH = WORKING_WIDTH


def method_debounce(method, wait):
    timer: None | threading.Timer = None

    def debounced(*args, **kwargs):
        nonlocal timer, method, wait
        if timer:
            timer.cancel()
            timer = None
        timer = threading.Timer(wait, method, args, kwargs)
        timer.start()

    return debounced


class NACanvas:
    """
    It is expected that any function call on the object is from the GUI Thread.
    """

    def __init__(self, rt, parent):
        self.rt = rt
        self.__image: typing.Any(None, np.ndarray) = None
        self.__parent = parent
        self.__last_canvasscale = 1.0
        self.__mode = 'view'
        self.__polygons = []
        self.__working_poly = []  # Current working Polygon
        self.__event_listeners = {
            '<ROISDone>': [],
            '<ROIAbort>': []
        }

        def on_canvas_resize(event):
            nonlocal self
            self.rt.run_in_gui(self.refresh_canvas)

        self.__canvas = Canvas(self.__parent, bg='pink')
        self.__canvas.pack(side=tkinter.LEFT, fill=tkinter.BOTH, expand=True)
        self.__canvas.rowconfigure(0, weight=1)
        self.__on_canvas_resize = method_debounce(on_canvas_resize, .2)
        self.__canvas.bind('<Configure>', self.__on_canvas_resize)
        self.__canvas.bind('<Motion>', self.on_motion)
        self.__canvas.bind('<ButtonRelease-1>', self.on_button1_release)
        self.__canvas.bind('<ButtonRelease-3>', self.on_button3_release)
        self.__canvas.bind_all('<KeyPress-Escape>', self.on_key_esc)

    def __call(self, event, *args):
        for cb in self.__event_listeners[event]:
            cb(*args)

    def on_key_esc(self, event=None):
        # print('Escape pressed')
        if self.__mode == 'roi':
            self.__working_poly = []
            self.__polygons = []
            self.__mode = 'view'
            self.refresh_canvas()
            self.__call('<ROIAbort>')

    def on_motion(self, event):
        if self.__mode != 'roi':
            return
        l = len(self.__working_poly)
        if l > 0:
            s = self.__last_canvasscale
            self.__working_poly[l - 1] = [int(event.x / s), int(event.y / s)]
            # print('on_motion', self.__working_poly[l - 1], event.x, event.y)
            self.draw_working_lastline()

    def on_button1_release(self, event):
        # print('Release', event.x, event.y)
        if self.__mode != 'roi':
            return
        l = len(self.__working_poly)
        s = self.__last_canvasscale
        if l > 0:
            self.__working_poly[l - 1] = [int(event.x / s), int(event.y / s)]
        else:
            self.__working_poly.append([int(event.x / s), int(event.y / s)])
        self.__working_poly.append([int(event.x / s), int(event.y / s)])
        self.draw_working_polygon()

    def on_button3_release(self, event):
        if self.__mode != 'roi':
            return
        if len(self.__working_poly) <= 3:
            return
        del self.__working_poly[-1]
        self.__polygons.append(self.__working_poly)
        self.__working_poly = []
        self.draw_polygons()
        if len(self.__polygons) == 20:
            # We are done.
            polygons = self.__polygons
            self.__polygons = []
            self.__canvas.delete('polygons')
            self.__mode = 'view'
            self.__call('<ROISDone>', polygons)

    def set_roi_mode(self, enabled):
        if enabled:
            self.__mode = 'roi'
        elif not enabled and self.__mode == 'roi':
            self.on_key_esc()

    def set_image(self, img):
        self.__image = img

    def draw_polygons(self):
        self.__canvas.delete('polygons')
        if self.__mode != 'roi':
            return
        s = self.__last_canvasscale
        for polygon in self.__polygons:
            adj_poly = np.array(s * np.array(polygon).flatten(), dtype=np.uint32).tolist()
            p = self.__canvas.create_polygon(np.array(adj_poly).flatten().tolist(), outline=POLY_COLOR, width=POLY_WIDTH, fill='')
            self.__canvas.itemconfig(p, tags=('polygons',))
        self.draw_working_polygon()

    def draw_working_lastline(self):
        self.__canvas.delete('lastline')
        if self.__mode != 'roi':
            return
        # Now our current working partial polygon
        l = len(self.__working_poly)
        if l > 1:
            s = self.__last_canvasscale
            p1 = self.__working_poly[l - 2]
            p2 = self.__working_poly[l - 1]
            points = np.array(s * np.array([p1, p2]).flatten(), dtype=np.uint32).tolist()
            # print('dwll', points)
            l = self.__canvas.create_line(*points, width=WORKING_WIDTH, fill=WORKING_COLOR)
            tags = ('polygons', 'working', 'lastline')
            self.__canvas.itemconfig(l, tags=tags)

    def draw_working_polygon(self):
        self.__canvas.delete('working')
        if self.__mode != 'roi':
            return
        s = self.__last_canvasscale
        # Now our current working partial polygon
        for idx in range(1, len(self.__working_poly)):
            # print('draw_working_polygon', len(self.__working_poly), idx)
            p1 = self.__working_poly[idx - 1]
            p2 = self.__working_poly[idx]
            points = np.array(s * np.array([p1, p2]).flatten(), dtype=np.uint32).tolist()
            l = self.__canvas.create_line(*points, fill=WORKING_COLOR, width=WORKING_WIDTH)
            tags = ('polygons', 'working')
            if idx == len(self.__working_poly) - 1:
                tags = ('polygons', 'working', 'lastline')
            self.__canvas.itemconfig(l, tags=tags)

    def draw_refresh_canvas(self):
        self.draw_polygons()
        self.draw_working_polygon()

    def refresh_canvas(self):
        if self.__image is None:
            return
        cwidth = self.__canvas.winfo_width()
        cheight = self.__canvas.winfo_height()
        # print('D: ', self.__state['image']['working'].shape)
        img = Image.fromarray(self.__image, mode='RGB')
        isize = img.size
        wscale = cwidth / isize[0]
        hscale = cheight / isize[1]
        s = min([wscale, hscale])
        self.__last_canvasscale = s
        img = img.resize((int(s * isize[0]), int(s * isize[1])), Image.BICUBIC)
        # print(img.size)
        image = ImageTk.PhotoImage(image=img)
        self.__canvas.delete('all')
        self.__canvas.image = image
        self.__canvas.create_image(0, 0, anchor='nw', image=image)
        self.draw_polygons()
        self.__canvas.pack(fill=tkinter.BOTH, expand=True)

    def bind(self, event, cb):
        if event not in self.__event_listeners:
            raise Exception('Invalid event: ', event)
        self.__event_listeners[event].append(cb)
