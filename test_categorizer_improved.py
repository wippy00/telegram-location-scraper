from pipeline.categorizer import categorize_message
import importlib
import pipeline.categorizer

# Ricarica il modulo per evitare cache
importlib.reload(pipeline.categorizer)
from pipeline.categorizer import categorize_message

test_messages = [
    # NO# - dovrebbero essere scartati
    ("Tokyo", False),
    ("Anguilla è il sogno", False),
    ("5 waggyu tokyo", False),
    ("5W-Tokyo", False),
    ("Odio i negri", False),
    ("Tassativo que", False),
    ("Morte ai negri", False),
    ("Apposto", False),
    ("tiktok mi rifiuto", False),
    ("mandero'", False),
    ("Daje", False),
    ("Nigga", False),
    ("Heil hitler", False),
    
    # SI# - dovrebbero essere processati
    ("Kanazawa", True),
    ("passiamo a Shibamata", True),
    ("kokedera temple - kyoto", True),
    ("nishiki market kyoto", True),
    ("minho national park osaka", True),
    ("sake market akihabara", True),
    ("hitachi seaside park", True),
    ("otaji nenbutsu-ji", True),
    ("adashino nenbutsu-ji", True),
    ("nara deer park", True),
    ("wakayama", True),
]

correct = 0
total = len(test_messages)

for msg, should_accept in test_messages:
    category = categorize_message(msg)
    is_accepted = category.value != "unknown"
    
    status = "✓" if is_accepted == should_accept else "✗"
    expected = "SI" if should_accept else "NO"
    actual = "SI" if is_accepted else "NO"
    
    print(f"{status} {expected}# {msg[:40]:<40} -> {actual} ({category.value})")
    if is_accepted == should_accept:
        correct += 1

print(f"\nRisultati: {correct}/{total} corretti")
