import os
import re
import urllib.request
import urllib.parse
from urllib.error import URLError

STATIC_DIR = os.path.join(os.path.dirname(__file__), 'static')
LIB_DIR = os.path.join(STATIC_DIR, 'lib')
CSS_DIR = os.path.join(STATIC_DIR, 'css')
WEBFONTS_DIR = os.path.join(STATIC_DIR, 'webfonts')
FONTS_DIR = os.path.join(STATIC_DIR, 'fonts') # for google fonts

for d in [LIB_DIR, CSS_DIR, WEBFONTS_DIR, FONTS_DIR]:
    os.makedirs(d, exist_ok=True)

def download(url, dest):
    print(f"Downloading {url} to {dest}")
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'})
    try:
        with urllib.request.urlopen(req, timeout=10) as response, open(dest, 'wb') as out_file:
            data = response.read()
            out_file.write(data)
            return data
    except Exception as e:
        print(f"Error downloading {url}: {e}")
        return None

# 1. Download FontAwesome
fa_version = "6.5.2"
fa_css_url = f"https://cdnjs.cloudflare.com/ajax/libs/font-awesome/{fa_version}/css/all.min.css"
fa_css_dest = os.path.join(CSS_DIR, 'all.min.css')
fa_css_data = download(fa_css_url, fa_css_dest)

if fa_css_data:
    css_content = fa_css_data.decode('utf-8')
    # Find all url(...) in CSS
    urls = re.findall(r'url\(([^)]+)\)', css_content)
    for u in urls:
        u = u.strip('"\'')
        if u.startswith('data:'):
            continue
        if '../webfonts' in u:
            # e.g., ../webfonts/fa-solid-900.woff2?v=6.5.2
            font_filename = u.split('/')[-1].split('?')[0].split('#')[0]
            # download it
            font_url = f"https://cdnjs.cloudflare.com/ajax/libs/font-awesome/{fa_version}/webfonts/{font_filename}"
            font_dest = os.path.join(WEBFONTS_DIR, font_filename)
            download(font_url, font_dest)

# 2. Download ApexCharts
apex_url = "https://cdn.jsdelivr.net/npm/apexcharts@3.49.0/dist/apexcharts.min.js"
apex_dest = os.path.join(LIB_DIR, 'apexcharts.min.js')
download(apex_url, apex_dest)

# 3. Download Google Fonts
google_fonts_urls = [
    "https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600;700;800&family=Space+Grotesk:wght@400;500;600;700&display=swap",
    "https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap"
]

all_google_css = ""

for i, g_url in enumerate(google_fonts_urls):
    print(f"Fetching Google Fonts CSS: {g_url}")
    req = urllib.request.Request(g_url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'})
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            css = response.read().decode('utf-8')
            # Extract woff2 urls
            font_urls = re.findall(r'url\((https://fonts\.gstatic\.com[^)]+)\)', css)
            for f_url in font_urls:
                f_url = f_url.strip('"\'')
                filename = f_url.split('/')[-1]
                # some filenames might not be unique across families, but usually they are hashed or named well.
                # Just to be safe, we can hash the url or use the filename if it's unique
                friendly_name = filename.split('.')[0] + ".woff2"
                dest = os.path.join(FONTS_DIR, friendly_name)
                download(f_url, dest)
                # Replace in css
                css = css.replace(f_url, f"../fonts/{friendly_name}")
            
            all_google_css += css + "\n\n"
    except Exception as e:
        print(f"Error fetching Google Fonts: {e}")

with open(os.path.join(CSS_DIR, 'fonts.css'), 'w', encoding='utf-8') as f:
    f.write(all_google_css)
print("Finished downloading assets.")
