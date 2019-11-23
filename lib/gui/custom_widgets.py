#!/usr/bin/env python3
""" Custom widgets for Faceswap GUI """

import logging
import platform
import re
import sys
import tkinter as tk
from tkinter import ttk, TclError

from .utils import get_config

logger = logging.getLogger(__name__)  # pylint: disable=invalid-name


class ContextMenu(tk.Menu):  # pylint: disable=too-many-ancestors
    """ A Pop up menu to be triggered when right clicking on widgets that this menu has been
    applied to.

    This widget provides a simple right click pop up menu to the widget passed in with `Cut`,
    `Copy`, `Paste` and `Select all` menu items.

    Parameters
    ----------
    widget: tkinter object
        The widget to apply the :class:`ContextMenu` to

    Example
    -------
    >>> text_box = ttk.Entry(parent)
    >>> text_box.pack()
    >>> right_click_menu = ContextMenu(text_box)
    >>> right_click_menu.cm_bind()
    """
    def __init__(self, widget):
        logger.debug("Initializing %s: (widget_class: '%s')",
                     self.__class__.__name__, widget.winfo_class())
        super().__init__(tearoff=0)
        self._widget = widget
        self._standard_actions()
        logger.debug("Initialized %s", self.__class__.__name__)

    def _standard_actions(self):
        """ Standard menu actions """
        self.add_command(label="Cut", command=lambda: self._widget.event_generate("<<Cut>>"))
        self.add_command(label="Copy", command=lambda: self._widget.event_generate("<<Copy>>"))
        self.add_command(label="Paste", command=lambda: self._widget.event_generate("<<Paste>>"))
        self.add_separator()
        self.add_command(label="Select all", command=self._select_all)

    def cm_bind(self):
        """ Bind the menu to the given widgets Right Click event

        After associating a widget with this :class:`ContextMenu` this function should be called
        to bind it to the right click button
        """
        button = "<Button-2>" if platform.system() == "Darwin" else "<Button-3>"
        logger.debug("Binding '%s' to '%s'", button, self._widget.winfo_class())
        scaling_factor = get_config().scaling_factor if get_config() is not None else 1.0
        x_offset = int(34 * scaling_factor)
        self._widget.bind(button,
                          lambda event: self.tk_popup(event.x_root + x_offset, event.y_root, 0))

    def _select_all(self):
        """ Select all for Text or Entry widgets """
        logger.debug("Selecting all for '%s'", self._widget.winfo_class())
        if self._widget.winfo_class() == "Text":
            self._widget.focus_force()
            self._widget.tag_add("sel", "1.0", "end")
        else:
            self._widget.focus_force()
            self._widget.select_range(0, tk.END)


class ConsoleOut(ttk.Frame):  # pylint: disable=too-many-ancestors
    """ The Console out section of the GUI.

    A Read only text box for displaying the output from stdout/stderr.

    All handling is internal to this method. To clear the console, the stored tkinter variable in
    :attr:`~lib.gui.Config.tk_vars` ``consoleclear`` should be triggered.

    Parameters
    ----------
    parent: tkinter object
        The Console's parent widget
    debug: bool
        ``True`` if console output should not be directed to this widget otherwise ``False``

    """

    def __init__(self, parent, debug):
        logger.debug("Initializing %s: (parent: %s, debug: %s)",
                     self.__class__.__name__, parent, debug)
        super().__init__(parent)
        self.pack(side=tk.TOP, anchor=tk.W, padx=10, pady=(2, 0),
                  fill=tk.BOTH, expand=True)
        self._console = _ReadOnlyText(self)
        rc_menu = ContextMenu(self._console)
        rc_menu.cm_bind()
        self._console_clear = get_config().tk_vars['consoleclear']
        self._set_console_clear_var_trace()
        self._debug = debug
        self._build_console()
        self._add_tags()
        logger.debug("Initialized %s", self.__class__.__name__)

    def _set_console_clear_var_trace(self):
        """ Set a trace on the consoleclear tkinter variable to trigger :func:`_clear` """
        logger.debug("Set clear trace")
        self._console_clear.trace("w", self._clear)

    def _build_console(self):
        """ Build and place the console  and add stdout/stderr redirection """
        logger.debug("Build console")
        self._console.config(width=100, height=6, bg="gray90", fg="black")
        self._console.pack(side=tk.LEFT, anchor=tk.N, fill=tk.BOTH, expand=True)

        scrollbar = ttk.Scrollbar(self, command=self._console.yview)
        scrollbar.pack(side=tk.LEFT, fill="y")
        self._console.configure(yscrollcommand=scrollbar.set)

        self._redirect_console()
        logger.debug("Built console")

    def _add_tags(self):
        """ Add tags to text widget to color based on output """
        logger.debug("Adding text color tags")
        self._console.tag_config("default", foreground="#1E1E1E")
        self._console.tag_config("stderr", foreground="#E25056")
        self._console.tag_config("info", foreground="#2B445E")
        self._console.tag_config("verbose", foreground="#008140")
        self._console.tag_config("warning", foreground="#F77B00")
        self._console.tag_config("critical", foreground="red")
        self._console.tag_config("error", foreground="red")

    def _redirect_console(self):
        """ Redirect stdout/stderr to console Text Box """
        logger.debug("Redirect console")
        if self._debug:
            logger.info("Console debug activated. Outputting to main terminal")
        else:
            sys.stdout = _SysOutRouter(self._console, "stdout")
            sys.stderr = _SysOutRouter(self._console, "stderr")
        logger.debug("Redirected console")

    def _clear(self, *args):  # pylint: disable=unused-argument
        """ Clear the console output screen """
        logger.debug("Clear console")
        if not self._console_clear.get():
            logger.debug("Console not set for clearing. Skipping")
            return
        self._console.delete(1.0, tk.END)
        self._console_clear.set(False)
        logger.debug("Cleared console")


