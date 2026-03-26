import os

def fix_currency():
    templates_dir = r"d:\Jai Agency\templates"
    for root, dirs, files in os.walk(templates_dir):
        for file in files:
            if file.endswith(".html"):
                path = os.path.join(root, file)
                try:
                    # Try reading with utf-8 first
                    with open(path, 'r', encoding='utf-8') as f:
                        content = f.read()
                except UnicodeDecodeError:
                    # If that fails, it's probably ANSI from the bad PowerShell command
                    with open(path, 'r', encoding='latin-1') as f:
                        content = f.read()
                
                original = content
                
                # Replace literal \u20B9
                content = content.replace(r"\u20B9", "₹")
                
                # If content contains the mangled '?' (or whatever PowerShell did)
                # target '?{{' but also look for '?\u20B9' or similar if they exist
                # But since previous turn showed '?', we target that.
                
                # Replace '?{{' and any other common mangled patterns
                content = content.replace("?{{", "₹{{")
                content = content.replace("?₹{{", "₹{{") # double fix
                content = content.replace("?&#8377;", "₹")
                content = content.replace("?&#x20B9;", "₹")
                
                # Specific mangled sequences
                # In some cases PowerShell mangles ₹ as 'â\x82\xac' (Euro?) or 'â\x82¹'
                # But here it looks like '?'
                
                if content != original:
                    with open(path, 'w', encoding='utf-8') as f:
                        f.write(content)
                    print(f"Fixed: {path}")

if __name__ == "__main__":
    fix_currency()
