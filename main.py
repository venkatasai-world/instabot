import os
import base64
import sqlite3
import textwrap
import requests
from dotenv import load_dotenv
from instagrapi import Client
from PIL import Image, ImageDraw, ImageFont
import google.generativeai as genai

# ---------------- ENV ----------------
load_dotenv()

USERNAME = os.getenv("IG_USERNAME")
PASSWORD = os.getenv("IG_PASSWORD")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
SESSION_B64 = os.getenv("IG_SESSION")

DB_NAME = "quotes.db"
SESSION_FILE = "session.json"
FONT_PATH = os.path.join("fonts", "Poppins-Regular.ttf")

if not USERNAME or not PASSWORD or not GEMINI_API_KEY:
    raise RuntimeError("❌ Missing environment variables")

# ---------------- RESTORE SESSION ----------------
if SESSION_B64:
    with open(SESSION_FILE, "wb") as f:
        f.write(base64.b64decode(SESSION_B64))

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

# ---------------- FETCH QUOTE ----------------
def fetch_quote():
    data = requests.get(
        "https://zenquotes.io/api/random",
        timeout=10
    ).json()[0]
    return data["q"].strip(), data["a"].strip()

cur.execute("SELECT COUNT(*) FROM quotes WHERE used=0")
if cur.fetchone()[0] == 0:
    try:
        q, a = fetch_quote()
        cur.execute(
            "INSERT OR IGNORE INTO quotes (quote, author) VALUES (?, ?)",
            (q, a)
        )
        conn.commit()
    except:
        pass

# ---------------- FONT ----------------
def load_font(size):
    try:
        return ImageFont.truetype(FONT_PATH, size)
    except:
        return ImageFont.load_default()

# ---------------- IMAGE (PURE BLACK THEME) ----------------
def create_image(quote, author, filename):
    img = Image.new("RGB", (1080, 1080), "#000000")  # pure black
    draw = ImageDraw.Draw(img)

    quote_font = load_font(64)
    author_font = load_font(42)

    wrapped = textwrap.fill(quote, 28)

    bbox = draw.multiline_textbbox((0, 0), wrapped, font=quote_font, align="center")
    w = bbox[2] - bbox[0]
    h = bbox[3] - bbox[1]

    # Center quote
    draw.multiline_text(
        ((1080 - w) / 2, (1080 - h) / 2 - 40),
        wrapped,
        fill="#FFFFFF",
        font=quote_font,
        align="center"
    )

    # Author (subtle gray)
    author_text = f"- {author}"
    abox = draw.textbbox((0, 0), author_text, font=author_font)
    aw = abox[2] - abox[0]

    draw.text(
        ((1080 - aw) / 2, 780),
        author_text,
        fill="#BFBFBF",
        font=author_font
    )

    img.save(filename, quality=95)

# ---------------- CAPTION ----------------
def generate_caption(quote):
    prompt = f"""
Create a very simple Instagram caption.
One short sentence.
Use 2 emojis.
Add only 3 hashtags.

Quote: "{quote}"
"""
    return model.generate_content(prompt).text.strip()

# ---------------- INSTAGRAM LOGIN ----------------
cl = Client()

if os.path.exists(SESSION_FILE):
    cl.load_settings(SESSION_FILE)
    cl.login(USERNAME, PASSWORD, relogin=False)
else:
    cl.login(USERNAME, PASSWORD)

# ---------------- POST ----------------
cur.execute("SELECT id, quote, author FROM quotes WHERE used=0 LIMIT 1")
row = cur.fetchone()

if row:
    qid, quote, author = row

    image_name = "post.jpg"
    create_image(quote, author, image_name)

    caption = generate_caption(quote)
    cl.photo_upload(image_name, caption)

    cur.execute("UPDATE quotes SET used=1 WHERE id=?", (qid,))
    conn.commit()

    print("✅ Posted successfully (black theme)")

conn.close()
