import os

def fix():
    for root, dirs, files in os.walk(r"d:\Jai Agency\templates"):
        for f in files:
            if f.endswith(".html"):
                p = os.path.join(root, f)
                with open(p, 'r', encoding='latin-1') as fr:
                    content = fr.read()
                
                # Check for ? immediately followed by {
                if "?{{" in content:
                    new_content = content.replace("?{{", "₹{{")
                    with open(p, 'w', encoding='utf-8') as fw:
                        fw.write(new_content)
                    print(f"Patched: {p}")

if __name__ == "__main__":
    fix()
