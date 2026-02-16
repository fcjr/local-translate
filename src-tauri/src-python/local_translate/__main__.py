"""The main entry point for the Tauri app."""

import sys
from multiprocessing import freeze_support

from local_translate import main

freeze_support()

sys.exit(main())
