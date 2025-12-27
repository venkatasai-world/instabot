import os
import time
import sqlite3
import textwrap
import requests
from dotenv import load_dotenv
from instagrapi import Client
from PIL import Image, ImageDraw, ImageFont
import google.generativeai as genai

load_dotenv()

USERNAME = os.getenv("IG_USERNAME")
PASSWORD = os.getenv("IG_PASSWORD")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

POSTS_PER_DAY = 3
DELAY_BETWEEN_POSTS = 3600  
DB_NAME = "quotes.db"
SESSION_FILE = "session.json"

if not USERNAME or not PASSWORD or not GEMINI_API_KEY:
    raise RuntimeError("❌ Environment variables missing")

# ---------------- GEMINI ----------------
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-2.5-flash")

# ---------------- DATABASE ----------------
conn = sqlite3.connect(DB_NAME)
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS quotes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    quote TEXT UNIQUE,
    author TEXT,
    used INTEGER DEFAULT 0
)
""")
conn.commit()

def fetch_quote():
    data = requests.get("https://zenquotes.io/api/random", timeout=10).json()[0]
    return data["q"].strip(), data["a"].strip()

cur.execute("SELECT COUNT(*) FROM quotes WHERE used=0")
available = cur.fetchone()[0]

while available < POSTS_PER_DAY:
    try:
        q, a = fetch_quote()
        cur.execute("INSERT INTO quotes (quote, author) VALUES (?, ?)", (q, a))
        conn.commit()
        available += 1
    except:
        pass

# ---------------- IMAGE ----------------
def load_font(size):
    try:
        return ImageFont.truetype("arial.ttf", size)
    except:
        return ImageFont.load_default()

def create_image(quote, author, filename):
    img = Image.new("RGB", (1080, 1080), "black")
    draw = ImageDraw.Draw(img)

    q_font = load_font(60)
    a_font = load_font(40)

    wrapped = textwrap.fill(quote, 30)
    bbox = draw.multiline_textbbox((0, 0), wrapped, font=q_font)
    w = bbox[2] - bbox[0]
    h = bbox[3] - bbox[1]

    draw.multiline_text(
        ((1080 - w) / 2, (1080 - h) / 2),
        wrapped,
        fill="white",
        font=q_font,
        align="center"
    )

    author_text = f"- {author}"
    abox = draw.textbbox((0, 0), author_text, font=a_font)
    aw = abox[2] - abox[0]

    draw.text(
        ((1080 - aw) / 2, 920),
        author_text,
        fill="white",
        font=a_font
    )

    img.save(filename)

def generate_caption(quote):
    prompt = f"""
Create a very simple Instagram caption.
One short sentence.
Use 2 relevant emojis.
Add only 3 hashtags.

Quote: "{quote}"
"""
    return model.generate_content(prompt).text.strip()


cl = Client()

if os.path.exists(SESSION_FILE):
    cl.load_settings(SESSION_FILE)
    cl.login(USERNAME, PASSWORD)
else:
    cl.login(USERNAME, PASSWORD)
    cl.dump_settings(SESSION_FILE)


cur.execute(
    "SELECT id, quote, author FROM quotes WHERE used=0 LIMIT ?",
    (POSTS_PER_DAY,)
)
posts = cur.fetchall()

for i, (qid, quote, author) in enumerate(posts, start=1):
    image_name = f"post_{i}.jpg"
    create_image(quote, author, image_name)

    caption = generate_caption(quote)
    cl.photo_upload(image_name, caption)

    cur.execute("UPDATE quotes SET used=1 WHERE id=?", (qid,))
    conn.commit()

    print(f"✅ Posted {i}/3")

    if i < POSTS_PER_DAY:
        time.sleep(DELAY_BETWEEN_POSTS)

conn.close()
