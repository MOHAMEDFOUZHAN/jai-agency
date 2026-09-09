# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules

datas = [
    ('templates', 'templates'),
    ('static', 'static'),
    ('datebase', 'datebase'),
] + collect_data_files('rapidocr_onnxruntime') + collect_data_files('pypdfium2') + collect_data_files('pypdfium2_raw') + collect_data_files('onnxruntime') + collect_data_files('webview')

binaries = collect_dynamic_libs('pypdfium2_raw') + collect_dynamic_libs('onnxruntime')

hiddenimports = [
    'webview',
    'webview.platforms.winforms',
    'webview.platforms.edgechromium',
    'waitress',
    'flask',
    'jinja2',
    'mailer',
    'fpdf',
    'clr',
    'clr_loader',
    'pythonnet',
    'ocr_invoice_parser',
    'rapidocr_onnxruntime',
    'rapidocr_onnxruntime.ch_ppocr_v3_det',
    'rapidocr_onnxruntime.ch_ppocr_v3_rec',
    'rapidocr_onnxruntime.ch_ppocr_v2_cls',
    'pypdfium2',
    'pypdfium2_raw',
    'onnxruntime',
    'cv2',
    'numpy',
    'PIL',
    'PIL.Image',
    'pyclipper',
    'shapely',
    'yaml',
    'sqlite3',
] + collect_submodules('rapidocr_onnxruntime') + collect_submodules('webview') + collect_submodules('onnxruntime') + collect_submodules('pypdfium2')

a = Analysis(
    ['app.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
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
    icon=['static/css/images/logo.ico'],
)
