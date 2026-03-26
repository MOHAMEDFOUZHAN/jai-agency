import os
import re

def fix_currency():
    templates_dir = r"d:\Jai Agency\templates"
    for root, dirs, files in os.walk(templates_dir):
        for file in files:
            if file.endswith(".html"):
                path = os.path.join(root, file)
                with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                
                # Replace literal \u20B9
                new_content = content.replace(r"\u20B9", "₹")
                
                # Replace mangled ? before currency tags
                # Target forms: ?{{ or ? (followed by a number in some cases, but better be safe)
                new_content = re.sub(r"\?\{\{", "₹{{", new_content)
                new_content = re.sub(r"\?\$", "₹", new_content) # if any ?$ ?
                
                if new_content != content:
                    with open(path, 'w', encoding='utf-8') as f:
                        f.write(new_content)
                    print(f"Fixed: {path}")

if __name__ == "__main__":
    fix_currency()
