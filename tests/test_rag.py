import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from ai import get_relevant_knowledge

class DummyEntry:
    def __init__(self, ctype, sname, content):
        self.content_type = ctype
        self.source_name = sname
        self.content = content
        self.filename = "dummy.jpg" if ctype == "image" else None

entries = [
    DummyEntry('product', 'iPhone 15 Pro', 'Zo\'r telefon. Oyna tana. 128GB. Kichik ramka.'),
    DummyEntry('product', 'Samsung S24 Ultra', 'Eng kuchli Android. Stylus bor. Kameralari daxshat.'),
    DummyEntry('file', 'iPhone_qollanma.txt', 'Ushbu telefon batareyasi 1 kunga yetadi. Quvvatlagich sotib olishingiz mumkin.'),
    DummyEntry('file', 'kurer.txt', 'Toshkent shahriga yetkazish narxi 30 ming so\'m. Viloyatlarga chiqarilmaydi.')
]

# Test 1: Ask about iPhone
print("User: iPhone batareyasi qanaqa?")
result1 = get_relevant_knowledge(entries, "iPhone batareyasi qanaqa?")
print("-" * 20)
print(result1)
print("=" * 40)

# Test 2: Ask about delivery
print("User: yetkazish qancha?")
result2 = get_relevant_knowledge(entries, "dostavka yoki yetkazish qancha?")
print("-" * 20)
print(result2)
print("=" * 40)

# Test 3: Ask about empty or very generic stuff
print("User: salom")
result3 = get_relevant_knowledge(entries, "salom")
print("-" * 20)
print(result3)
print("=" * 40)
