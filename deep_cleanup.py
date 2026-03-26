
import os
import re

base_path = r'd:\Homewoode small factory\templates\inventory'
files = [f for f in os.listdir(base_path) if f.endswith('.html')]

def clean_file(filepath):
    print(f"Cleaning {filepath}...")
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    initial_len = len(content)
    
    # 1. Remove the dropdown block for Invoice (multiple possible formats)
    # This one specifically targets the dropdown structure seen in stock_return
    content = re.sub(r'<div class="dropdown">.*?Invoice.*?</div>\s*</div>', '', content, flags=re.DOTALL)
    
    # 2. Remove standard navigation links (with or without Jinja)
    content = re.sub(r'<a href="/inventory/stock-list".*?</a>', '', content, flags=re.DOTALL)
    content = re.sub(r'<a href="/inventory/payments".*?</a>', '', content, flags=re.DOTALL)
    
    # 3. Specifically look for links by text if href patterns missed something
    # but the href pattern is usually best.
    
    if len(content) != initial_len:
        print(f"  Modified {filepath}")
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
    else:
        print(f"  No changes for {filepath}")

for filename in files:
    clean_file(os.path.join(base_path, filename))
print("Deep cleanup complete!")
