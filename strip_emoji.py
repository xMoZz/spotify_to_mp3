"""Strip emojis from main.py"""
import re
import unicodedata

with open('main.py', 'r', encoding='utf-8') as f:
    content = f.read()

cleaned = []
for ch in content:
    if unicodedata.category(ch) == 'So':
        cleaned.append('')
    else:
        cleaned.append(ch)

cleaned = ''.join(cleaned)
# Fix any double spaces/lines caused by removal
cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
cleaned = re.sub(r'  +', ' ', cleaned)

with open('main.py', 'w', encoding='utf-8') as f:
    f.write(cleaned)

print('done - emojis stripped')
