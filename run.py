"""PyInstaller entry — Flet Apple style"""
import sys
import flet as ft

if __name__ == "__main__":
    if "--editor" in sys.argv:
        from editor import main as editor_main
        ft.run(editor_main)
    else:
        from launcher import main
        ft.run(main)
