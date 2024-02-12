import queue
import time
import tkinter
import traceback

import cv2
import numpy as np

from NACanvas import NACanvas

windows = {}
gui_queue = None
root = None


def process_gui_queue():
    global gui_queue, root
    is_quit = False
    try:
        command = gui_queue.get(0)
        if command[0] == 'quit':
            is_quit = True
        else:
            args = []
            kwargs = {}
            method = command[0]
            if len(command) > 1:
                args = command[1]
            if len(command) > 2:
                kwargs = command[2]
            if args is not None:
                # print(args, kwargs)
                method(*args, **kwargs)
            else:
                method()
    except queue.Empty:
        pass
    except Exception as e:
        traceback.print_exc()
    finally:
        if not is_quit:
            if root:
                root.after(50, process_gui_queue)


def on_exit(name):
    global windows, root, gui_queue
    if name in windows:
        windows[name].destroy()
        del windows[name]
    # print('on_exit', windows.keys())
    if len(windows.keys()) == 0:
        root.destroy()
        gui_queue = None
        root = None


class ImageWindow:
    def __init__(self, parent, name, image, new_window=False, x_pos=0):
        self.__parent = parent
        self.__name = name
        if new_window:
            self.window = tkinter.Toplevel(parent)
            self.window.title(name)
        else:
            self.window = self.__parent
            self.window.title(name)
        self.__frame = tkinter.Frame(self.window)
        self.__frame.pack(fill=tkinter.BOTH, expand=True)
        self.__canvas = NACanvas(self, self.__frame)
        self.__canvas.set_image(normalize_image(image))
        self.run_in_gui(lambda: self.__canvas.refresh_canvas())

        def __on_exit():
            nonlocal name
            on_exit(name)

        self.window.protocol('WM_DELETE_WINDOW', __on_exit)
        self.window.geometry("+%d+%d" % (x_pos, x_pos))

    def destroy(self):
        self.window.destroy()

    @staticmethod
    def run_in_gui(gui_method, *args, **kwargs):
        global gui_queue
        gui_queue.put((gui_method, args, kwargs))

    def set_image(self, image):
        self.__canvas.set_image(image)
        self.__canvas.refresh_canvas()


def normalize_image(image):
    rimg = image.copy()
    if len(rimg.shape) < 3:
        rimg = np.array(cv2.cvtColor(rimg, cv2.COLOR_GRAY2RGB), dtype=np.uint8)
    else:
        rimg = np.array(cv2.cvtColor(rimg, cv2.COLOR_BGR2RGB), dtype=np.uint8)
    if rimg.dtype == np.bool_:
        rimg = np.uint8(rimg) * 255
    rmax = rimg.max()
    rmin = rimg.min()
    rimg = np.uint8(255 * ((rimg - rmin) / (rmax - rmin)))
    return rimg


def show(name, image):
    global windows, root, gui_queue
    if not root:
        root = tkinter.Tk()
        # root.overrideredirect(1)
        root.withdraw()
        gui_queue = queue.Queue()
        windows[name] = ImageWindow(root, name, image, True)
        root.after(250, process_gui_queue)
    else:
        if name in windows:
            w = windows[name]
            w.set_image(normalize_image(image))
        else:
            windows[name] = ImageWindow(root, name, image, True, len(windows.keys()) * 20)


def wait(wait_time=0):
    global root, windows
    if root:
        root.after(wait_time, lambda: root.destroy())
        root.mainloop()
        root = None



def main():
    # Quick way to test it.
    image = np.random.default_rng(int(time.time())).random((150, 200))
    show('test1', image)
    show('test2', image)
    wait(20000)


if __name__ == '__main__':
    main()
