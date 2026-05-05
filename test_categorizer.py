from pipeline.categorizer import categorize_message

messages = [
    "Ninenzaka - Kyoto\nhttps://maps.app.goo.gl/Y5SLYDjjvMJVEaq1A",
    "https://maps.app.goo.gl/fZi74PpDFB2rvJCM7?g_st=ic",
]

for msg in messages:
    category = categorize_message(msg)
    print(f"Messaggio: {msg.replace(chr(10), ' ')[:60]}...")
    print(f"Categoria: {category}\n")
