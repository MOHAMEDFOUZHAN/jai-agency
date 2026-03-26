import os

def fix():
    templates_dir = r"d:\Jai Agency\templates"
    for root, dirs, files in os.walk(templates_dir):
        for file in files:
            if file.endswith(".html"):
                path = os.path.join(root, file)
                with open(path, 'rb') as f:
                    content = f.read()
                
                # Replace literal \u20B9 (hex: 5C 75 32 30 42 39) with ₹ (utf-8: E2 82 B9)
                new_content = content.replace(b"\\u20B9", "₹".encode('utf-8'))
                
                # Replace ?{{ (hex: 3F 7B 7B) with ₹{{ (utf-8: E2 82 B9 7B 7B)
                new_content = new_content.replace(b"?{{", "₹{{".encode('utf-8'))
                
                # Replace PAID: ?{{ (hex: 50 41 49 44 3A 20 3F 7B 7B)
                new_content = new_content.replace(b"PAID: ?{{", "PAID: ₹{{".encode('utf-8'))
                
                # Replace O/S: ?{{ (hex: 4F 2F  53 3A 20 3F 7B 7B)
                new_content = new_content.replace(b"O/S: ?{{", "O/S: ₹{{".encode('utf-8'))

                # Replace &#8377; and &#x20B9;
                new_content = new_content.replace(b"&#8377;", "₹".encode('utf-8'))
                new_content = new_content.replace(b"&#x20B9;", "₹".encode('utf-8'))
                
                if new_content != content:
                    with open(path, 'wb') as f:
                        f.write(new_content)
                    print(f"Patched: {path}")

if __name__ == "__main__":
    fix()
