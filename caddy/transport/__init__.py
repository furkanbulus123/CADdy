"""The layer that talks to claude.exe.

It uses QtCore (QProcess, Signal) but never touches QtWidgets — it is
independent of the UI and can be tested on its own.
"""
