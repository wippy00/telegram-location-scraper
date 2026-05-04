from utils.llm_extractor import extract_places_via_llm



reel_description = """
🔥 JAPAN’S DREAM BENTO BOX 🔥
@oneblogram ◀ Follow for more insane local eats in Japan 🇯🇵

This Harajuku spot serves a bento box that’s every meat lover’s dream—featuring Kokusan ribs weighing over one kilogram!

Smoked low and slow for 10–12 hours, the ribs come out fall-off-the-bone tender with an intense smoky punch. And here’s the pro move: drench them in the house-made sauces. The red hot sauce and BBQ sauce are unbeatable.

This is one of those meals that leaves a lasting impression—seriously a must for anyone chasing bold flavors in Tokyo.

📍 Kokusan Ribs
4 Chome-21-13 Jingumae, Shibuya, Tokyo
• Kokusan Ribs 2,900 JPY per 100g

🍀 SAVE this post for your next Tokyo food adventure! 🍀

/ Japanese cuisine / Tokyo food / BBQ Japan / Harajuku eats / Japan foodie / Hidden gems Tokyo / Lunch in Japan / #texasbbq #japanfood #japanesefoodie #wagyubeef
"""


reel_ocr = """
OVER KG BEEF RIB BENTO IN JAPAN
Today Im in Harajuku
follo Kokusay Fd always wanted t0 sink my teeth grams the Please Irom yea
Td always wanted to sink teeth
into mouthful of smoked beef chunk
and today that dream came true
Their Kokusan ribs are smoked
low and slw for 10 t0 12 hours
which is why they re incredibly tender Kokusan BEEF
with that bold smoky flavor
And here s pro tip
pour their sauces generously over the meat
The red hot sauce and
and everything here is homemade
If you re a true meat lover
this is one spot
Shibuya Tokyo YoU can t afford to miss
SLICE of LIE you can t afford to miss
"""

places = extract_places_via_llm(reel_description, reel_ocr)

print(places)



