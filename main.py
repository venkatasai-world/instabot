import os
from dotenv import load_dotenv
import sqlite3
import textwrap
import requests
from instagrapi import Client
from PIL import Image, ImageDraw, ImageFont
import google.generativeai as genai


load_dotenv()


USERNAME = os.getenv("IG_USERNAME")
PASSWORD = os.getenv("IG_PASSWORD")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

POSTS_PER_DAY = 1
DB_NAME = "quotes.db"
SESSION_FILE = "session.json"

if not USERNAME or not PASSWORD or not GEMINI_API_KEY:
    raise RuntimeError("❌ Environment variables not loaded. Check .env or Render env settings.")


genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-2.5-flash")

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


def generate_new_quote():
    url = "https://zenquotes.io/api/random"
    data = requests.get(url, timeout=10).json()[0]
    return data["q"].strip(), data["a"].strip()

# ---------- Ensure One Unused Quote ----------
cur.execute("SELECT COUNT(*) FROM quotes WHERE used=0")
available = cur.fetchone()[0]

while available < POSTS_PER_DAY:
    try:
        quote, author = generate_new_quote()
        cur.execute(
            "INSERT INTO quotes (quote, author) VALUES (?, ?)",
            (quote, author)
        )
        conn.commit()
        available += 1
        print("Saved:", quote, "-", author)
    except:
        pass


def load_font(size):
    try:
        return ImageFont.truetype("arial.ttf", size)
    except:
        return ImageFont.load_default()

def generate_image(quote, author, filename):
    img = Image.new("RGB", (1080, 1080), "black")
    draw = ImageDraw.Draw(img)

    font_q = load_font(60)
    font_a = load_font(40)

    wrapped = textwrap.fill(quote, width=30)

    bbox = draw.multiline_textbbox((0, 0), wrapped, font=font_q)
    w = bbox[2] - bbox[0]
    h = bbox[3] - bbox[1]

    draw.multiline_text(
        ((1080 - w) / 2, (1080 - h) / 2),
        wrapped,
        fill="white",
        font=font_q,
        align="center"
    )

    author_text = f"- {author}"
    abox = draw.textbbox((0, 0), author_text, font=font_a)
    aw = abox[2] - abox[0]

    draw.text(
        ((1080 - aw) / 2, 920),
        author_text,
        fill="white",
        font=font_a
    )

    img.save(filename)


def generate_caption(quote):
    prompt = f"""
Create a very simple Instagram caption (one short sentence),
include two emojis related to the quote:
"{quote}"
Add ONLY 3 simple hashtags.
"""
    return model.generate_content(prompt).text.strip()


cl = Client()

if os.path.exists(SESSION_FILE):
    cl.load_settings(SESSION_FILE)
    cl.login(USERNAME, PASSWORD)
else:
    cl.login(USERNAME, PASSWORD)
    cl.dump_settings(SESSION_FILE)

# ---------- Fetch One Unused Quote ----------
cur.execute("SELECT id, quote, author FROM quotes WHERE used=0 LIMIT 1")
post = cur.fetchone()

if post:
    qid, quote, author = post

    image_name = "post.jpg"
    generate_image(quote, author, image_name)
    caption = generate_caption(quote)

    cl.photo_upload(image_name, caption)

    cur.execute("UPDATE quotes SET used=1 WHERE id=?", (qid,))
    conn.commit()

    print("Posted:", quote, "-", author)

conn.close()
