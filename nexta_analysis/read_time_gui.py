import os.path
import traceback
import tkinter
from tkinter import Tk, Menu, filedialog, Canvas, BOTH, Frame, messagebox, Label, StringVar, Entry
import queue
import sys
import json
import sigfig
import pathlib

import cv2

import led_selector
import read_time
from PIL import Image, ImageTk
import numpy as np
import threading
from auto_stretch.stretch import Stretch


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


class ReadTimeGUI:
    def __init__(self, master):
        self.__master = master
        self.__master.minsize(700, 400)
        self.__master.title('Exposure Timing Analysis')
        self.__master.protocol('WM_DELETE_WINDOW', self.__on_exit)

        self.__state = {
            'image': {'DATE-OBS': None, 'EXPTIME': None, 'date': None, 'path': None, 'data': None, 'working': None},
            'registration': {'path': None, 'name': None, 'data': None},
            'timinginfo': {'path': None, 'name': None, 'data': None}
        }
        self.work_queue = queue.Queue()
        self.gui_queue = queue.Queue()
        self.work_thread = threading.Thread(target=work_loop, args=(self.work_queue, self.gui_queue))
        self.work_thread.start()

        self.__setup_menu()
        self.__setup_statusbar()
        self.__setup_canvas()
        self.__master.after(50, self.__process_gui_queue)

    def __setup_menu(self):
        menubar = Menu(self.__master)
        # FILE
        self.filemenu = Menu(menubar, tearoff=0)
        self.filemenu.add_command(label="Open Image", command=self.__open_image)
        self.filemenu.add_command(label="Open Registration File", command=self.__open_registration)
        self.filemenu.add_separator()
        self.filemenu.add_command(label="Save Registration As", command=self.__save_registration,
                                  state=tkinter.DISABLED)
        self.filemenu.add_command(label="Save Timing As", command=self.__save_timing, state=tkinter.DISABLED)
        self.filemenu.add_separator()
        self.filemenu.add_command(label="Exit", command=self.__on_exit)
        menubar.add_cascade(label="File", menu=self.filemenu)
        # Action
        self.actionmenu = Menu(menubar, tearoff=0)
        self.actionmenu.add_command(label="Auto-register", command=self.__autoregister, state=tkinter.DISABLED)
        self.actionmenu.add_command(label="Manual-register", command=self.__manualregister, state=tkinter.DISABLED)
        self.actionmenu.add_command(label="Read Time", command=self.__readtime, state=tkinter.DISABLED)

        menubar.add_cascade(label="Action", menu=self.actionmenu)
        self.__master.config(menu=menubar)

    def __setup_canvas(self):
        def on_canvas_resize(event):
            nonlocal self
            self.run_in_gui(self.__update_image)

        self.__frame = Frame(self.__master)
        self.__frame.pack(fill=BOTH, expand=True)

        self.__canvas = Canvas(self.__frame, bg='pink')
        self.__canvas.pack(side=tkinter.LEFT, fill=tkinter.BOTH, expand=True)
        # self.__canvas.grid(row=0, column=0)
        self.__canvas.rowconfigure(0, weight=1)
        self.__on_canvas_resize = method_debounce(on_canvas_resize, .2)
        self.__canvas.bind('<Configure>', self.__on_canvas_resize)
        self.__frame2 = Frame(self.__frame, width=300)
        self.__frame2.pack(side=tkinter.RIGHT)
        self.__dateobs_strvar = StringVar()
        self.__headerdelta_strvar = StringVar()
        self.__shuttertype_strvar = StringVar()
        self.__rowreadout_strvar = StringVar()
        self.__firstrow_strvar = StringVar()
        self.__lastrow_strvar = StringVar()
        self.__fullread_strvar = StringVar()
        table = [['Header Start:', self.__dateobs_strvar],
                 ['Header Delta:', self.__headerdelta_strvar],
                 ['Shutter Type:', self.__shuttertype_strvar],
                 ['Row Time:', self.__rowreadout_strvar],
                 ['First Row:', self.__firstrow_strvar],
                 ['Last Row:', self.__lastrow_strvar],
                 ['Full Read:', self.__fullread_strvar]]
        for row_idx in range(len(table)):
            print(row_idx, table[row_idx])
            a = Label(self.__frame2, text=table[row_idx][0])
            a.grid(sticky=tkinter.W, row=row_idx, column=0)
            b = Entry(self.__frame2, textvariable=table[row_idx][1], state='readonly')
            b.grid(row=row_idx, column=1)

    def __clear_table(self):
        self.__dateobs_strvar.set('')
        self.__headerdelta_strvar.set('')
        self.__shuttertype_strvar.set('')
        self.__rowreadout_strvar.set('')
        self.__firstrow_strvar.set('')
        self.__lastrow_strvar.set('')
        self.__fullread_strvar.set('')
        self.__state['timinginfo'] = {'data': None, 'path': None, 'name': 'memory'}
        self.filemenu.entryconfig("Save Timing As", state=tkinter.DISABLED)

    def __setup_statusbar(self):
        self.__statusvar = StringVar()
        self.__statuslabel = Label(self.__master, textvariable=self.__statusvar, relief=tkinter.SUNKEN, anchor='w')
        self.__statuslabel.pack(side=tkinter.BOTTOM, fill=tkinter.X)

    def __set_statusbar(self, s):
        self.__statusvar.set(s)
        self.__statuslabel.update()

    def __on_exit(self):
        # TODO: Any saving warnings?
        self.gui_queue.put(('quit',))
        self.work_queue.put(('quit',))
        self.__master.destroy()

    def __open_image(self):
        def error(e):
            nonlocal self
            traceback.print_exception(e)
            self.__error_dialog('Failed to load image.')
            self.__set_statusbar('')

        f = filedialog.askopenfile(mode='rb', title="Open Image", filetypes=[("FITS files", '.fit .fits')])
        if f is not None:
            self.run_in_work(open_image, self.__set_imagedata, error, f)
            self.__set_statusbar("Loading Image...")

    def __open_registration(self):
        f = filedialog.askopenfile(mode='rb', title="Open Registration", filetypes=[("Registration files", '.etreg')])
        if f is not None:
            try:
                j = json.load(f)
                self.__update_overlay(j, self.__state['image']['data'], f.name)
            except Exception as e:
                traceback.print_exception(e)
                self.__error_dialog('Error loading registration file.')
            finally:
                f.close()

    def __save_timing(self):
        initialfile = None
        if self.__state['image']['name'] is not None and self.__state['image']['name'] != 'memory':
            initialfile = pathlib.Path(self.__state['image']['name']).stem
        f = tkinter.filedialog.asksaveasfile(initialfile=initialfile, title='Save Timing As',
                                             filetypes=[('Timing files', '.ettime')])
        if f is not None:
            try:
                json.dump(self.__state['timinginfo']['data'], f)
                self.__state['timinginfo']['path'] = f.name
                self.__state['timinginfo']['name'] = os.path.basename(f.name)
            finally:
                f.close()

    def __save_registration(self):
        f = tkinter.filedialog.asksaveasfile(title='Save Registration As', filetypes=[('Timing files', '.etreg')])
        if f is not None:
            try:
                json.dump(self.__state['registration']['data'], f)
                self.__state['registration']['path'] = f.name
                self.__state['registration']['name'] = os.path.basename(f.name)
            finally:
                f.close()

    def __update_overlay(self, reg_json, img, path):
        def error(e):
            traceback.print_exception(e)
            self.__state['registration'] = {'path': None, 'name': None, 'data': None}
            self.actionmenu.entryconfig('Read Time', state=tkinter.DISABLED)
            self.filemenu.entryconfig("Save Registration As", state=tkinter.DISABLED)
            self.__update_image()
            self.__error_dialog('Error loading registration file.')

        def success(w):
            self.__state['image']['working'] = w
            self.__state['registration'] = {'path': path, 'name': os.path.basename(path), 'data': reg_json}
            self.actionmenu.entryconfig('Read Time', state=tkinter.NORMAL)
            self.filemenu.entryconfig("Save Registration As", state=tkinter.NORMAL)
            self.__update_image()

        self.run_in_work(update_overlay, success, error, reg_json, img)

    def __update_image(self):
        if self.__state['image']['working'] is None:
            return
        self.__set_statusbar("Resizing to canvas...")
        cwidth = self.__canvas.winfo_width()
        cheight = self.__canvas.winfo_height()
        # print('D: ', self.__state['image']['working'].shape)
        img = Image.fromarray(self.__state['image']['working'], mode='RGB')
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
        self.__canvas.pack(fill=BOTH, expand=True)
        self.__set_statusbar('')

    def __error_dialog(self, message):
        tkinter.messagebox.showerror(title='Error', message=message)

    def __process_gui_queue(self):
        is_quit = False
        try:
            command = self.gui_queue.get(0)
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
                self.__master.after(50, self.__process_gui_queue)

    def __set_imagedata(self, data, working, dateobs, exptime, path):
        self.__clear_table()
        self.__state['image']['path'] = path
        self.__state['image']['name'] = os.path.basename(path)
        self.__master.title('Exposure Timing Analysis: ' + self.__state['image']['name'])
        self.__state['image']['DATE-OBS'] = dateobs
        self.__dateobs_strvar.set(dateobs)
        self.__state['image']['EXPTIME'] = exptime
        self.__state['image']['data'] = data
        self.__state['image']['working'] = working
        self.actionmenu.entryconfig('Auto-register', state=tkinter.NORMAL)
        self.actionmenu.entryconfig('Manual-register', state=tkinter.NORMAL)
        self.filemenu.entryconfig("Save Registration As", state=tkinter.DISABLED)
        if self.__state['registration']['data']:
            self.__update_overlay(self.__state['registration']['data'], data, self.__state['registration']['path'])
        else:
            self.__update_image()

    def __autoregister(self):
        def error(e):
            traceback.print_exception(e)
            self.__set_statusbar('')
            self.__error_dialog('Failed to auto register, you can try manual.')

        def success(points):
            self.__update_overlay(points, self.__state['image']['data'], 'memory')

        self.__set_statusbar('Running autoregister...')
        self.run_in_work(autoregister, success, error, self.__state['image']['data'])

    def __manualregister(self):
        tkinter.messagebox.showinfo(title='Manual Register',
                                    message='In the new window. outline one LED at a time. To close the outline, '
                                            'double clicking. Start with first seconds LEDs and move in order to 0.1ms '
                                            'leds. Press ESC to abort.')
        manual_roi_img = cv2.cvtColor(self.__state['image']['data'], cv2.COLOR_GRAY2BGR)
        manual_roi_img = cv2.resize(manual_roi_img, (0, 0), fx=self.__last_canvasscale, fy=self.__last_canvasscale)
        registration = led_selector.select_rois_easyroi_poly(manual_roi_img, self.__last_canvasscale)
        cv2.destroyAllWindows()
        self.__state['registration']['data'] = registration
        self.__update_overlay(registration, self.__state['image']['data'], 'memory')

    def __readtime(self):
        def error(e):
            traceback.print_exception(e)
            self.__set_statusbar('')
            self.__clear_table()
            self.__error_dialog('Failed to read time')

        def success(timinginfo):
            self.__set_statusbar('')
            self.__state['timinginfo'] = {'data': timinginfo, 'path': None, 'name': 'memory'}
            self.__headerdelta_strvar.set(str(sigfig.round(timinginfo['fits_delta'], 6)))
            self.__shuttertype_strvar.set(timinginfo['shutter_type'])
            self.__rowreadout_strvar.set(str(sigfig.round(timinginfo['rolling_shutter_row_time'], 6)))
            self.__firstrow_strvar.set(str(sigfig.round(timinginfo['calc_first_pixel'], 6)))
            self.__lastrow_strvar.set(str(sigfig.round(timinginfo['calc_last_pixel'], 6)))
            self.__fullread_strvar.set(str(sigfig.round(timinginfo['full_readout_time'], 6)))
            self.filemenu.entryconfig("Save Timing As", state=tkinter.NORMAL)

        self.__set_statusbar('Reading time...')
        self.run_in_work(readtime, success, error, self.__state['image']['data'], self.__state['registration']['data'],
                         self.__state['image']['DATE-OBS'], self.__state['image']['EXPTIME'])

    def set_status(self, message):
        self.run_in_gui(self.__set_statusbar, message)

    def run_in_work(self, work_method, successcb, errorcb, *args, **kwargs):
        self.work_queue.put((work_method, successcb, errorcb, args, kwargs))

    def run_in_gui(self, gui_method, *args, **kwargs):
        self.gui_queue.put((gui_method, args, kwargs))


