"""bmlauncher.pyw - starts the Burnout Mashup launcher window without a console (Python 3.11+, standard library)."""
import os
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
if sys.version_info < (3, 11):
    import tkinter.messagebox as mb
    mb.showerror("Burnout Mashup", "Python 3.11 or newer is needed (this is %d.%d). Install it from python.org "
                 "(tick 'Add python.exe to PATH') and start Burnout Mashup again." % sys.version_info[:2])
    sys.exit(9)
import bmgui  # noqa: E402

sys.exit(bmgui.main(sys.argv[1:]))
