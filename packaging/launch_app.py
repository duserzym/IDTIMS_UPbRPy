"""Entry script for the frozen app (PyInstaller runs this file as __main__)."""
import multiprocessing

from idtims_app.main import main

if __name__ == "__main__":
    multiprocessing.freeze_support()
    raise SystemExit(main())
