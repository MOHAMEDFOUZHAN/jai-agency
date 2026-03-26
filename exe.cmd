pyinstaller --onefile --noconsole `
--name="Kokkalatty_Sales" `
--add-data "templates;templates" `
--add-data "static;static" `
--icon="static/css/images/logo.ico" `
--hidden-import webview `
--hidden-import waitress `
app.py

cd "d:\Homewoode small factory\transfers"; pyinstaller --noconfirm --onefile --windowed --icon="static/images/logo.ico" --add-data "static;static" --add-data "templates;templates" app.py
