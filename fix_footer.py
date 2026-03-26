
path = r'd:\Homewoode small factory\templates\inventory\products.html'
with open(path, 'r') as f:
    content = f.read()

import re
# Find the last </script> and replace everything after it with \n{% endblock %}
new_content = re.sub(r'</script>.*$', '</script>\n{% endblock %}', content, flags=re.DOTALL)

with open(path, 'w') as f:
    f.write(new_content)
print("Fixed!")
