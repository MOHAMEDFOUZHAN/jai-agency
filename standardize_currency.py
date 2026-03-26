import os

def standardize_currency():
    templates_dir = r"d:\Jai Agency\templates"
    patterns = [
        ("?{{", "₹{{"),
        (r"\u20B9", "₹"),
        ("&#8377;", "₹"),
        ("&#x20B9;", "₹"),
        ("PAID: ?", "PAID: ₹"),
        ("O/S: ?", "O/S: ₹")
    ]
    
    for root, dirs, files in os.walk(templates_dir):
        for file in files:
            if file.endswith(".html"):
                path = os.path.join(root, file)
                try:
                    with open(path, 'r', encoding='utf-8') as f:
                        content = f.read()
                except:
                    with open(path, 'r', encoding='latin-1') as f:
                        content = f.read()
                
                original = content
                for old, new in patterns:
                    content = content.replace(old, new)
                
                if content != original:
                    with open(path, 'w', encoding='utf-8') as f:
                        f.write(content)
                    print(f"Standardized: {path}")

if __name__ == "__main__":
    standardize_currency()