def work_loop(work_queue, gui_queue):
    """
    :param work_queue: 0 - method, 1 - successcb, 2 - errorcb, 3 - args, 4 - kwargs
    :param gui_queue:
    :return:
    """
    command = ('',)
    errorcb = None
    while True:
        try:
            command = work_queue.get()
            args = []
            kwargs = {}
            successcb = None
            errorcb = None
            method = None
            if len(command) > 0:
                method = command[0]
            if len(command) > 1:
                successcb = command[1]
            if len(command) > 2:
                errorcb = command[2]
            if len(command) > 3:
                args = command[3]
            if len(command) > 4:
                kwargs = command[4]

            if method == 'quit':
                break
            ret = method(*args, **kwargs)
            if successcb:
                gui_queue.put((successcb, ret))
        except Exception as e:
            if errorcb is not None:
                gui_queue.put((errorcb, (e,)))
            else:
                traceback.print_exc()
        finally:
            errorcb = None
            if command[0] == 'quit':
                print('Quitting work loop.')
                return


def update_overlay(reg_json, img):
    if img is not None and reg_json is not None:
        w = np.array(
            cv2.cvtColor(
                led_selector.draw_ordered_led_polys(img, reg_json, 0.25),
                cv2.COLOR_BGR2RGB), dtype=np.uint8)
        return (w,)


def open_image(fileobj):
    try:
        img, dateobs, exptime = read_time.open_fits(fileobj)
        stretched_image = np.uint8(Stretch().stretch(img) * 255)
        working = np.array(cv2.cvtColor(stretched_image, cv2.COLOR_GRAY2RGB), dtype=np.uint8)
        return stretched_image, working, dateobs, exptime, fileobj.name
    finally:
        fileobj.close()


def autoregister(img):
    points = led_selector.find_ordered_LED_polypoints(img, 1.0, 0)
    return (points,)


def readtime(img, regjson, dateobs, exptime):
    return (read_time.readtime(img, regjson, dateobs, exptime),)


def main():
    root = Tk()
    rtgui = ReadTimeGUI(root)
    root.mainloop()


if __name__ == '__main__':
    sys.exit(main())
