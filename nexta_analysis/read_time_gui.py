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
import json
import os.path
import pathlib
import queue
import sys
import threading
import tkinter
import traceback
from tkinter import Tk, Menu, filedialog, BOTH, Frame, messagebox, Label, StringVar, Entry

import cv2
import numpy as np
import sigfig
from auto_stretch.stretch import Stretch

import led_selector
import read_time
from NACanvas import NACanvas


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
        # Help
        self.helpmenu = Menu(menubar, tearoff=0)
        self.helpmenu.add_command(label="Help", command=self.__help, state=tkinter.NORMAL)
        self.helpmenu.add_command(label="About", command=self.__about, state=tkinter.NORMAL)

        menubar.add_cascade(label="Help", menu=self.helpmenu)

        self.__master.config(menu=menubar)

    def __setup_canvas(self):

        self.__frame = Frame(self.__master)
        self.__frame.pack(fill=BOTH, expand=True)

        self.__canvas = NACanvas(self, self.__frame)
        self.__canvas.bind('<ROISDone>', self.__on_rois_done)
        self.__canvas.bind('<ROIAbort>', self.__on_rois_abort)
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

        f = filedialog.askopenfile(mode='rb', title="Open Image", filetypes=[("FITS files", '.fit .fits'), ("All files", '.*')])
        if f is not None:
            self.run_in_work(open_image, self.__set_imagedata, error, f)
            self.__set_statusbar("Loading Image...")

    def __open_registration(self):
        f = filedialog.askopenfile(mode='rb', title="Open Registration", filetypes=[("Registration files", '.etreg'), ("All files", '.*')])
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

    def __clear_registration(self):
        self.__state['registration'] = {'path': None, 'name': None, 'data': None}
        if self.__state['image']['data'] is not None:
            self.__state['image']['working'] = np.array(cv2.cvtColor(self.__state['image']['data'], cv2.COLOR_GRAY2RGB),
                                                        dtype=np.uint8)
            self.__canvas.set_image(self.__state['image']['working'])
            self.__update_image()


    def __update_overlay(self, reg_json, img, path):
        def error(e):
            traceback.print_exception(e)
            self.__clear_registration()
            self.actionmenu.entryconfig('Read Time', state=tkinter.DISABLED)
            self.filemenu.entryconfig("Save Registration As", state=tkinter.DISABLED)
            self.__error_dialog('Error loading registration file.')

        def success(w):
            self.__state['image']['working'] = w
            self.__canvas.set_image(w)
            self.__state['registration'] = {'path': path, 'name': os.path.basename(path), 'data': reg_json}
            self.actionmenu.entryconfig('Read Time', state=tkinter.NORMAL)
            self.filemenu.entryconfig("Save Registration As", state=tkinter.NORMAL)
            self.__update_image()

        self.run_in_work(update_overlay, success, error, reg_json, img)

    def __update_image(self):
        if self.__state['image']['working'] is None:
            return
        self.__set_statusbar("Resizing to canvas...")
        self.__canvas.refresh_canvas()
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
        self.__canvas.set_image(working)
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

    def __on_rois_done(self, polygons):
        self.__state['registration']['data'] = polygons
        self.__update_overlay(polygons, self.__state['image']['data'], 'memory')

    def __on_rois_abort(self):
        self.__set_statusbar('')

    def __help(self):
        tkinter.messagebox.showinfo(title='Help',
                                    message='For users guides, and instructional videos visit.\nhttps://starsynctrackers.com/learn/nexta\n'
                                            'To file bug reports goto:\nhttps://github.com/bluthen/exposure_timing/issues')

    def __about(self):
        tkinter.messagebox.showinfo(title='About',
                                    message='Exposure Timing Analysis Software\n'
                                            'Version 1.1.0\n'
                                            'Copyright (c) 2024 Russell Valentine\n'
                                            'based on the paper:\n\n'
                                            'Kamiński, K., Weber, C., Marciniak, A., Żołnowski, M., & Gędek, M. (2023).\n'
                                             'Reaching sub-millisecond accuracy in stellar occultations and artificial\n'
                                             'satellites tracking. arXiv. https://doi.org/10.48550/ARXIV.2301.06378')

    def __manualregister(self):
        self.__clear_registration()
        self.__canvas.set_roi_mode(True)
        tkinter.messagebox.showinfo(title='Manual Register',
                                    message='Outline one LED at a time. '
                                            'To close the outline, right click. '
                                            'Start with the first "seconds" LEDs and move in order to the 0.1ms LEDs. '
                                            'Press ESC key to abort.')
        self.__set_statusbar('ROI Mode| Select polygons')

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


def main_cli():
    import argparse
    parser = argparse.ArgumentParser(
        prog="Read Time",
        description="Tool to read exposure timing information."
    )
    subparsers = parser.add_subparsers(title="subcommands",
                                       dest="subparser",
                                       description="Run without any subcommands to run GUI.")
    regparser = subparsers.add_parser('registration', help="Generate registration file for reading")
    led_selector.add_parser_args(regparser)
    readtime_parser = subparsers.add_parser('readtime', help="Read time info from image.")
    read_time.add_parser_args(readtime_parser)
    args = parser.parse_args()
    if args.subparser == 'registration':
        led_selector.main(args)
    elif args.subparser == 'readtime':
        read_time.main(args)
    else:
        main()


if __name__ == '__main__':
    sys.exit(main_cli())