class _ReadOnlyText(tk.Text):  # pylint: disable=too-many-ancestors
    """ A read only text widget.

    Standard tkinter Text widgets are read/write by default. As we want to make the console
    display writable by the Faceswap process but not the user, we need to redirect its insert and
    delete attributes.

    Source: https://stackoverflow.com/questions/3842155
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.redirector = _WidgetRedirector(self)
        self.insert = self.redirector.register("insert", lambda *args, **kw: "break")
        self.delete = self.redirector.register("delete", lambda *args, **kw: "break")


class _SysOutRouter():
    """ Route stdout/stderr to the given text box.

    Parameters
    ----------
    console: tkinter Object
        The widget that will receive the output from stderr/stdout
    out_type: ['stdout', 'stderr']
        The output type to redirect
    """

    def __init__(self, console, out_type):
        logger.debug("Initializing %s: (console: %s, out_type: '%s')",
                     self.__class__.__name__, console, out_type)
        self._console = console
        self._out_type = out_type
        self._recolor = re.compile(r".+?(\s\d+:\d+:\d+\s)(?P<lvl>[A-Z]+)\s")
        logger.debug("Initialized %s", self.__class__.__name__)

    def _get_tag(self, string):
        """ Set the tag based on regex of log output """
        if self._out_type == "stderr":
            # Output all stderr in red
            return self._out_type

        output = self._recolor.match(string)
        if not output:
            return "default"
        tag = output.groupdict()["lvl"].strip().lower()
        return tag

    def write(self, string):
        """ Capture stdout/stderr """
        self._console.insert(tk.END, string, self._get_tag(string))
        self._console.see(tk.END)

    @staticmethod
    def flush():
        """ If flush is forced, send it to normal terminal """
        sys.__stdout__.flush()


class _WidgetRedirector:
    """Support for redirecting arbitrary widget sub-commands.

    Some Tk operations don't normally pass through tkinter.  For example, if a
    character is inserted into a Text widget by pressing a key, a default Tk
    binding to the widget's 'insert' operation is activated, and the Tk library
    processes the insert without calling back into tkinter.

    Although a binding to <Key> could be made via tkinter, what we really want
    to do is to hook the Tk 'insert' operation itself.  For one thing, we want
    a text.insert call in idle code to have the same effect as a key press.

    When a widget is instantiated, a Tcl command is created whose name is the
    same as the path name widget._w.  This command is used to invoke the various
    widget operations, e.g. insert (for a Text widget). We are going to hook
    this command and provide a facility ('register') to intercept the widget
    operation.  We will also intercept method calls on the tkinter class
    instance that represents the tk widget.

    In IDLE, WidgetRedirector is used in Percolator to intercept Text
    commands.  The function being registered provides access to the top
    of a Percolator chain.  At the bottom of the chain is a call to the
    original Tk widget operation.

    Attributes
    -----------
    _operations: dict
        Dictionary mapping operation name to new function. widget: the widget whose tcl command
        is to be intercepted.
    tk: widget.tk
        A convenience attribute, probably not needed.
    orig: str
        new name of the original tcl command.

    Notes
    -----
    Since renaming to orig fails with TclError when orig already exists, only one
    WidgetDirector can exist for a given widget.
    """
    def __init__(self, widget):
        self._operations = {}
        self.widget = widget                                # widget instance
        self.tk_ = tk_ = widget.tk                          # widget's root
        wgt = widget._w  # pylint:disable=protected-access  # widget's (full) Tk pathname
        self.orig = wgt + "_orig"
        # Rename the Tcl command within Tcl:
        tk_.call("rename", wgt, self.orig)
        # Create a new Tcl command whose name is the widget's path name, and
        # whose action is to dispatch on the operation passed to the widget:
        tk_.createcommand(wgt, self.dispatch)

    def __repr__(self):
        return "%s(%s<%s>)" % (self.__class__.__name__,
                               self.widget.__class__.__name__,
                               self.widget._w)  # pylint:disable=protected-access

    def close(self):
        "Unregister operations and revert redirection created by .__init__."
        for operation in list(self._operations):
            self.unregister(operation)
        widget = self.widget
        tk_ = widget.tk
        wgt = widget._w  # pylint:disable=protected-access
        # Restore the original widget Tcl command.
        tk_.deletecommand(wgt)
        tk_.call("rename", self.orig, wgt)
        del self.widget, self.tk_  # Should not be needed
        # if instance is deleted after close, as in Percolator.

    def register(self, operation, function):
        """Return _OriginalCommand(operation) after registering function.

        Registration adds an operation: function pair to ._operations.
        It also adds a widget function attribute that masks the tkinter
        class instance method.  Method masking operates independently
        from command dispatch.

        If a second function is registered for the same operation, the
        first function is replaced in both places.
        """
        self._operations[operation] = function
        setattr(self.widget, operation, function)
        return _OriginalCommand(self, operation)

    def unregister(self, operation):
        """Return the function for the operation, or None.

        Deleting the instance attribute unmasks the class attribute.
        """
        if operation in self._operations:
            function = self._operations[operation]
            del self._operations[operation]
            try:
                delattr(self.widget, operation)
            except AttributeError:
                pass
            return function
        return None

    def dispatch(self, operation, *args):
        """Callback from Tcl which runs when the widget is referenced.

        If an operation has been registered in self._operations, apply the
        associated function to the args passed into Tcl. Otherwise, pass the
        operation through to Tk via the original Tcl function.

        Note that if a registered function is called, the operation is not
        passed through to Tk.  Apply the function returned by self.register()
        to *args to accomplish that.  For an example, see colorizer.py.

        """
        op_ = self._operations.get(operation)
        try:
            if op_:
                return op_(*args)
            return self.tk_.call((self.orig, operation) + args)
        except TclError:
            return ""


class _OriginalCommand:
    """Callable for original tk command that has been redirected.

    Returned by .register; can be used in the function registered.
    redir = WidgetRedirector(text)
    def my_insert(*args):
        print("insert", args)
        original_insert(*args)
    original_insert = redir.register("insert", my_insert)
    """

    def __init__(self, redir, operation):
        """Create .tk_call and .orig_and_operation for .__call__ method.

        .redir and .operation store the input args for __repr__.
        .tk and .orig copy attributes of .redir (probably not needed).
        """
        self.redir = redir
        self.operation = operation
        self.tk_ = redir.tk_  # redundant with self.redir
        self.orig = redir.orig  # redundant with self.redir
        # These two could be deleted after checking recipient code.
        self.tk_call = redir.tk_.call
        self.orig_and_operation = (redir.orig, operation)

    def __repr__(self):
        return "%s(%r, %r)" % (self.__class__.__name__,
                               self.redir, self.operation)

    def __call__(self, *args):
        return self.tk_call(self.orig_and_operation + args)


class StatusBar(ttk.Frame):  # pylint: disable=too-many-ancestors
    """ Status Bar for displaying the Status Message and  Progress Bar at the
    bottom of the GUI. """

    def __init__(self, parent):
        ttk.Frame.__init__(self, parent)
        self.pack(side=tk.BOTTOM, padx=10, pady=2, fill=tk.X, expand=False)

        self._status_message = tk.StringVar()
        self._pbar_message = tk.StringVar()
        self._pbar_position = tk.IntVar()

        self._status_message.set("Ready")

        self._status()
        self._pbar = self._progress_bar()

    @property
    def status_message(self):
        """:class:`tkinter.StringVar`: The variable to hold the status bar message on the left
        hand side of the status bar. """
        return self._status_message

    def _status(self):
        """ Place Status label into left of the status bar. """
        statusframe = ttk.Frame(self)
        statusframe.pack(side=tk.LEFT, anchor=tk.W, fill=tk.X, expand=False)

        lbltitle = ttk.Label(statusframe, text="Status:", width=6, anchor=tk.W)
        lbltitle.pack(side=tk.LEFT, expand=False)

        lblstatus = ttk.Label(statusframe,
                              width=40,
                              textvariable=self._status_message,
                              anchor=tk.W)
        lblstatus.pack(side=tk.LEFT, anchor=tk.W, fill=tk.X, expand=True)

    def _progress_bar(self):
        """ Place progress bar into right of the status bar. """
        progressframe = ttk.Frame(self)
        progressframe.pack(side=tk.RIGHT, anchor=tk.E, fill=tk.X)

        lblmessage = ttk.Label(progressframe, textvariable=self._pbar_message)
        lblmessage.pack(side=tk.LEFT, padx=3, fill=tk.X, expand=True)

        pbar = ttk.Progressbar(progressframe,
                               length=200,
                               variable=self._pbar_position,
                               maximum=100,
                               mode="determinate")
        pbar.pack(side=tk.LEFT, padx=2, fill=tk.X, expand=True)
        pbar.pack_forget()
        return pbar

    def progress_start(self, mode):
        """ Set progress bar mode and display,

        Parameters
        ----------
        mode: ["indeterminate", "determinate"]
            The mode that the progress bar should be executed in
        """
        self._progress_set_mode(mode)
        self._pbar.pack()

    def progress_stop(self):
        """ Reset progress bar and hide """
        self._pbar_message.set("")
        self._pbar_position.set(0)
        self._progress_set_mode("determinate")
        self._pbar.pack_forget()

    def _progress_set_mode(self, mode):
        """ Set the progress bar mode """
        self._pbar.config(mode=mode)
        if mode == "indeterminate":
            self._pbar.config(maximum=100)
            self._pbar.start()
        else:
            self._pbar.stop()
            self._pbar.config(maximum=100)

    def progress_update(self, message, position, update_position=True):
        """ Update the GUIs progress bar and position.

        Parameters
        ----------
        message: str
            The message to display next to the progress bar
        position: int
            The position that the progress bar should be set to
        update_position: bool, optional
            If ``True`` then the progress bar will be updated to the position given in
            :attr:`position`. If ``False`` the progress bar will not be updates. Default: ``True``
        """
        self._pbar_message.set(message)
        if update_position:
            self._pbar_position.set(position)


class Tooltip:
    """
    Create a tooltip for a given widget as the mouse goes on it.

    Parameters
    ----------
    widget: tkinter object
        The widget to apply the tool-tip to
    background: str, optional
        The hex code for the background color. Default:'#FFFFEA'
    pad: tuple, optional
        (left, top, right, bottom) padding for the tool-tip. Default: (5, 3, 5, 3)
    text: str, optional
        The text to be displayed in the tool-tip. Default: 'widget info'
    waittime: int, optional
        The time in miliseconds to wait before showing the tool-tip. Default: 400
    wraplength: int, optional
        The text length for each line before wrapping. Default: 250

    Example
    -------
    >>> button = ttk.Button(parent, text="Exit")
    >>> Tooltip(button, text="Click to exit")
    >>> button.pack()

    Notes
    -----
    Adapted from StackOverflow: http://stackoverflow.com/questions/3221956 and
    http://www.daniweb.com/programming/software-development/code/484591/a-tooltip-class-for-tkinter


    - Originally written by vegaseat on 2014.09.09.
    - Modified to include a delay time by Victor Zaccardo on 2016.03.25.
    - Modified to correct extreme right and extreme bottom behavior by Alberto Vassena on \
        2016.11.05.
    - Modified to stay inside the screen whenever the tooltip might go out on the top but still \
        the screen is higher than the tooltip  by Alberto Vassena on 2016.11.05.
    - Modified to use the more flexible mouse positioning  by Alberto Vassena on 2016.11.05.
    - Modified to add customizable background color, padding, waittime and wraplength on creation \
        by Alberto Vassena on 2016.11.05.

    Tested on Ubuntu 16.04/16.10, running Python 3.5.2
    """
    def __init__(self, widget, *, background="#FFFFEA", pad=(5, 3, 5, 3), text="widget info",
                 waittime=400, wraplength=250):

        self._waittime = waittime  # in milliseconds, originally 500
        self._wraplength = wraplength  # in pixels, originally 180
        self._widget = widget
        self._text = text
        self._widget.bind("<Enter>", self._on_enter)
        self._widget.bind("<Leave>", self._on_leave)
        self._widget.bind("<ButtonPress>", self._on_leave)
        self._background = background
        self._pad = pad
        self._ident = None
        self._topwidget = None

    def _on_enter(self, event=None):  # pylint:disable=unused-argument
        """ Schedule on an enter event """
        self._schedule()

    def _on_leave(self, event=None):  # pylint:disable=unused-argument
        """ Unschedule on a leave event """
        self._unschedule()
        self._hide()

    def _schedule(self):
        """ Show the tooltip after wait period """
        self._unschedule()
        self._ident = self._widget.after(self._waittime, self._show)

    def _unschedule(self):
        """ Hide the tooltip """
        id_ = self._ident
        self._ident = None
        if id_:
            self._widget.after_cancel(id_)

    def _show(self):
        """ Show the tooltip """
        def tip_pos_calculator(widget, label,
                               *,
                               tip_delta=(10, 5), pad=(5, 3, 5, 3)):
            """ Calculate the tooltip position """

            s_width, s_height = widget.winfo_screenwidth(), widget.winfo_screenheight()

            width, height = (pad[0] + label.winfo_reqwidth() + pad[2],
                             pad[1] + label.winfo_reqheight() + pad[3])

            mouse_x, mouse_y = widget.winfo_pointerxy()

            x_1, y_1 = mouse_x + tip_delta[0], mouse_y + tip_delta[1]
            x_2, y_2 = x_1 + width, y_1 + height

            x_delta = x_2 - s_width
            if x_delta < 0:
                x_delta = 0
            y_delta = y_2 - s_height
            if y_delta < 0:
                y_delta = 0

            offscreen = (x_delta, y_delta) != (0, 0)

            if offscreen:

                if x_delta:
                    x_1 = mouse_x - tip_delta[0] - width

                if y_delta:
                    y_1 = mouse_y - tip_delta[1] - height

            offscreen_again = y_1 < 0  # out on the top

            if offscreen_again:
                # No further checks will be done.

                # TIP:
                # A further mod might auto-magically augment the
                # wraplength when the tooltip is too high to be
                # kept inside the screen.
                y_1 = 0

            return x_1, y_1

        background = self._background
        pad = self._pad
        widget = self._widget

        # creates a toplevel window
        self._topwidget = tk.Toplevel(widget)
        if platform.system() == "Darwin":
            # For Mac OS
            self._topwidget.tk.call("::tk::unsupported::MacWindowStyle",
                                    "style", self._topwidget._w,  # pylint:disable=protected-access
                                    "help", "none")

        # Leaves only the label and removes the app window
        self._topwidget.wm_overrideredirect(True)

        win = tk.Frame(self._topwidget,
                       background=background,
                       borderwidth=0)
        label = tk.Label(win,
                         text=self._text,
                         justify=tk.LEFT,
                         background=background,
                         relief=tk.SOLID,
                         borderwidth=0,
                         wraplength=self._wraplength)

        label.grid(padx=(pad[0], pad[2]),
                   pady=(pad[1], pad[3]),
                   sticky=tk.NSEW)
        win.grid()

        xpos, ypos = tip_pos_calculator(widget, label)

        self._topwidget.wm_geometry("+%d+%d" % (xpos, ypos))

    def _hide(self):
        """ Hide the tooltip """
        topwidget = self._topwidget
        if topwidget:
            topwidget.destroy()
        self._topwidget = None
