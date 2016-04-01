import tkinter as tk
from tkinter.filedialog import askdirectory
from tkinter.messagebox import showwarning, showerror, showinfo
from tkinter import ttk
import logging
import sys
from threading import Thread

from spider_board.client import Browser
from spider_board.utils import time_job, LOG_FILE, get_logger, humansize


# Create the logging handlers and attach them
logger = get_logger(__name__, LOG_FILE)

stream_handler = logging.StreamHandler()
stream_handler.setLevel(logging.DEBUG)
logger.addHandler(stream_handler)


class Gui:
    def __init__(self):
        logger.info('Instantiating GUI')
        self.root = tk.Tk()
        self.browser = None
        self.make_gui()

    def make_gui(self):
        logger.info('Building GUI')
        self.main_frame = ttk.Frame(self.root)
        self.main_frame.pack(expand=True, fill=tk.BOTH, pady=10, padx=10)

        # Make the username label and box
        ttk.Label(self.main_frame, text='Username:').grid(row=0, column=2)

        self.username = tk.StringVar()
        self.username_box = ttk.Entry(self.main_frame, 
                textvariable=self.username)
        self.username_box.grid(row=0, column=3, sticky='nsew')

        # Make the password label and box
        ttk.Label(self.main_frame, text='Password:').grid(row=1, column=2)

        self.password = tk.StringVar()
        self.password_box = ttk.Entry(self.main_frame, 
                textvariable=self.password)
        self.password_box.grid(row=1, column=3, sticky='nsew')

        # Make the savefile label and box
        self.savefile_btn = ttk.Button(self.main_frame, text='Browse',
                command=self.ask_find_directory)
        self.savefile_btn.grid(row=2, column=2)

        self.savefile = tk.StringVar()
        self.savefile_box = ttk.Entry(self.main_frame, 
                textvariable=self.savefile)
        self.savefile_box.grid(row=2, column=3, sticky='nsew')

        # Set up the column weightings
        self.main_frame.columnconfigure(3, weight=1)
        self.main_frame.columnconfigure(0, weight=5)
        self.main_frame.rowconfigure(3, weight=1)

        # Make the listbox (and scrollbar) for selecting units
        self.unit_box = tk.Listbox(self.main_frame, relief=tk.SUNKEN, 
                selectmode=tk.EXTENDED)
        self.unit_box.grid(row=0, column=0, 
                rowspan=5, columnspan=2, 
                sticky='nsew')

        scrollbar = tk.Scrollbar(self.main_frame)
        scrollbar.config(command=self.unit_box.yview)
        self.unit_box.config(yscrollcommand=scrollbar.set)

        scrollbar.grid(row=0, column=1, rowspan=5, sticky='nsew')

        # Make the "login" button
        self.go_button = ttk.Button(self.main_frame, text='Login',
                command=self.login)
        self.go_button.grid(row=4, column=2, sticky='es')

        # Make the "start downloading" button
        self.go_button = ttk.Button(self.main_frame, text='Start Downloading',
                command=self.start_downloading)
        self.go_button.grid(row=4, column=3, sticky='es')

    def login(self):
        logger.info('Login button pressed')

        username = self.username.get()
        password = self.password.get()
        savefile = self.savefile.get()

        # Check all required fields are filled in
        if username and password and savefile:
            logger.info('Attempting login')
            self.browser = Browser(username, password, savefile)
            self.bootstrap_browser(self.browser)

            # Do the login in a different thread
            Thread(target=self.browser.login).start()
        else:
            showwarning('Ok', 'Please fill in all necessary fields.')
            logger.warn("Required fields haven't been filled in")


    def start_downloading(self):
        logger.info('Download button pressed')

        if self.browser and self.browser.is_logged_in:
            self.browser.spider_concurrent()
            self.browser.download_concurrent()
        else:
            logger.info('Not logged in')
            showerror('Ok', 'Not logged in')

    def ask_find_directory(self):
        save_location = askdirectory()
        self.savefile.set(save_location)

    def mainloop(self):
        self.root.mainloop()

    def quit(self):
        self.root.destroy()

    def update_units(self):
        self.unit_box.delete(0, tk.END)
        for unit in self.browser.units:
            self.unit_box.insert(tk.END, unit.title)

        self.root.after(1000, self.update_units)

    def bootstrap_browser(self, browser):
        """
        Add in any hooks to the browser so they will be run on certain events.
        """
        def on_quit(browser_instance, gui):
            """Close the GUI"""
            gui.quit()

        def on_login_successful(browser_instance, gui):
            """Fire off an info dialog and get units (in another thread)"""
            # Thread(target=browser_instance.get_units).start()
            gui.root.after(0, showinfo, 'Ok', 'Login Successful')

        def on_login_failed(browser_instance, gui):
            """Fire off an error dialog"""
            showerror('Ok', 'Login Unsuccessful')


        def on_get_units(browser_instance, gui):
            gui.root.after(0, gui.update_units)

        hooks = [on_quit, on_login_successful, on_login_failed,
                on_get_units]

        # Do the actual bootstrapping
        for hook in hooks:
            callback = lambda browser_instance: hook(browser_instance, self)
            setattr(browser, hook.__name__, callback)

        browser.on_login_failed(self)
