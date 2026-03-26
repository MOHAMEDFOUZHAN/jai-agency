print("Testing swapped imports...")
import os
from flask import Flask
print("Imported Flask")
try:
    print("Attempting to import waitress...")
    from waitress import serve
    print("Imported waitress")
    print("Attempting to import webview...")
    import webview
    print("Imported webview")
except Exception as e:
    print(f"Import failed: {e}")
print("Done.")
