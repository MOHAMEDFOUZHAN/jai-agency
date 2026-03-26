
import os

base_path = r'd:\Homewoode small factory\templates\inventory'
files = [f for f in os.listdir(base_path) if f.endswith('.html')]

forbidden_patterns = [
    '/inventory/stock-list',
    '/inventory/payments',
    'Invoice',
    'Payments'
]

# Specifically we want to remove the <a> tags containing these links
def clean_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    new_lines = []
    for line in lines:
        skip = False
        # If the line contains stock-list or payments in an <a> tag, skip it
        if ('<a ' in line and '/inventory/stock-list' in line) or ('<a ' in line and '/inventory/payments' in line):
            skip = True
        
        if not skip:
            new_lines.append(line)
            
    with open(filepath, 'w', encoding='utf-8') as f:
        f.writelines(new_lines)

for filename in files:
    clean_file(os.path.join(base_path, filename))
print("Cleanup complete!")
