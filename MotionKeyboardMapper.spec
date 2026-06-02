# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['run.py'],
    pathex=[],
    binaries=[('C:/Users/gjc_9/AppData/Roaming/Python/Python313/site-packages/mediapipe/tasks/c/libmediapipe.dll', 'mediapipe/tasks/c')],
    datas=[('assets/models/pose_landmarker_heavy.task', 'assets/models'), ('config/profiles/naruto_fighting.json', 'config/profiles'), ('actions/definitions/metric_catalog.json', 'actions/definitions'), ('actions/definitions/naruto_actions.json', 'actions/definitions')],
    hiddenimports=['mediapipe', 'mediapipe.tasks', 'mediapipe.tasks.python', 'mediapipe.tasks.python.vision', 'mediapipe.tasks.python.vision.core', 'mediapipe.tasks.python.core', 'mediapipe.tasks.python.components', 'mediapipe.tasks.python.components.containers', 'cv2', 'pynput'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['PyQt5', 'PySide6', 'sphinx', 'jedi', 'black', 'zmq', 'tensorflow'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='MotionKeyboardMapper',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['assets\\icon.ico'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='MotionKeyboardMapper',
)
