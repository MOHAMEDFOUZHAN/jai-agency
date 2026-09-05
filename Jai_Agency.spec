# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules

a = Analysis(
    ['app.py'],
    pathex=[],
    binaries=collect_dynamic_libs('pypdfium2_raw') + collect_dynamic_libs('onnxruntime'),
    datas=[
        ('templates', 'templates'),
        ('static', 'static'),
        ('datebase', 'datebase')
    ] + collect_data_files('rapidocr_onnxruntime') + collect_data_files('pypdfium2') + collect_data_files('pypdfium2_raw') + collect_data_files('onnxruntime'),
    hiddenimports=[
        'webview',
        'waitress',
        'flask',
        'jinja2',
        'mailer',
        'clr',
        'pythonnet',
        'ocr_invoice_parser',
        'rapidocr_onnxruntime',
        'pypdfium2',
        'pypdfium2_raw',
        'onnxruntime',
        'cv2',
        'numpy',
        'PIL',
        'PIL.Image',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='Jai_Agency',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['static\\css\\images\\logo.ico'],
)
