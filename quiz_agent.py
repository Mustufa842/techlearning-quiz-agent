"""
================================================================================
  AUTONOMOUS CODING QUIZ VIDEO AGENT
  Generates quiz content → renders video → uploads to YouTube, Facebook, Instagram
  100% Free & Open-Source. No paid APIs required.
================================================================================

SETUP INSTRUCTIONS:
-------------------
1. Install dependencies:
   pip install moviepy Pillow google-auth-oauthlib google-api-python-client requests

2. Fill in your API credentials in the CONFIG section below.

3. YouTube OAuth Setup:
   - Go to https://console.cloud.google.com/
   - Create a project → Enable "YouTube Data API v3"
   - Create OAuth 2.0 credentials → Download as client_secrets.json
   - Place client_secrets.json in the same directory as this script.

4. Facebook/Instagram Setup:
   - Go to https://developers.facebook.com/
   - Create an App → Get a Page Access Token with pages_manage_posts permission
   - For Instagram: connect your Instagram Business Account to your Facebook Page
   - Get your Facebook Page ID and Instagram Business Account ID

5. Run: python quiz_agent.py
================================================================================
"""

import os
import random
import textwrap
import json
import time
import requests

# Load secrets from a local .env file (never commit .env to git)
from dotenv import load_dotenv
load_dotenv()

# ─── PIL / Pillow ────────────────────────────────────────────────────────────
from PIL import Image, ImageDraw, ImageFont

# ─── MoviePy 2.x (moviepy.editor was removed in v2) ─────────────────────────
try:
    # MoviePy 2.x
    from moviepy import ImageClip, VideoFileClip, concatenate_videoclips, CompositeVideoClip, ColorClip
except ImportError:
    # MoviePy 1.x fallback
    from moviepy.editor import ImageClip, VideoFileClip, concatenate_videoclips, CompositeVideoClip, ColorClip

# ─── Google / YouTube ────────────────────────────────────────────────────────
import google_auth_oauthlib.flow
import googleapiclient.discovery
import googleapiclient.errors
from googleapiclient.http import MediaFileUpload


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║                        CONFIGURATION SECTION                            ║
# ╚══════════════════════════════════════════════════════════════════════════╝

CONFIG = {
    # ── Video output ──────────────────────────────────────────────────────
    "output_video":       "quiz_output.mp4",
    "video_width":        1080,      # 9:16 → 1080x1920
    "video_height":       1920,
    "fps":                30,
    "quiz_display_sec":   8,         # seconds the quiz frame is shown
    "answer_display_sec": 5,         # seconds the answer frame is shown

    # ── Font paths (update to your system fonts or place .ttf in same dir) ─
    # On Windows: C:/Windows/Fonts/arial.ttf
    # On Linux:   /usr/share/fonts/truetype/dejavu/DejaVuSans.ttf
    # On macOS:   /System/Library/Fonts/Helvetica.ttc
    "font_regular":  "DejaVuSans.ttf",
    "font_bold":     "DejaVuSans-Bold.ttf",
    "font_mono":     "DejaVuSansMono.ttf",

    # ── YouTube ───────────────────────────────────────────────────────────
    "youtube_secrets_file": r"C:\Users\abid_\OneDrive\Desktop\client_secrets.json",
    "youtube_upload":       True,

    # ── Facebook Reels ────────────────────────────────────────────────────
    # TO ENABLE: fill in FB_ACCESS_TOKEN / FB_PAGE_ID in your .env then set "facebook_upload": True
    # Get token from: https://developers.facebook.com/tools/explorer/
    "fb_access_token": os.environ.get("FB_ACCESS_TOKEN"),
    "fb_page_id":      os.environ.get("FB_PAGE_ID"),
    "facebook_upload": False,   # ← set True once token is filled in

    # ── Instagram Reels ───────────────────────────────────────────────────
    # TO ENABLE: fill in IG_ACCESS_TOKEN / IG_USER_ID in your .env then set "instagram_upload": True
    "ig_access_token": os.environ.get("IG_ACCESS_TOKEN"),
    "ig_user_id":      os.environ.get("IG_USER_ID"),
    "instagram_upload": False,  # ← set True once token is filled in

    # ── Make.com Webhook (posts to Instagram + Facebook via Make automation) ─────────
    # 1. Create scenario at make.com
    # 2. Add Webhook module → copy the URL → put it in your .env as MAKE_WEBHOOK_URL
    # 3. Add Instagram + Facebook modules in Make
    # 4. Set make_upload to True
    "make_webhook_url": os.environ.get("MAKE_WEBHOOK_URL"),
    "make_upload":      True,
    "make_image_only":  False,    # Always False — post as Reel (video)
    "make_song":        "LUZ ROJA by bxkq",  # Song in caption
    "make_pin_comment": True,     # Pin A/B/C/D vote options as first comment

    # ── Background music (baked into every video) ─────────────────────────────
    # Place these MP3 files on your Desktop — script alternates between them.
    # Song 1: INSONAMIA (SLOWED)   → sfx_background.mp3
    # Song 2: LUZ ROJA by bxkq    → sfx_background2.mp3
    "bg_music": [
        r"C:\Users\abid_\OneDrive\Desktop\sfx_background.mp3",
        r"C:\Users\abid_\OneDrive\Desktop\sfx_background2.mp3",
    ],
    "bg_music_volume": 0.85,   # 0.0 = silent, 1.0 = full volume
    "tick_volume":     0.30,   # tick/buzzer volume when mixed with song

    # ── Platform video specs (auto-applied per platform) ─────────────────────
    # YouTube Shorts : 1080x1920  9:16  up to 60s  H.264
    # Instagram Reels: 1080x1920  9:16  up to 90s  H.264  max 650MB
    # Facebook Reels : 1080x1920  9:16  up to 90s  H.264  max 1GB
    # All platforms use same 9:16 resolution — we render once and reuse.
    # Bitrate is adjusted per platform for size compliance.
    "platform_specs": {
        "youtube":   {"width": 1080, "height": 1920, "fps": 30, "bitrate": "4000k"},
        "instagram": {"width": 1080, "height": 1920, "fps": 30, "bitrate": "3500k"},
        "facebook":  {"width": 1080, "height": 1920, "fps": 30, "bitrate": "4000k"},
        "make":      {"width": 1080, "height": 1920, "fps": 30, "bitrate": "3500k"},
    },
}


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║                  QUIZ CONTENT DATABASE (Zero-Cost, Local)               ║
# ╚══════════════════════════════════════════════════════════════════════════╝

# Quiz templates are stored in quiz_templates.py
# Add new quizzes there — this file stays clean.
from quiz_templates import QUIZ_TEMPLATES
# ╔══════════════════════════════════════════════════════════════════════════╗
# ║                     STEP 1 — CONTENT GENERATION                         ║
# ╚══════════════════════════════════════════════════════════════════════════╝

import hashlib

# ╔══════════════════════════════════════════════════════════════════════════╗
# ║              SQL SERVER (LocalDB) DATABASE LAYER                         ║
# ║  Server : (localdb)\MSSQLLocalDB                                         ║
# ║  DB     : smartquizsystem                                                ║
# ║  Table  : askedquestion                                                  ║
# ╚══════════════════════════════════════════════════════════════════════════╝

DB_SERVER = r"(localdb)\MSSQLLocalDB"
DB_NAME   = "smartquizsystem"

# Connection string — uses Windows Authentication (no username/password needed)
DB_CONN_STR = (
    f"DRIVER={{ODBC Driver 17 for SQL Server}};"
    f"SERVER={DB_SERVER};"
    f"DATABASE={DB_NAME};"
    f"Trusted_Connection=yes;"
)


def db_connect():
    """Open and return a pyodbc connection to SQL Server LocalDB."""
    try:
        import pyodbc
        return pyodbc.connect(DB_CONN_STR)
    except ImportError:
        raise RuntimeError(
            "pyodbc is not installed.\n"
            "Run:  pip install pyodbc\n"
            "Also ensure 'ODBC Driver 17 for SQL Server' is installed:\n"
            "https://learn.microsoft.com/en-us/sql/connect/odbc/download-odbc-driver-for-sql-server"
        )


def db_init():
    """
    Create the 'askedquestion' table in smartquizsystem if it doesn't exist.
    Also creates the database itself if LocalDB doesn't have it yet.
    """
    import pyodbc

    # First connect to master to create DB if missing
    master_conn_str = (
        f"DRIVER={{ODBC Driver 17 for SQL Server}};"
        f"SERVER={DB_SERVER};"
        f"DATABASE=master;"
        f"Trusted_Connection=yes;"
    )
    try:
        conn = pyodbc.connect(master_conn_str, autocommit=True)
        cur = conn.cursor()
        cur.execute(
            "IF NOT EXISTS (SELECT name FROM sys.databases WHERE name = ?) "
            "CREATE DATABASE [smartquizsystem]",
            DB_NAME,
        )
        conn.close()
    except Exception as e:
        print(f"[DB] Warning during DB creation check: {e}")

    # Now connect to smartquizsystem and create the table
    conn = db_connect()
    cur = conn.cursor()
    cur.execute("""
        IF NOT EXISTS (
            SELECT * FROM INFORMATION_SCHEMA.TABLES
            WHERE TABLE_NAME = 'askedquestion'
        )
        CREATE TABLE askedquestion (
            id             INT           IDENTITY(1,1) PRIMARY KEY,
            quiz_hash      NVARCHAR(32)  UNIQUE NOT NULL,
            language       NVARCHAR(50)  NOT NULL,
            question_type  NVARCHAR(100) NOT NULL,
            code_snippet   NVARCHAR(MAX) NOT NULL,
            correct_answer NVARCHAR(10),
            youtube_id     NVARCHAR(100),
            facebook_id    NVARCHAR(100),
            instagram_id   NVARCHAR(100),
            upload_status  NVARCHAR(20)  NOT NULL DEFAULT 'pending',
            uploaded_at    DATETIME      DEFAULT GETDATE(),
            cycle_number   INT           DEFAULT 1
        )
    """)
    conn.commit()
    conn.close()
    print(f"[DB] Connected to [{DB_SERVER}].[{DB_NAME}].askedquestion ✅")


def db_quiz_hash(q: dict) -> str:
    """Stable MD5 hash for a quiz based on language + type + code."""
    key = f"{q['language']}::{q['question_type']}::{q['code'].strip()}"
    return hashlib.md5(key.encode()).hexdigest()


def db_get_used_hashes() -> set:
    """Return hashes of all quizzes already successfully uploaded."""
    conn = db_connect()
    cur = conn.cursor()
    cur.execute(
        "SELECT quiz_hash FROM askedquestion WHERE upload_status = 'success'"
    )
    rows = cur.fetchall()
    conn.close()
    return {r[0] for r in rows}


def db_get_current_cycle() -> int:
    """Get the current cycle number from the DB."""
    conn = db_connect()
    cur = conn.cursor()
    cur.execute("SELECT ISNULL(MAX(cycle_number), 1) FROM askedquestion")
    cycle = cur.fetchone()[0]
    conn.close()
    return cycle


def db_insert_question(q: dict, status: str = "pending") -> int:
    """
    Insert a new record into askedquestion.
    Returns the new row's ID.
    """
    h = db_quiz_hash(q)
    cycle = db_get_current_cycle()
    conn = db_connect()
    cur = conn.cursor()

    # Check if already exists (from a previous failed attempt)
    cur.execute("SELECT id FROM askedquestion WHERE quiz_hash = ?", h)
    existing = cur.fetchone()
    if existing:
        conn.close()
        return existing[0]

    cur.execute("""
        INSERT INTO askedquestion
            (quiz_hash, language, question_type, code_snippet,
             correct_answer, upload_status, cycle_number)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        h,
        q["language"],
        q["question_type"],
        q["code"],
        q.get("correct", ""),
        status,
        cycle,
    ))
    conn.commit()

    cur.execute("SELECT @@IDENTITY")
    new_id = int(cur.fetchone()[0])
    conn.close()
    return new_id


def db_mark_uploaded(q: dict, results: dict):
    """
    Update the askedquestion row with platform IDs and mark as success.
    results = {"youtube": "abc123", "facebook": "def456", ...}
    """
    h = db_quiz_hash(q)
    conn = db_connect()
    cur = conn.cursor()
    cur.execute("""
        UPDATE askedquestion SET
            upload_status  = 'success',
            youtube_id     = ?,
            facebook_id    = ?,
            instagram_id   = ?,
            uploaded_at    = GETDATE()
        WHERE quiz_hash = ?
    """, (
        str(results.get("youtube",  "") or ""),
        str(results.get("facebook", "") or ""),
        str(results.get("instagram","") or ""),
        h,
    ))
    conn.commit()
    conn.close()
    print(f"[DB] ✅ Record saved → askedquestion | hash={h[:8]}...")


def db_reset_cycle():
    """Increment cycle number — called when all quizzes are exhausted."""
    conn = db_connect()
    cur = conn.cursor()
    cur.execute("SELECT ISNULL(MAX(cycle_number), 1) FROM askedquestion")
    current = cur.fetchone()[0]
    new_cycle = current + 1
    # We don't delete records — just bump the cycle so used_hashes resets
    conn.close()
    print(f"[DB] 🔄 All quizzes used! Starting cycle {new_cycle}...")
    return new_cycle


def db_print_stats():
    """Print a formatted summary of all records in askedquestion."""
    conn = db_connect()
    cur = conn.cursor()

    print("\n" + "=" * 72)
    print("  smartquizsystem → askedquestion  |  UPLOAD HISTORY")
    print("=" * 72)
    print(f"  {'#':<4} {'Language':<14} {'Type':<22} {'Status':<10} {'YouTube ID':<14} {'Date'}")
    print("  " + "-" * 68)

    cur.execute("""
        SELECT TOP 20 id, language, question_type, upload_status,
                      youtube_id, uploaded_at
        FROM askedquestion
        ORDER BY uploaded_at DESC
    """)
    rows = cur.fetchall()
    if not rows:
        print("  No records yet.")
    else:
        for r in rows:
            yt = (r[4] or "")[:12]
            dt = str(r[5])[:16] if r[5] else "—"
            print(f"  {r[0]:<4} {r[1]:<14} {r[2]:<22} {r[3]:<10} {yt:<14} {dt}")

    cur.execute("SELECT COUNT(*) FROM askedquestion")
    total = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM askedquestion WHERE upload_status='success'")
    success = cur.fetchone()[0]
    cur.execute("SELECT ISNULL(MAX(cycle_number),1) FROM askedquestion")
    cycle = cur.fetchone()[0]

    print(f"\n  Total records   : {total}")
    print(f"  Successful      : {success}")
    print(f"  Current cycle   : {cycle}")
    print("=" * 72)
    conn.close()


def generate_quiz():
    """Pick a quiz never successfully uploaded — checks askedquestion table."""
    db_init()

    used_hashes = db_get_used_hashes()
    available   = [q for q in QUIZ_TEMPLATES if db_quiz_hash(q) not in used_hashes]

    # ── All quizzes used → reset cycle ────────────────────────────────────────
    if not available:
        db_reset_cycle()
        available = QUIZ_TEMPLATES[:]

    # ── Pick random unused quiz ───────────────────────────────────────────────
    quiz = random.choice(available)

    total     = len(QUIZ_TEMPLATES)
    used      = len(used_hashes)
    remaining = total - used if available else total

    print(f"\n[QUIZ] Language  : {quiz['language']}")
    print(f"[QUIZ] Type      : {quiz['question_type']}")
    print(f"[QUIZ] DB Status : {used}/{total} used | {remaining} remaining")

    # Insert as 'pending' immediately — prevents duplicate picks on parallel runs
    row_id = db_insert_question(quiz, status="pending")
    print(f"[DB]  Inserted → askedquestion row id={row_id}")

    return quiz


def mark_quiz_uploaded(quiz: dict, results: dict):
    """Update DB record to 'success' with all platform IDs."""
    db_mark_uploaded(quiz, results)
    db_print_stats()


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║                     STEP 2 — VIDEO CREATION                             ║
# ╚══════════════════════════════════════════════════════════════════════════╝

# ── Design constants ──────────────────────────────────────────────────────────
BG_COLOR        = (15, 15, 25)       # near-black background
ACCENT_COLOR    = (99, 235, 170)     # green accent
CARD_COLOR      = (25, 28, 45)       # card / code box bg
HEADER_COLOR    = (45, 48, 75)       # top bar color
TEXT_WHITE      = (240, 240, 250)
TEXT_GRAY       = (160, 165, 185)
CORRECT_COLOR   = (99, 235, 130)
OPTION_COLORS   = [
    (60, 110, 200),   # A - blue
    (200, 80, 80),    # B - red
    (80, 180, 80),    # C - green
    (200, 150, 50),   # D - amber
]

LETTER_LABELS = ["A", "B", "C", "D"]


def _load_font(path: str, size: int) -> ImageFont.FreeTypeFont:
    """Load a font, falling back to default if not found."""
    try:
        return ImageFont.truetype(path, size)
    except (IOError, OSError):
        # Pillow 10+ load_default accepts size; older versions ignore it
        try:
            return ImageFont.load_default(size=size)
        except TypeError:
            return ImageFont.load_default()


def _draw_rounded_rect(draw, xy, radius=20, fill=None, outline=None, width=2):
    """Draw a rounded rectangle on a PIL ImageDraw object."""
    x0, y0, x1, y1 = xy
    draw.rounded_rectangle([x0, y0, x1, y1], radius=radius, fill=fill, outline=outline, width=width)


def _wrap_code(code: str, max_chars: int = 42) -> list[str]:
    """
    Prepare code lines for display:
      1. Skip full-line comments (// or #) that are too long — they clutter display
      2. Hard-wrap any remaining lines that exceed max_chars
      3. Collapse consecutive blank lines into one
    """
    result = []
    prev_blank = False

    for raw_line in code.split("\n"):
        stripped = raw_line.strip()

        # Skip pure comment lines that are too long (they are usually explanatory text)
        if len(raw_line) > max_chars:
            is_comment = (
                stripped.startswith("//") or
                stripped.startswith("#") or
                stripped.startswith("/*") or
                stripped.startswith("*")
            )
            if is_comment:
                # Shorten to a truncated version so viewer knows line existed
                short = raw_line[:max_chars - 3] + "..."
                result.append(short)
                prev_blank = False
                continue

        # Collapse multiple blank lines into one
        if stripped == "":
            if not prev_blank:
                result.append("")
            prev_blank = True
            continue
        prev_blank = False

        # Hard-wrap lines that are still too long
        line = raw_line
        while len(line) > max_chars:
            result.append(line[:max_chars])
            line = "    " + line[max_chars:]
        result.append(line)

    # Remove leading/trailing blank lines
    while result and result[0] == "":
        result.pop(0)
    while result and result[-1] == "":
        result.pop()

    return result


def _text_width(draw: ImageDraw.ImageDraw, text: str, font) -> int:
    """Return text width — compatible with Pillow 9.x and 10.x."""
    try:
        return int(draw.textlength(text, font=font))
    except AttributeError:
        # Pillow < 9.2
        return draw.textsize(text, font=font)[0]


def _draw_gradient_bg(img: Image.Image, top_color: tuple, bottom_color: tuple):
    """Draw a vertical gradient background using PIL."""
    W, H = img.size
    draw = ImageDraw.Draw(img)
    for y in range(H):
        t = y / H
        r = int(top_color[0] + (bottom_color[0] - top_color[0]) * t)
        g = int(top_color[1] + (bottom_color[1] - top_color[1]) * t)
        b = int(top_color[2] + (bottom_color[2] - top_color[2]) * t)
        draw.line([(0, y), (W, y)], fill=(r, g, b))


def _draw_glow_rect(img: Image.Image, xy: list, radius: int, color: tuple, glow_radius: int = 18):
    """Draw a rounded rect with a soft glow effect using multiple alpha layers."""
    from PIL import ImageFilter
    glow_layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow_layer)
    for i in range(glow_radius, 0, -1):
        alpha = int(60 * (1 - i / glow_radius))
        expand = i
        gd.rounded_rectangle(
            [xy[0] - expand, xy[1] - expand, xy[2] + expand, xy[3] + expand],
            radius=radius + expand,
            fill=(*color, alpha),
        )
    blurred = glow_layer.filter(ImageFilter.GaussianBlur(radius=glow_radius // 2))
    img.paste(Image.alpha_composite(Image.new("RGBA", img.size, (0,0,0,0)), blurred),
              mask=blurred.split()[3])



# ── shared drawing helpers ────────────────────────────────────────────────────

def _gold_header(draw, x1, y1, x2, y2, text, font, GOLD, GOLD_DIM):
    """Draw a gold-bordered header bar with centred text."""
    W_full = x2 - x1
    draw.rounded_rectangle([x1, y1, x2, y2], radius=14, fill=(14,30,82,255))
    draw.rounded_rectangle([x1, y1, x2, y2], radius=14, outline=GOLD, width=3)
    draw.rounded_rectangle([x1, y1, x2, y1+8], radius=14, fill=GOLD)
    tw = draw.textlength(text, font=font) if hasattr(draw, 'textlength') else font.getlength(text)
    cx = x1 + (W_full - tw) // 2
    draw.text((cx, y1 + (y2-y1-font.size)//2 + 2), text, font=font, fill=GOLD)


def _option_card(draw, x1, y1, x2, y2, letter, text, font_lbl, font_opt,
                 GOLD, SILVER, pulse_border, locked):
    """Draw a single metallic option card."""
    draw.rounded_rectangle([x1,   y1,   x2,   y2],           radius=12, fill=(68,78,100))
    draw.rounded_rectangle([x1,   y1,   x2,   y1+(y2-y1)//2],radius=12, fill=(90,104,128))
    draw.rounded_rectangle([x1+1, y1+1, x2-1, y2-1],         radius=11, fill=(46,54,74))
    draw.rounded_rectangle([x1,   y1,   x2,   y2],           radius=12,
                            outline=pulse_border if not locked else (68,78,100), width=2)
    # Letter circle
    cx = x1 + 44; cy = y1 + (y2-y1)//2
    draw.ellipse([cx-22, cy-22, cx+22, cy+22], fill=(10,20,58))
    draw.ellipse([cx-22, cy-22, cx+22, cy+22], outline=GOLD, width=2)
    lw = draw.textlength(letter, font=font_lbl) if hasattr(draw,'textlength') else len(letter)*14
    draw.text((cx-lw//2, cy-17), letter, font=font_lbl, fill=GOLD)
    # Text
    col = (108,118,140) if locked else SILVER
    draw.text((x1+78, y1+(y2-y1-font_opt.size)//2+2), text, font=font_opt, fill=col)


# ══════════════════════════════════════════════════════════════════════════════
# FRAME 1 — animated quiz frame
# ══════════════════════════════════════════════════════════════════════════════

def render_quiz_frame(quiz: dict, cfg: dict) -> str:
    """Static quiz frame (unused by animated path, kept for compatibility)."""
    img = render_quiz_frame_at(quiz, cfg, 0.0, cfg["quiz_display_sec"])
    out = "frame_quiz.png"
    img.save(out)
    return out


def render_quiz_frame_at(quiz: dict, cfg: dict, elapsed: float, total: float) -> Image.Image:
    """
    Animated quiz frame.
    Layout is fully data-driven — sections packed tightly with only
    a fixed 14px gap between each, zero empty bottom space.
    """
    import math

    W, H      = cfg["video_width"], cfg["video_height"]
    remaining = max(0.0, total - elapsed)
    fraction  = remaining / total
    locked    = remaining <= 0

    img  = Image.new("RGBA", (W, H))
    _draw_gradient_bg(img, (4, 12, 40), (6, 20, 58))
    img  = img.convert("RGBA")
    draw = ImageDraw.Draw(img)

    GOLD     = (255, 210, 60)
    GOLD_DIM = (175, 138, 18)
    GOLD_DRK = (68,  50,   4)
    SILVER   = (200, 210, 226)
    BLUE_LT  = (120, 178, 255)

    pad  = 38
    GAP  = 14   # fixed gap between every section

    # ── measure code lines first so we can size fonts ─────────────────────────
    code_lines = _wrap_code(quiz["code"], max_chars=42)[:10]
    n_lines    = len(code_lines)

    # ── fonts ─────────────────────────────────────────────────────────────────
    # ── Auto-scale fonts based on code length ─────────────────────────────────
    # Fewer lines = bigger fonts, more lines = smaller to fit
    if n_lines <= 4:
        code_sz, lnum_sz, lhc = 28, 20, 34
    elif n_lines <= 6:
        code_sz, lnum_sz, lhc = 26, 18, 32
    elif n_lines <= 8:
        code_sz, lnum_sz, lhc = 24, 17, 30
    else:
        code_sz, lnum_sz, lhc = 22, 16, 28

    f_hdr   = _load_font(cfg["font_bold"],    40)
    f_tag   = _load_font(cfg["font_bold"],    26)
    f_lang  = _load_font(cfg["font_bold"],    23)
    f_code  = _load_font(cfg["font_mono"],    code_sz)
    f_lnum  = _load_font(cfg["font_mono"],    lnum_sz)
    f_opt   = _load_font(cfg["font_bold"],    28)
    f_lbl   = _load_font(cfg["font_bold"],    25)
    f_cta   = _load_font(cfg["font_bold"],    31)
    f_timer = _load_font(cfg["font_bold"],    62)
    f_tsub  = _load_font(cfg["font_bold"],    20)
    f_brand = _load_font(cfg["font_regular"], 22)

    # ── fixed section heights ──────────────────────────────────────────────────
    HDR_H   = 98                        # header bar
    TAG_H   = 40                        # question-type tag
    CODE_H  = n_lines * lhc + 34       # code block (dynamic, scaled)
    ACL_H   = 34                        # "answer choices" label
    OPT_H   = 4 * 78 + 3 * 8           # options
    RING_H  = 24 + 24 + (56*2) + 24    # TIMER label + ring + SECONDS LEFT
    CTA_H   = 56                        # button
    BRAND_H = 82                        # branding strip
    GAPS    = GAP * 7                   # 7 gaps between 8 sections

    TOTAL   = HDR_H + TAG_H + CODE_H + ACL_H + OPT_H + RING_H + CTA_H + BRAND_H + GAPS
    # Distribute leftover evenly as top margin
    TOP_MARGIN = max(14, (H - TOTAL) // 2)

    y = TOP_MARGIN

    # ── 1. HEADER BAR ─────────────────────────────────────────────────────────
    draw.rounded_rectangle([pad-10, y, W-pad+10, y+HDR_H], radius=14, fill=(14,30,82,255))
    draw.rounded_rectangle([pad-10, y, W-pad+10, y+HDR_H], radius=14, outline=GOLD, width=3)
    draw.rounded_rectangle([pad-10, y, W-pad+10, y+8],     radius=14, fill=GOLD)

    hdr_txt = "QUIZ QUESTION"
    hw = _text_width(draw, hdr_txt, f_hdr)
    draw.text(((W-hw)//2, y+30), hdr_txt, font=f_hdr, fill=GOLD)

    # Language badge
    lang = quiz["language"]
    lw   = _text_width(draw, lang, f_lang)
    lbx1 = W - pad - lw - 26
    draw.rounded_rectangle([lbx1-6, y+28, lbx1+lw+16, y+78], radius=9, fill=(8,22,68,220))
    draw.rounded_rectangle([lbx1-6, y+28, lbx1+lw+16, y+78], radius=9, outline=GOLD, width=2)
    draw.text((lbx1+5, y+42), lang, font=f_lang, fill=GOLD)

    y += HDR_H + GAP

    # ── 2. QUESTION TYPE TAG ──────────────────────────────────────────────────
    qtxt = f"?  {quiz['question_type'].upper()}"
    qtw  = _text_width(draw, qtxt, f_tag)
    draw.rounded_rectangle([pad-4, y, pad+qtw+20, y+TAG_H], radius=8, fill=(12,28,82,220))
    draw.rounded_rectangle([pad-4, y, pad+qtw+20, y+TAG_H], radius=8, outline=GOLD_DIM, width=2)
    draw.text((pad+8, y+8), qtxt, font=f_tag, fill=GOLD)

    y += TAG_H + GAP

    # ── 3. CODE BLOCK ─────────────────────────────────────────────────────────
    draw.rounded_rectangle([pad-6, y, W-pad+6, y+CODE_H], radius=11, fill=(3,9,28,255))
    draw.rounded_rectangle([pad-6, y, W-pad+6, y+CODE_H], radius=11, outline=GOLD_DIM, width=2)
    draw.rounded_rectangle([pad-6, y, W-pad+6, y+10],     radius=11, fill=GOLD_DIM)
    for di, dc in enumerate([(210,70,70),(210,170,50),(70,190,90)]):
        draw.ellipse([pad+4+di*18, y+1, pad+14+di*18, y+11], fill=dc)

    for i, line in enumerate(code_lines):
        ry = y + 16 + i*lhc
        draw.text((pad+0,  ry), str(i+1), font=f_lnum, fill=(88,106,142))
        draw.text((pad+28, ry), line,      font=f_code, fill=(172,202,252))

    y += CODE_H + GAP

    # ── 4. ANSWER CHOICES LABEL ───────────────────────────────────────────────
    ac_txt = "ANSWER CHOICES"
    acw    = _text_width(draw, ac_txt, f_tag)
    draw.text(((W-acw)//2, y+4), ac_txt, font=f_tag, fill=GOLD)

    y += ACL_H + GAP

    # ── 5. OPTIONS ────────────────────────────────────────────────────────────
    opt_h_each = 82
    for i, option in enumerate(quiz["options"]):
        by1 = y
        by2 = y + opt_h_each
        phase  = (elapsed*1.4 + i*0.55) % (2*3.14159)
        pv     = int(8 + 6*abs(math.sin(phase))) if not locked else 0
        bc     = (165+pv, 178+pv, 200+pv)
        opt_raw = option[3:] if len(option)>2 and option[1]==')' else option
        opt_txt = opt_raw if len(opt_raw)<=40 else opt_raw[:38]+"…"
        _option_card(draw, pad, by1, W-pad, by2,
                     LETTER_LABELS[i], opt_txt, f_lbl, f_opt, GOLD, SILVER, bc, locked)
        y += opt_h_each + 8

    y += GAP

    # ── 6. TIMER RING ─────────────────────────────────────────────────────────
    rr = 56; rw = 9; ring_cx = W//2

    # "TIMER" above
    tl  = "TIMER"
    tlw = _text_width(draw, tl, f_tsub)
    draw.text((ring_cx-tlw//2, y), tl, font=f_tsub, fill=GOLD)
    y += 26

    ring_cy = y + rr
    # Timer colour
    tc = (255,140,0) if fraction>0.4 else (255, int(90*(fraction/0.4)), 0)

    draw.ellipse([ring_cx-rr-8, ring_cy-rr-8, ring_cx+rr+8, ring_cy+rr+8], fill=(6,16,50,220))
    draw.ellipse([ring_cx-rr-8, ring_cy-rr-8, ring_cx+rr+8, ring_cy+rr+8], outline=GOLD_DIM, width=2)
    draw.ellipse([ring_cx-rr, ring_cy-rr, ring_cx+rr, ring_cy+rr],
                 outline=(26,36,66), width=rw)
    if fraction > 0.005:
        draw.arc([ring_cx-rr, ring_cy-rr, ring_cx+rr, ring_cy+rr],
                 start=-90, end=-90+fraction*360, fill=tc, width=rw)

    secs = f"{int(math.ceil(remaining)):02d}"
    sw   = _text_width(draw, secs, f_timer)
    draw.text((ring_cx-sw//2, ring_cy-36), secs, font=f_timer, fill=tc)

    y = ring_cy + rr + 10

    # "SECONDS LEFT" below
    sl  = "SECONDS LEFT"
    slw = _text_width(draw, sl, f_tsub)
    draw.text((ring_cx-slw//2, y), sl, font=f_tsub, fill=GOLD)
    y += 26 + GAP

    # ── 7. CTA / LOCK ─────────────────────────────────────────────────────────
    if locked:
        draw.rounded_rectangle([pad, y, W-pad, y+CTA_H], radius=13, fill=(115,14,14,235))
        draw.rounded_rectangle([pad, y, W-pad, y+CTA_H], radius=13, outline=(218,55,55), width=2)
        lt  = "TIME'S UP!  Answer Locked!"
        ltw = _text_width(draw, lt, f_cta)
        draw.text(((W-ltw)//2, y+12), lt, font=f_cta, fill=(255,200,200))
    else:
        cta  = "COMMENT YOUR ANSWER  +"
        ctaw = _text_width(draw, cta, f_cta)
        cx1  = (W-ctaw-44)//2; cx2 = cx1+ctaw+44
        draw.rounded_rectangle([cx1+3, y+3, cx2+3, y+CTA_H+2], radius=15, fill=(38,26,0,155))
        draw.rounded_rectangle([cx1,   y,   cx2,   y+CTA_H-2], radius=15, fill=GOLD_DIM)
        draw.rounded_rectangle([cx1,   y,   cx2,   y+26],      radius=15, fill=GOLD)
        draw.rounded_rectangle([cx1+2, y+2, cx2-2, y+CTA_H-4], radius=13, outline=GOLD_DRK, width=1)
        draw.text((cx1+18, y+12), cta, font=f_cta, fill=(14,9,0))

    y += CTA_H + GAP

    # ── 8. BRANDING ───────────────────────────────────────────────────────────
    # Pin to actual bottom
    by = H - BRAND_H
    draw.rectangle([0, by,   W, H],   fill=(4,10,36,240))
    draw.rectangle([0, by,   W, by+2],fill=GOLD_DIM)
    brand = "@TechLearning  |  Like & Follow for daily quizzes!"
    bfw   = _text_width(draw, brand, f_brand)
    draw.text(((W-bfw)//2, by+28), brand, font=f_brand, fill=GOLD)

    return img.convert("RGB")


# ══════════════════════════════════════════════════════════════════════════════
# FRAME 2 — answer reveal
# ══════════════════════════════════════════════════════════════════════════════

def render_answer_frame(quiz: dict, cfg: dict) -> str:
    """
    Answer reveal frame — completely rewritten layout.
    Fixed issues:
      - Answer text no longer overflows at top
      - All sections calculated with exact pixel budgets
      - Fonts sized to never overlap
      - Explanation card fills remaining space cleanly
    """
    W, H = cfg["video_width"], cfg["video_height"]

    img  = Image.new("RGBA", (W, H))
    _draw_gradient_bg(img, (4, 12, 40), (6, 20, 58))
    img  = img.convert("RGBA")
    draw = ImageDraw.Draw(img)

    # ── Colour palette ────────────────────────────────────────────────────────
    GOLD     = (255, 210, 60)
    GOLD_DIM = (175, 138, 18)
    GREEN    = (55,  225, 85)
    GREEN_D  = (15,  100, 28)
    RED      = (200,  50, 50)
    WHITE    = (255, 255, 255)
    SILVER   = (165, 178, 196)
    DIM_TXT  = (90,  105, 128)
    BLUE_BG  = (14,  30,  82, 255)

    pad      = 38
    GAP      = 14
    BRAND_H  = 84

    # ── Fonts — all sized to prevent overflow ─────────────────────────────────
    f_hdr   = _load_font(cfg["font_bold"],    40)   # header
    f_sub   = _load_font(cfg["font_bold"],    28)   # section labels
    f_corr  = _load_font(cfg["font_bold"],    32)   # correct answer text
    f_ans   = _load_font(cfg["font_bold"],    28)   # answer option text
    f_lbl   = _load_font(cfg["font_bold"],    24)   # letter badges
    f_opt   = _load_font(cfg["font_bold"],    24)   # wrong option text
    f_exp   = _load_font(cfg["font_regular"], 28)   # explanation
    f_why   = _load_font(cfg["font_bold"],    28)   # WHY label
    f_brand = _load_font(cfg["font_regular"], 22)   # branding

    # ── Pre-calculate all section heights ─────────────────────────────────────
    HDR_H    = 96    # header bar
    ROW2_H   = 44    # "CORRECT ANSWER" + badge row
    BAR_H    = 110   # green correct answer bar (taller for 2 lines of text)
    GRID_H   = 170   # 2-row wrong options grid (2 × 80 + gap)
    DESC_H   = 46    # "DESCRIPTION" label
    # Explanation card gets whatever is left
    USED     = (20 + HDR_H + GAP + ROW2_H + GAP +
                BAR_H + GAP + GRID_H + GAP + DESC_H + GAP + BRAND_H + 10)
    EXP_H    = max(200, H - USED)

    y = 20

    # ══════════════════════════════════════════════════════════════════════════
    # 1. HEADER BAR
    # ══════════════════════════════════════════════════════════════════════════
    draw.rounded_rectangle([pad-10, y, W-pad+10, y+HDR_H],
                            radius=14, fill=BLUE_BG)
    draw.rounded_rectangle([pad-10, y, W-pad+10, y+HDR_H],
                            radius=14, outline=GOLD, width=3)
    draw.rounded_rectangle([pad-10, y, W-pad+10, y+8],
                            radius=14, fill=GOLD)
    hdr = "CORRECT ANSWER & EXPLANATION"
    hw  = _text_width(draw, hdr, f_hdr)
    draw.text(((W-hw)//2, y+30), hdr, font=f_hdr, fill=GOLD)

    y += HDR_H + GAP

    # ══════════════════════════════════════════════════════════════════════════
    # 2. "CORRECT ANSWER" label + green "CORRECT!" badge — same row
    # ══════════════════════════════════════════════════════════════════════════
    draw.text((pad+4, y+7), "CORRECT ANSWER", font=f_sub, fill=GOLD)

    badge = "CORRECT!"
    bw    = _text_width(draw, badge, f_sub)
    bx1   = W - pad - bw - 50
    draw.rounded_rectangle([bx1, y, bx1+bw+44, y+ROW2_H],
                            radius=10, fill=(16, 75, 22, 220))
    draw.rounded_rectangle([bx1, y, bx1+bw+44, y+ROW2_H],
                            radius=10, outline=GREEN, width=2)
    draw.text((bx1+12, y+7), badge, font=f_sub, fill=GREEN)
    # Checkmark inside badge
    ckx = bx1 + bw + 28
    draw.line([(ckx-8, y+24), (ckx-2, y+34), (ckx+10, y+14)],
              fill=GREEN, width=3)

    y += ROW2_H + GAP

    # ══════════════════════════════════════════════════════════════════════════
    # 3. GREEN CORRECT ANSWER BAR
    #    Layout: [CORRECT! ✓] [circle:A] [answer text — 2 lines max]
    # ══════════════════════════════════════════════════════════════════════════
    ans_letter  = quiz["correct"]
    correct_opt = next((o for o in quiz["options"] if o.startswith(ans_letter)), "")
    opt_text    = correct_opt[3:] if len(correct_opt) > 2 else correct_opt

    draw.rounded_rectangle([pad, y, W-pad, y+BAR_H],
                            radius=13, fill=(16, 125, 34, 235))
    draw.rounded_rectangle([pad, y, W-pad, y+BAR_H],
                            radius=13, outline=GREEN, width=3)
    # Highlight top stripe
    draw.rounded_rectangle([pad, y, W-pad, y+40],
                            radius=13, fill=(26, 168, 48, 180))

    # "CORRECT!" label
    draw.text((pad+14, y+12), "CORRECT!", font=f_corr, fill=WHITE)

    # Checkmark circle
    ckc_x = pad + 172; ckc_y = y + BAR_H//2
    draw.ellipse([ckc_x-18, ckc_y-18, ckc_x+18, ckc_y+18], fill=GREEN_D)
    draw.ellipse([ckc_x-18, ckc_y-18, ckc_x+18, ckc_y+18],
                 outline=WHITE, width=2)
    draw.line([(ckc_x-8, ckc_y+2), (ckc_x-2, ckc_y+10),
               (ckc_x+9, ckc_y-8)], fill=WHITE, width=3)

    # Letter circle
    lc_x = pad + 218; lc_y = y + BAR_H//2
    draw.ellipse([lc_x-18, lc_y-18, lc_x+18, lc_y+18], fill=(8, 18, 52))
    draw.ellipse([lc_x-18, lc_y-18, lc_x+18, lc_y+18],
                 outline=GOLD, width=2)
    alf  = _load_font(cfg["font_bold"], 24)
    alfw = _text_width(draw, ans_letter, alf)
    draw.text((lc_x - alfw//2, lc_y - 14), ans_letter, font=alf, fill=GOLD)

    # Answer text — wrap into 2 lines, max 18 chars each
    ans_lines = textwrap.wrap(opt_text, width=22)[:2]
    ans_x     = pad + 248
    ans_y_start = y + BAR_H//2 - (len(ans_lines) * 30)//2
    for ai, al in enumerate(ans_lines):
        draw.text((ans_x, ans_y_start + ai * 32), al, font=f_ans, fill=WHITE)

    y += BAR_H + GAP

    # ══════════════════════════════════════════════════════════════════════════
    # 4. WRONG OPTIONS — 2×2 grid with X strikethrough
    # ══════════════════════════════════════════════════════════════════════════
    wrong_opts = [o for o in quiz["options"] if not o.startswith(ans_letter)]
    cell_w     = (W - pad * 2 - 12) // 2
    cell_h     = 80   # taller cells for longer option text

    for i, opt in enumerate(wrong_opts[:4]):
        col = i % 2; row = i // 2
        ox  = pad + col * (cell_w + 12)
        oy  = y + row * (cell_h + 10)
        ox2 = ox + cell_w
        oy2 = oy + cell_h

        opt_letter = opt[0] if opt else "?"
        opt_body   = opt[3:] if len(opt) > 2 and opt[1] == ')' else opt
        opt_short  = opt_body if len(opt_body) <= 20 else opt_body[:19] + "…"

        # Card
        draw.rounded_rectangle([ox, oy, ox2, oy2],
                                radius=10, fill=(12, 22, 56, 215))
        draw.rounded_rectangle([ox, oy, ox2, oy2],
                                radius=10, outline=(50, 60, 92), width=1)

        # Letter badge
        lbf  = _load_font(cfg["font_bold"], 21)
        draw.rounded_rectangle([ox+7, oy+8, ox+38, oy+cell_h-8],
                                radius=7, fill=(26, 36, 76))
        draw.rounded_rectangle([ox+7, oy+8, ox+38, oy+cell_h-8],
                                radius=7, outline=(70, 80, 112), width=1)
        lbfw = _text_width(draw, opt_letter, lbf)
        draw.text((ox + 23 - lbfw//2, oy + 16), opt_letter,
                  font=lbf, fill=SILVER)

        # Option text — wrap to 2 lines if needed
        opt_lines = textwrap.wrap(opt_body, width=16)[:2]
        for oli, otxt in enumerate(opt_lines):
            draw.text((ox+46, oy+14+oli*26), otxt, font=f_opt, fill=DIM_TXT)

        # Red X badge top-right
        draw.rounded_rectangle([ox2-25, oy+5, ox2-5, oy+24],
                                radius=5, fill=(125, 22, 22))
        xf = _load_font(cfg["font_bold"], 16)
        draw.text((ox2 - 20, oy + 6), "X", font=xf, fill=(255, 135, 135))

        # Diagonal strikethrough
        draw.line([(ox+4, oy+4),   (ox2-4, oy2-4)],
                  fill=(*RED, 90), width=2)
        draw.line([(ox2-4, oy+4),  (ox+4,  oy2-4)],
                  fill=(*RED, 90), width=2)

    rows_used = (len(wrong_opts[:4]) + 1) // 2
    y += rows_used * (cell_h + 12) - 12 + GAP

    # ══════════════════════════════════════════════════════════════════════════
    # 5. DESCRIPTION LABEL
    # ══════════════════════════════════════════════════════════════════════════
    desc_lbl = "DESCRIPTION"
    dlw      = _text_width(draw, desc_lbl, f_sub)
    draw.text(((W - dlw)//2, y + 4), desc_lbl, font=f_sub, fill=GOLD)
    draw.rectangle([pad + 10, y + 38, W - pad - 10, y + 40],
                   fill=(*GOLD_DIM, 140))
    y += DESC_H + GAP

    # ══════════════════════════════════════════════════════════════════════════
    # 6. EXPLANATION CARD — fills all remaining space
    # ══════════════════════════════════════════════════════════════════════════
    exp_bottom = H - BRAND_H - 10
    exp_h      = max(180, exp_bottom - y)

    draw.rounded_rectangle([pad, y, W-pad, y+exp_h],
                            radius=13, fill=(8, 16, 44, 235))
    draw.rounded_rectangle([pad, y, W-pad, y+exp_h],
                            radius=13, outline=(*GOLD_DIM, 160), width=2)
    # Left gold accent stripe
    draw.rounded_rectangle([pad, y+12, pad+5, y+exp_h-12],
                            radius=3, fill=GOLD_DIM)

    # "WHY IT IS CORRECT:" label
    draw.text((pad+16, y+12), "WHY IT IS CORRECT:", font=f_why, fill=GOLD)
    draw.rectangle([pad+16, y+48, W-pad-16, y+50],
                   fill=(*GOLD_DIM, 70))

    # Explanation text — clean wrapping, skip "Answer: X" lines
    exp_lines = []
    for para in quiz["explanation"].split("\n"):
        stripped = para.strip()
        if stripped.startswith("Answer:"):
            continue
        if stripped:
            exp_lines.extend(textwrap.wrap(stripped, width=38))
        else:
            if exp_lines and exp_lines[-1] != "":
                exp_lines.append("")

    ey     = y + 62
    line_h = 38
    for line in exp_lines:
        if ey + line_h > y + exp_h - 10:
            break
        draw.text((pad + 18, ey), line, font=f_exp,
                  fill=(185, 200, 220))
        ey += line_h

    # ══════════════════════════════════════════════════════════════════════════
    # 7. BRANDING STRIP
    # ══════════════════════════════════════════════════════════════════════════
    by = H - BRAND_H
    draw.rectangle([0, by,   W, H],     fill=(4, 10, 36, 240))
    draw.rectangle([0, by,   W, by+2],  fill=GOLD_DIM)
    brand = "@TechLearning  |  Follow for daily coding quizzes!"
    bfw   = _text_width(draw, brand, f_brand)
    draw.text(((W-bfw)//2, by + 28), brand, font=f_brand, fill=GOLD)

    out = "frame_answer.png"
    img.convert("RGB").save(out)
    print(f"[VIDEO] Answer frame saved → {out}")
    return out

def generate_audio(quiz_secs: float, answer_secs: float, cfg: dict) -> str:
    """
    Perfectly frame-synced soundtrack.

    SYNC CONTRACT:
      - Tick fires at EXACTLY sample int(sec * sr) for each second 0..N-1
      - Last 3 seconds: tick + half-beat tock, rising pitch
      - At sample Q = int(quiz_secs * sr): BUZZER starts (transition frame)
      - At Q + 0.6s : dramatic low hit
      - At Q + 1.4s : rising chromatic run
      - At Q + 2.5s : triumphant C-major fanfare

    Audio file duration = quiz_secs + answer_secs exactly,
    so MoviePy trims nothing and every sound lands on the right frame.
    """
    import numpy as np
    import wave
    import os

    sr = 44100

    # ── Synthesisers ─────────────────────────────────────────────────────────

    def place(track, sig, pos):
        if sig is None or len(sig) == 0:
            return
        end = min(pos + len(sig), len(track))
        if end > pos:
            track[pos:end] += sig[:end - pos]

    def adsr(sig, sr=sr, a=0.005, d=0.06, sl=0.60, r=0.12):
        n  = len(sig)
        e  = np.full(n, sl, dtype=np.float32)
        ai = min(int(a*sr), n)
        di = min(int(d*sr), n-ai)
        ri = min(int(r*sr), n)
        e[:ai]             = np.linspace(0, 1,  ai)
        if di > 0: e[ai:ai+di] = np.linspace(1, sl, di)
        e[max(0,n-ri):]    = np.linspace(sl, 0, min(ri, n))
        return sig * e

    def tone(freq, dur, amp, harmonics=()):
        n   = max(1, int(sr * dur))
        t   = np.linspace(0, dur, n, endpoint=False)
        sig = amp * np.sin(2*np.pi*freq*t).astype(np.float32)
        for mult, rel in harmonics:
            sig += (amp*rel*np.sin(2*np.pi*freq*mult*t)).astype(np.float32)
        return sig

    def tick(freq=920, amp=0.30):
        dur = 0.016
        n   = int(sr*dur)
        t   = np.linspace(0, dur, n, endpoint=False)
        sig = amp * np.sin(2*np.pi*freq*t)
        sig += np.random.randn(n) * amp * 0.10
        return (sig * np.exp(-t*330)).astype(np.float32)

    def tock(freq=740, amp=0.18):
        dur = 0.014
        n   = int(sr*dur)
        t   = np.linspace(0, dur, n, endpoint=False)
        sig = amp * np.sin(2*np.pi*freq*t)
        sig += np.random.randn(n) * amp * 0.08
        return (sig * np.exp(-t*390)).astype(np.float32)

    def kick(amp=0.20):
        dur = 0.18
        n   = int(sr*dur)
        t   = np.linspace(0, dur, n, endpoint=False)
        f   = 80 * np.exp(-t*20)
        sig = amp * np.sin(2*np.pi*np.cumsum(f)/sr)
        return (sig * np.exp(-t*22)).astype(np.float32)

    def buzzer(dur=0.75, amp=0.40):
        """Game-show wrong-answer buzzer — descending harsh tone."""
        n   = int(sr*dur)
        t   = np.linspace(0, dur, n, endpoint=False)
        f   = 290 * np.exp(-t*1.8)
        ph  = np.cumsum(2*np.pi*f/sr)
        sig = amp*(np.sin(ph) + 0.55*np.sin(ph*2) + 0.28*np.sin(ph*3))
        env = np.exp(-t*2.2)
        env[:int(sr*0.008)] = np.linspace(0, 1, int(sr*0.008))
        return (sig*env).astype(np.float32)

    # ── Try to load real SFX files ────────────────────────────────────────────
    SFX_DIR = os.path.dirname(os.path.abspath(__file__))

    def load_sfx(path):
        if not os.path.exists(path):
            return None
        try:
            with wave.open(path, 'r') as wf:
                nc  = wf.getnchannels()
                sw  = wf.getsampwidth()
                fsr = wf.getframerate()
                raw = wf.readframes(wf.getnframes())
            dtype = {1: np.uint8, 2: np.int16, 4: np.int32}.get(sw, np.int16)
            data  = np.frombuffer(raw, dtype=dtype).astype(np.float32)
            if sw == 1:  data = data/128.0 - 1.0
            elif sw == 2: data = data/32768.0
            else:         data = data/2147483648.0
            if nc > 1:
                data = data.reshape(-1, nc).mean(axis=1)
            if fsr != sr:
                n_new = int(len(data)*sr/fsr)
                data  = np.interp(np.linspace(0,len(data)-1,n_new),
                                  np.arange(len(data)), data)
            peak = np.max(np.abs(data))
            return (data/peak*0.85).astype(np.float32) if peak>0 else data
        except Exception:
            return None

    tick_sfx    = load_sfx(os.path.join(SFX_DIR, "sfx_tick.wav"))
    timeout_sfx = load_sfx(os.path.join(SFX_DIR, "sfx_timeout.wav"))
    fanfare_sfx = load_sfx(os.path.join(SFX_DIR, "sfx_fanfare.wav"))

    if tick_sfx    is not None: print(f"[AUDIO] Loaded sfx_tick.wav")
    else:                       print(f"[AUDIO] Using synth tick")
    if timeout_sfx is not None: print(f"[AUDIO] Loaded sfx_timeout.wav")
    else:                       print(f"[AUDIO] Using synth timeout (buzzer)")
    if fanfare_sfx is not None: print(f"[AUDIO] Loaded sfx_fanfare.wav")
    else:                       print(f"[AUDIO] Using synth fanfare")

    # ══════════════════════════════════════════════════════════════════════════
    # QUIZ TRACK — one tick per second, perfectly synced
    # ══════════════════════════════════════════════════════════════════════════
    Q  = int(sr * quiz_secs)
    qt = np.zeros(Q, dtype=np.float32)

    # Soft atmospheric pad (D minor)
    for f, a in [(146.8, 0.040), (220.0, 0.025), (293.7, 0.014)]:
        p = adsr(tone(f, quiz_secs, a), a=0.5, d=0.2, sl=0.85, r=1.0)
        place(qt, p, 0)

    # Ticks — placed at exact sample position int(sec * sr)
    for sec in range(int(quiz_secs)):
        remaining  = quiz_secs - sec      # seconds left on clock
        pos        = int(sec * sr)        # exact sample — perfectly synced

        t_sig = tick_sfx if tick_sfx is not None else None

        if remaining > 3.0:
            # Normal single tick
            sig = t_sig if t_sig is not None else tick(freq=900, amp=0.30)
            place(qt, sig * 0.88, pos)

        else:
            # Urgent — louder, higher, + tock at half-second
            urgency  = (3.0 - remaining) / 3.0
            tick_amp = 1.0 + urgency * 0.35
            tick_freq = int(900 + urgency * 440)

            if t_sig is not None:
                place(qt, t_sig * tick_amp, pos)
                place(qt, t_sig * tick_amp * 0.55, pos + sr//2)
            else:
                place(qt, tick(freq=tick_freq, amp=0.32*tick_amp), pos)
                place(qt, tock(freq=tick_freq-90, amp=0.18*tick_amp), pos + sr//2)

            # Extra kick on last second
            if remaining <= 1.0:
                place(qt, kick(amp=0.16), pos)

    # ══════════════════════════════════════════════════════════════════════════
    # ANSWER TRACK — buzzer → pause → rise → fanfare
    # The buzzer starts at sample 0 of the answer track, which is
    # exactly frame 0 of the answer video clip — perfect sync.
    # ══════════════════════════════════════════════════════════════════════════
    A  = int(sr * answer_secs)
    at = np.zeros(A, dtype=np.float32)

    # 0.00s — TIMEOUT BUZZER (fires exactly on transition frame)
    buz = timeout_sfx if timeout_sfx is not None else buzzer(dur=0.75, amp=0.40)
    place(at, buz, 0)

    # 0.60s — Low dramatic tension chord
    for f, a in [(65.4, 0.18), (98.0, 0.11), (130.8, 0.07)]:
        h = tone(f, min(1.2, answer_secs-0.6), a,
                 harmonics=[(2, 0.20)])
        h = adsr(h, a=0.005, d=0.38, sl=0.10, r=0.40)
        place(at, h, int(sr*0.60))
    place(at, kick(amp=0.22), int(sr*0.60))

    # 1.40s — Rising chromatic run (13 notes over ~1s)
    RISE = [261.6, 277.2, 293.7, 311.1, 329.6, 349.2, 370.0,
            392.0, 415.3, 440.0, 466.2, 493.9, 523.2]
    nd = 0.072
    rs = int(sr * 1.40)
    for ni, freq in enumerate(RISE):
        rp = rs + int(ni*nd*sr)
        if rp >= A:
            break
        rn = tone(freq, nd, 0.12+ni*0.008, harmonics=[(2,0.18),(3,0.05)])
        rn = adsr(rn, a=0.004, d=0.03, sl=0.70, r=0.06)
        place(at, rn, rp)

    # 2.50s — TRIUMPHANT C-MAJOR FANFARE
    FS  = min(int(sr*2.50), A - int(sr*2.0))
    if fanfare_sfx is not None:
        place(at, fanfare_sfx, FS)
    else:
        FAN = [
            (523.2,  0.08),
            (659.3,  0.08),
            (784.0,  0.08),
            (1046.5, 0.55),
            (880.0,  0.14),
            (784.0,  0.14),
            (1046.5, 0.72),
        ]
        fp = FS
        for freq, dur in FAN:
            if fp >= A:
                break
            fn  = tone(freq, dur, 0.18, harmonics=[(2,0.15),(3,0.06)])
            fn += tone(freq/2, dur, 0.07)
            fn  = adsr(fn, a=0.006, d=0.04, sl=0.80, r=0.14)
            place(at, fn, fp)
            fp += int(dur*sr*0.87)

    # Kick + snare rolls on fanfare
    place(at, kick(amp=0.22), FS)
    beat = int(sr * 60.0/118)
    for ri in range(3):
        sp = FS + int(ri*beat*0.5)
        if sp >= A:
            break
        sn = tone(200, 0.12, 0.06)
        sn += (np.random.randn(len(sn))*0.05).astype(np.float32)
        sn  = adsr(sn, a=0.001, d=0.03, sl=0.25, r=0.07)
        place(at, sn, sp)

    # ══════════════════════════════════════════════════════════════════════════
    # MASTER MIX
    # ══════════════════════════════════════════════════════════════════════════
    full = np.concatenate([qt, at])
    # Soft tanh limiter — no clipping
    full = np.tanh(full * 1.35) / 1.35 * 0.80
    # Gentle low-pass
    full = np.convolve(full, [0.25, 0.50, 0.25], mode='same')

    audio_int = (full * 32767).astype(np.int16)

    out = "quiz_audio.wav"
    with wave.open(out, 'w') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(audio_int.tobytes())

    print(f"[AUDIO] Soundtrack saved → {out} "
          f"({quiz_secs:.0f}s ticks + buzzer + {answer_secs:.0f}s fanfare)")
    return out

def _make_image_clip(path: str, duration: float, fps: int):
    """Create an ImageClip compatible with both MoviePy 1.x and 2.x."""
    try:
        return ImageClip(path, duration=duration)
    except TypeError:
        return ImageClip(path).set_duration(duration).set_fps(fps)


def render_quiz_frame_at(quiz: dict, cfg: dict, elapsed: float, total: float) -> Image.Image:
    """
    Animated quiz frame — game-show style.
    Fixes:
      - No background grid lines
      - Timer ring labels outside ring (not inside)
      - Content spread to fill full 1920px height
      - No empty bottom half
    """
    import math

    W, H      = cfg["video_width"], cfg["video_height"]
    remaining = max(0.0, total - elapsed)
    fraction  = remaining / total
    locked    = remaining <= 0

    # ── Solid clean background — NO grid lines ────────────────────────────────
    img  = Image.new("RGBA", (W, H))
    _draw_gradient_bg(img, (4, 12, 40), (6, 20, 58))
    img  = img.convert("RGBA")
    draw = ImageDraw.Draw(img)
    # NO diagonal lines drawn here

    GOLD      = (255, 210, 60)
    GOLD_DIM  = (180, 140, 20)
    GOLD_DARK = (70,  50,  4)
    SILVER    = (200, 210, 226)
    WHITE     = (255, 255, 255)
    BLUE_LT   = (120, 178, 255)

    pad = 40

    # ── Calculate dynamic layout based on content ─────────────────────────────
    code_lines = _wrap_code(quiz["code"], max_chars=42)[:10]
    n_code     = len(code_lines)

    # Compute how much space each section needs
    HEADER_H   = 110    # header bar
    TAG_H      = 50     # question type tag
    CODE_H     = n_code * 34 + 40  # code block
    ACL_H      = 40     # "answer choices" label
    OPT_H      = 4 * 86 + 3 * 10   # 4 options with gaps = 374
    RING_H     = 160    # timer ring section (ring + labels above/below)
    CTA_H      = 72     # CTA / lock button
    BRAND_H    = 90     # branding strip

    CONTENT_H  = HEADER_H + TAG_H + CODE_H + ACL_H + OPT_H + RING_H + CTA_H + BRAND_H
    # Available vertical space to distribute as gaps
    EXTRA      = max(H - CONTENT_H, 0)
    # Split extra space into 6 gaps between sections
    GAP        = EXTRA // 7

    # ── Fonts ─────────────────────────────────────────────────────────────────
    f_hdr   = _load_font(cfg["font_bold"],    44)
    f_tag   = _load_font(cfg["font_bold"],    28)
    f_lang  = _load_font(cfg["font_bold"],    26)
    f_code  = _load_font(cfg["font_mono"],    28)
    f_lnum  = _load_font(cfg["font_mono"],    20)
    f_opt   = _load_font(cfg["font_bold"],    32)
    f_lbl   = _load_font(cfg["font_bold"],    28)
    f_cta   = _load_font(cfg["font_bold"],    34)
    f_timer = _load_font(cfg["font_bold"],    70)
    f_tsub  = _load_font(cfg["font_bold"],    22)
    f_brand = _load_font(cfg["font_regular"], 24)

    # ══════════════════════════════════════════════════════════════════════════
    # SECTION 1: HEADER BAR
    # ══════════════════════════════════════════════════════════════════════════
    y = 20
    draw.rounded_rectangle([pad-12, y, W-pad+12, y+HEADER_H-10],
                            radius=14, fill=(14, 30, 82, 255))
    draw.rounded_rectangle([pad-12, y, W-pad+12, y+HEADER_H-10],
                            radius=14, outline=GOLD, width=3)
    draw.rounded_rectangle([pad-12, y, W-pad+12, y+8],
                            radius=14, fill=GOLD)

    hdr_txt = "QUIZ QUESTION"
    hw = _text_width(draw, hdr_txt, f_hdr)
    draw.text(((W-hw)//2, y+28), hdr_txt, font=f_hdr, fill=GOLD)

    # Language badge inside header right
    lang = quiz["language"]
    lw   = _text_width(draw, lang, f_lang)
    lbx1 = W - pad - lw - 28
    lby1 = y + 30
    draw.rounded_rectangle([lbx1-6, lby1, lbx1+lw+18, lby1+42],
                            radius=10, fill=(8, 22, 68, 220))
    draw.rounded_rectangle([lbx1-6, lby1, lbx1+lw+18, lby1+42],
                            radius=10, outline=GOLD, width=2)
    draw.text((lbx1+6, lby1+8), lang, font=f_lang, fill=GOLD)

    y += HEADER_H + GAP

    # ══════════════════════════════════════════════════════════════════════════
    # SECTION 2: QUESTION TYPE TAG
    # ══════════════════════════════════════════════════════════════════════════
    qtxt = f"?  {quiz['question_type'].upper()}"
    qtw  = _text_width(draw, qtxt, f_tag)
    draw.rounded_rectangle([pad-6, y, pad+qtw+22, y+44],
                            radius=8, fill=(12, 28, 82, 220))
    draw.rounded_rectangle([pad-6, y, pad+qtw+22, y+44],
                            radius=8, outline=GOLD_DIM, width=2)
    draw.text((pad+8, y+8), qtxt, font=f_tag, fill=GOLD)

    y += TAG_H + GAP

    # ══════════════════════════════════════════════════════════════════════════
    # SECTION 3: CODE BLOCK
    # ══════════════════════════════════════════════════════════════════════════
    lhc  = 34
    cb_h = n_code * lhc + 40

    draw.rounded_rectangle([pad-8, y, W-pad+8, y+cb_h],
                            radius=12, fill=(3, 9, 28, 255))
    draw.rounded_rectangle([pad-8, y, W-pad+8, y+cb_h],
                            radius=12, outline=GOLD_DIM, width=2)
    # Editor top bar
    draw.rounded_rectangle([pad-8, y, W-pad+8, y+12], radius=12, fill=GOLD_DIM)
    # Editor dots
    for di, dc in enumerate([(210,70,70),(210,170,50),(70,190,90)]):
        draw.ellipse([pad+6+di*20, y+1, pad+18+di*20, y+13], fill=dc)

    for i, line in enumerate(code_lines):
        row_y = y + 20 + i * lhc
        draw.text((pad+2,  row_y), str(i+1), font=f_lnum, fill=(90,108,145))
        draw.text((pad+30, row_y), line,      font=f_code, fill=(175,205,255))

    y += cb_h + GAP

    # ══════════════════════════════════════════════════════════════════════════
    # SECTION 4: ANSWER CHOICES LABEL
    # ══════════════════════════════════════════════════════════════════════════
    ac_txt = "ANSWER CHOICES"
    acw    = _text_width(draw, ac_txt, f_tag)
    draw.text(((W-acw)//2, y+4), ac_txt, font=f_tag, fill=GOLD)

    y += ACL_H + GAP

    # ══════════════════════════════════════════════════════════════════════════
    # SECTION 5: OPTIONS
    # ══════════════════════════════════════════════════════════════════════════
    opt_h_each = 86
    opt_gap    = 10

    for i, option in enumerate(quiz["options"]):
        by1 = y
        by2 = y + opt_h_each

        # Metallic card — 3 layers
        draw.rounded_rectangle([pad,   by1,   W-pad,   by2],             radius=13, fill=(72,82,104))
        draw.rounded_rectangle([pad,   by1,   W-pad,   by1+opt_h_each//2], radius=13, fill=(95,108,134))
        draw.rounded_rectangle([pad+1, by1+1, W-pad-1, by2-1],           radius=12, fill=(50,58,78))

        # Pulsing border when not locked
        if not locked:
            phase = (elapsed*1.4 + i*0.55) % (2*3.14159)
            pv    = int(8 + 6*abs(math.sin(phase)))
            bc    = (168+pv, 180+pv, 204+pv)
        else:
            bc    = (70,80,104)
        draw.rounded_rectangle([pad, by1, W-pad, by2], radius=13, outline=bc, width=2)

        # Letter circle
        cx_c = pad + 46
        cy_c = by1 + opt_h_each // 2
        draw.ellipse([cx_c-26, cy_c-26, cx_c+26, cy_c+26], fill=(10,20,58))
        draw.ellipse([cx_c-26, cy_c-26, cx_c+26, cy_c+26], outline=GOLD, width=2)
        lfw = _text_width(draw, LETTER_LABELS[i], f_lbl)
        draw.text((cx_c-lfw//2, cy_c-18), LETTER_LABELS[i], font=f_lbl, fill=GOLD)

        # Option text
        opt_raw = option[3:] if len(option)>2 and option[1]==')' else option
        opt_txt = opt_raw if len(opt_raw)<=28 else opt_raw[:26]+"…"
        draw.text((pad+86, by1+26), opt_txt, font=f_opt,
                  fill=(108,118,140) if locked else SILVER)

        y += opt_h_each + opt_gap

    y += GAP

    # ══════════════════════════════════════════════════════════════════════════
    # SECTION 6: TIMER RING — labels OUTSIDE the ring, not inside
    # Layout: "TIMER" above ring, digits inside ring, "SECONDS LEFT" below ring
    # ══════════════════════════════════════════════════════════════════════════
    ring_r  = 62
    ring_w  = 10
    ring_cx = W // 2

    # "TIMER" label ABOVE the ring
    tl  = "TIMER"
    tlw = _text_width(draw, tl, f_tsub)
    draw.text((ring_cx-tlw//2, y), tl, font=f_tsub, fill=GOLD)

    ring_cy = y + 28 + ring_r   # ring centre: 28px below "TIMER" text

    # Timer colour: orange → red as time runs out
    if fraction > 0.40:
        tc = (255, 140, 0)
    else:
        t2 = fraction / 0.40
        tc = (255, int(90*t2), 0)

    # Outer dark halo
    draw.ellipse([ring_cx-ring_r-10, ring_cy-ring_r-10,
                  ring_cx+ring_r+10, ring_cy+ring_r+10],
                 fill=(6, 16, 50, 220))
    draw.ellipse([ring_cx-ring_r-10, ring_cy-ring_r-10,
                  ring_cx+ring_r+10, ring_cy+ring_r+10],
                 outline=GOLD_DIM, width=2)
    # Track ring
    draw.ellipse([ring_cx-ring_r, ring_cy-ring_r,
                  ring_cx+ring_r, ring_cy+ring_r],
                 outline=(28, 38, 70), width=ring_w)
    # Progress arc
    if fraction > 0.005:
        draw.arc([ring_cx-ring_r, ring_cy-ring_r,
                  ring_cx+ring_r, ring_cy+ring_r],
                 start=-90, end=-90+fraction*360, fill=tc, width=ring_w)

    # Seconds digits INSIDE ring — only the number, centred
    secs = f"{int(math.ceil(remaining)):02d}"
    sw   = _text_width(draw, secs, f_timer)
    # Vertically centre inside ring
    draw.text((ring_cx-sw//2, ring_cy-36), secs, font=f_timer, fill=tc)

    # "SECONDS LEFT" label BELOW the ring
    sl  = "SECONDS LEFT"
    slw = _text_width(draw, sl, f_tsub)
    draw.text((ring_cx-slw//2, ring_cy+ring_r+12), sl, font=f_tsub, fill=GOLD)

    y = ring_cy + ring_r + 12 + 30 + GAP  # below "SECONDS LEFT" + gap

    # ══════════════════════════════════════════════════════════════════════════
    # SECTION 7: CTA / LOCK BUTTON
    # ══════════════════════════════════════════════════════════════════════════
    if locked:
        draw.rounded_rectangle([pad, y, W-pad, y+64],
                                radius=14, fill=(118,14,14,235))
        draw.rounded_rectangle([pad, y, W-pad, y+64],
                                radius=14, outline=(220,58,58), width=2)
        lt  = "TIME'S UP!  Answer Locked!"
        ltw = _text_width(draw, lt, f_cta)
        draw.text(((W-ltw)//2, y+14), lt, font=f_cta, fill=(255,200,200))
    else:
        cta  = "COMMENT YOUR ANSWER  +"
        ctaw = _text_width(draw, cta, f_cta)
        cx1  = (W-ctaw-50)//2
        cx2  = cx1+ctaw+50
        # Gold button — shadow layer
        draw.rounded_rectangle([cx1+4, y+4, cx2+4, y+66],
                                radius=16, fill=(40,28,0,160))
        # Button body
        draw.rounded_rectangle([cx1, y,   cx2, y+62], radius=16, fill=GOLD_DIM)
        draw.rounded_rectangle([cx1, y,   cx2, y+28], radius=16, fill=GOLD)
        draw.rounded_rectangle([cx1+2, y+2, cx2-2, y+60],
                                radius=14, outline=GOLD_DARK, width=1)
        draw.text((cx1+20, y+14), cta, font=f_cta, fill=(16,10,0))

    # ══════════════════════════════════════════════════════════════════════════
    # BRANDING STRIP — always pinned to bottom
    # ══════════════════════════════════════════════════════════════════════════
    draw.rectangle([0, H-88, W, H],    fill=(4, 10, 36, 240))
    draw.rectangle([0, H-90, W, H-88], fill=GOLD_DIM)
    brand = "@TechLearning  |  Like & Follow for daily quizzes!"
    bfw   = _text_width(draw, brand, f_brand)
    draw.text(((W-bfw)//2, H-62), brand, font=f_brand, fill=GOLD)

    return img.convert("RGB")

# ── Platform video specs ─────────────────────────────────────────────────────
#
#  Platform      W     H    FPS   Max size  Notes
#  YouTube Shorts 1080 1920  30   unlimited  H.264 + AAC
#  Instagram Reel 1080 1920  30   650 MB     H.264 + AAC, 9:16 required
#  Facebook Reel  1080 1920  30   1 GB       H.264 + AAC
#
#  All three use identical 1080x1920 9:16 — we render ONE master video
#  and export platform-specific copies with correct bitrate/size limits.

PLATFORM_SPECS = {
    "youtube":   {"width": 1080, "height": 1920, "fps": 30, "bitrate": "4000k", "max_mb": None},
    "instagram": {"width": 1080, "height": 1920, "fps": 30, "bitrate": "3500k", "max_mb": 600},
    "facebook":  {"width": 1080, "height": 1920, "fps": 30, "bitrate": "4000k", "max_mb": 950},
    "make":      {"width": 1080, "height": 1920, "fps": 30, "bitrate": "3500k", "max_mb": 600},
}



# ══════════════════════════════════════════════════════════════════════════════
# PROMO FRAME — 2 second agency promo shown between quiz and answer
# ══════════════════════════════════════════════════════════════════════════════

def render_promo_frame(cfg: dict) -> str:
    """
    2-second fullstack dev agency promo frame.
    Shown between quiz and answer frames.
    Layout: bold headline + services + link + CTA button
    """
    W, H = cfg["video_width"], cfg["video_height"]

    img  = Image.new("RGBA", (W, H))
    _draw_gradient_bg(img, (4, 8, 28), (8, 20, 60))
    img  = img.convert("RGBA")
    draw = ImageDraw.Draw(img)

    GOLD     = (255, 210, 60)
    GOLD_DIM = (175, 138, 18)
    WHITE    = (255, 255, 255)
    SILVER   = (200, 210, 226)
    ACCENT   = (99,  235, 170)   # green accent
    BLUE_LT  = (120, 178, 255)
    pad      = 50

    f_big    = _load_font(cfg["font_bold"],    72)
    f_title  = _load_font(cfg["font_bold"],    52)
    f_sub    = _load_font(cfg["font_bold"],    36)
    f_body   = _load_font(cfg["font_regular"], 32)
    f_link   = _load_font(cfg["font_bold"],    34)
    f_cta    = _load_font(cfg["font_bold"],    38)
    f_small  = _load_font(cfg["font_regular"], 26)
    f_brand  = _load_font(cfg["font_regular"], 24)

    # ── Decorative top accent line ────────────────────────────────────────────
    draw.rectangle([0, 0, W, 6], fill=GOLD)

    # ── "FULLSTACK DEVELOPER" badge ────────────────────────────────────────────
    y = 80
    badge_txt = "FULLSTACK DEVELOPER"
    bw = _text_width(draw, badge_txt, f_sub)
    bx1 = (W - bw - 48) // 2
    bx2 = bx1 + bw + 48
    draw.rounded_rectangle([bx1, y, bx2, y+52], radius=26, fill=(20,40,100,220))
    draw.rounded_rectangle([bx1, y, bx2, y+52], radius=26, outline=ACCENT, width=2)
    btw = _text_width(draw, badge_txt, f_sub)
    draw.text(((W-btw)//2, y+10), badge_txt, font=f_sub, fill=ACCENT)

    y += 80

    # ── Big headline ──────────────────────────────────────────────────────────
    line1 = "Need a"
    line2 = "Website?"
    w1 = _text_width(draw, line1, f_big)
    w2 = _text_width(draw, line2, f_big)
    draw.text(((W-w1)//2, y), line1, font=f_big, fill=WHITE)
    y += 82
    draw.text(((W-w2)//2, y), line2, font=f_big, fill=GOLD)

    y += 110

    # ── Divider ───────────────────────────────────────────────────────────────
    draw.rectangle([pad+20, y, W-pad-20, y+3], fill=(*GOLD_DIM, 160))
    y += 28

    # ── Services list ─────────────────────────────────────────────────────────
    services = [
        ("✦", "Websites & Web Apps"),
        ("✦", "AI Chatbots & Automation"),
        ("✦", "UI/UX Design"),
    ]
    for icon, svc in services:
        # Icon dot
        draw.ellipse([pad+8, y+10, pad+28, y+30], fill=ACCENT)
        draw.text((pad+36, y), svc, font=f_body, fill=SILVER)
        y += 52

    y += 20

    # ── Divider ───────────────────────────────────────────────────────────────
    draw.rectangle([pad+20, y, W-pad-20, y+3], fill=(*GOLD_DIM, 160))
    y += 36

    # ── Contact options row ───────────────────────────────────────────────────
    contact_label = "DM / Email me:"
    clw = _text_width(draw, contact_label, f_sub)
    draw.text(((W-clw)//2, y), contact_label, font=f_sub, fill=GOLD)
    y += 56

    # Email
    email_txt = "techlearn.908@gmail.com"
    ew = _text_width(draw, email_txt, f_small)
    draw.text(((W-ew)//2, y), email_txt, font=f_small, fill=SILVER)
    y += 46

    # ── Big link box ──────────────────────────────────────────────────────────
    link_txt = "agency-website.mustufaaijaz1234"
    link_sub = "           .workers.dev"
    lw = _text_width(draw, link_txt, f_link)
    lx1 = pad - 10
    lx2 = W - pad + 10
    ly1 = y
    ly2 = y + 90

    # Glowing box
    draw.rounded_rectangle([lx1, ly1, lx2, ly2], radius=16, fill=(8, 30, 90, 235))
    draw.rounded_rectangle([lx1, ly1, lx2, ly2], radius=16, outline=GOLD, width=3)
    draw.rounded_rectangle([lx1, ly1, lx2, ly1+8], radius=16, fill=GOLD)

    # "CLICK LINK IN BIO" label inside box top
    bio_txt = "🔗  CLICK LINK IN BIO"
    biolabel = "CLICK LINK IN BIO"
    biolw = _text_width(draw, biolabel, f_small)
    draw.text(((W-biolw)//2, ly1+12), biolabel, font=f_small, fill=(14,9,0))

    # URL text
    url_full = "agency-website.mustufaaijaz1234.workers.dev"
    urlw = _text_width(draw, url_full, f_link)
    draw.text(((W-urlw)//2, ly1+36), url_full, font=f_link, fill=GOLD)

    y = ly2 + 36

    # ── CTA Button ───────────────────────────────────────────────────────────
    cta_txt = "Let's Build Together!"
    ctaw    = _text_width(draw, cta_txt, f_cta)
    cx1 = (W - ctaw - 60) // 2
    cx2 = cx1 + ctaw + 60
    # Shadow
    draw.rounded_rectangle([cx1+4, y+4, cx2+4, y+72], radius=18, fill=(30,60,0,140))
    # Button
    draw.rounded_rectangle([cx1, y, cx2, y+68], radius=18, fill=ACCENT)
    draw.rounded_rectangle([cx1, y, cx2, y+28], radius=18, fill=(140,255,200))
    draw.rounded_rectangle([cx1+2, y+2, cx2-2, y+66], radius=16, outline=(20,120,60), width=1)
    ctaw2 = _text_width(draw, cta_txt, f_cta)
    draw.text(((W-ctaw2)//2, y+14), cta_txt, font=f_cta, fill=(4,40,16))

    y += 88

    # ── TechLearning branding strip at bottom ─────────────────────────────────
    draw.rectangle([0, H-88, W, H],    fill=(4, 10, 36, 240))
    draw.rectangle([0, H-90, W, H-88], fill=GOLD_DIM)
    brand = "@TechLearning  |  Daily Coding Quizzes"
    bfw   = _text_width(draw, brand, f_brand)
    draw.text(((W-bfw)//2, H-62), brand, font=f_brand, fill=GOLD)

    # ── Bottom accent line ────────────────────────────────────────────────────
    draw.rectangle([0, H-2, W, H], fill=GOLD)

    out = "frame_promo.png"
    img.convert("RGB").save(out)
    print(f"[VIDEO] Promo frame saved → {out}")
    return out


# ── Background music helpers ──────────────────────────────────────────────────

def _pick_bg_music(cfg: dict) -> str | None:
    """
    Pick which background song to use this run.
    Alternates between the two songs based on DB record count (odd/even).
    Returns the file path, or None if neither file exists.
    """
    songs = cfg.get("bg_music", [])
    if not songs:
        return None

    # Use DB count to alternate — odd runs get song 1, even get song 2
    try:
        conn = db_connect()
        cur  = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM askedquestion")
        count = cur.fetchone()[0]
        conn.close()
    except Exception:
        count = 0

    # Pick song based on even/odd total uploads
    song_path = songs[count % len(songs)]

    if os.path.exists(song_path):
        names = ["INSONAMIA (SLOWED)", "LUZ ROJA by bxkq"]
        name  = names[count % len(names)]
        print(f"[AUDIO] Background song #{(count%len(songs))+1}: {name}")
        return song_path
    else:
        print(f"[AUDIO] Song file not found: {song_path}")
        print(f"[AUDIO] Falling back to synthesized audio only")
        return None


def _mix_audio(ticks_path: str, song_path: str, cfg: dict) -> str | None:
    """
    Mix tick/buzzer sounds with the background song.

    - Song plays at bg_music_volume (default 0.85) throughout
    - Ticks/buzzer play at tick_volume (default 0.30) on top
    - Song is looped/trimmed to match exact video duration
    - Returns path to mixed WAV file, or None on error
    """
    import numpy as np
    import wave
    import struct

    bg_vol   = cfg.get("bg_music_volume", 0.85)
    tick_vol = cfg.get("tick_volume", 0.30)
    sr       = 44100

    # ── Load ticks WAV ────────────────────────────────────────────────────────
    def load_wav(path):
        try:
            with wave.open(path, "r") as wf:
                nc  = wf.getnchannels()
                sw  = wf.getsampwidth()
                fsr = wf.getframerate()
                raw = wf.readframes(wf.getnframes())
            dtype = {1: np.uint8, 2: np.int16, 4: np.int32}.get(sw, np.int16)
            data  = np.frombuffer(raw, dtype=dtype).astype(np.float32)
            if sw == 1:   data = data / 128.0 - 1.0
            elif sw == 2: data = data / 32768.0
            else:         data = data / 2147483648.0
            if nc > 1:
                data = data.reshape(-1, nc).mean(axis=1)
            if fsr != sr:
                n_new = int(len(data) * sr / fsr)
                data  = np.interp(
                    np.linspace(0, len(data)-1, n_new),
                    np.arange(len(data)), data
                )
            return data.astype(np.float32)
        except Exception as e:
            print(f"[AUDIO] WAV load error: {e}")
            return None

    # ── Load MP3 — tries pydub first, then imageio-ffmpeg, then subprocess ─────
    def load_mp3(path):
        # Method 1: pydub (most reliable — pip install pydub)
        try:
            from pydub import AudioSegment
            print("[AUDIO] Loading MP3 with pydub...")
            audio   = AudioSegment.from_file(path)
            audio   = audio.set_frame_rate(sr).set_channels(1)
            samples = np.array(
                audio.get_array_of_samples(), dtype=np.float32
            )
            samples /= (2 ** (8 * audio.sample_width - 1))
            print("[AUDIO] MP3 loaded OK via pydub")
            return samples.astype(np.float32)
        except ImportError:
            pass   # pydub not installed, try next method
        except Exception as e:
            print(f"[AUDIO] pydub error: {e}")

        # Method 2: imageio-ffmpeg (bundled with MoviePy — already installed)
        try:
            import imageio_ffmpeg, subprocess, tempfile
            ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
            print(f"[AUDIO] Loading MP3 with imageio-ffmpeg...")
            tmp = tempfile.mktemp(suffix=".wav")
            result = subprocess.run([
                ffmpeg_exe, "-y", "-i", path,
                "-ar", str(sr), "-ac", "1", "-f", "wav", tmp
            ], capture_output=True, timeout=60)
            if result.returncode == 0:
                data = load_wav(tmp)
                try: os.remove(tmp)
                except: pass
                if data is not None:
                    print("[AUDIO] MP3 loaded OK via imageio-ffmpeg")
                    return data
        except Exception as e:
            print(f"[AUDIO] imageio-ffmpeg failed: {e}")

        # Method 3: system ffmpeg
        try:
            import subprocess, tempfile
            tmp = tempfile.mktemp(suffix=".wav")
            result = subprocess.run([
                "ffmpeg", "-y", "-i", path,
                "-ar", str(sr), "-ac", "1", "-f", "wav", tmp
            ], capture_output=True, timeout=60)
            if result.returncode == 0:
                data = load_wav(tmp)
                try: os.remove(tmp)
                except: pass
                if data is not None:
                    print("[AUDIO] MP3 loaded OK via system ffmpeg")
                    return data
        except Exception as e:
            print(f"[AUDIO] system ffmpeg failed: {e}")

        print("[AUDIO] All MP3 loaders failed — using ticks only")
        print("[AUDIO] Fix: pip install pydub  (already done!)")
        print("[AUDIO] If still failing, MP3 file may be corrupt/missing")
        return None

    # ── Load both tracks ──────────────────────────────────────────────────────
    ticks = load_wav(ticks_path)
    if ticks is None:
        return None

    ext  = os.path.splitext(song_path)[1].lower()
    song = load_mp3(song_path) if ext in (".mp3", ".ogg", ".flac", ".m4a")            else load_wav(song_path)
    if song is None:
        print("[AUDIO] Could not load song — using ticks only")
        return None

    total_samples = len(ticks)

    # ── Loop or trim song to match ticks length ───────────────────────────────
    if len(song) < total_samples:
        repeats   = (total_samples // len(song)) + 1
        song      = np.tile(song, repeats)
    song = song[:total_samples]

    # ── Normalise each track then apply volumes ───────────────────────────────
    def norm(sig, target):
        peak = np.max(np.abs(sig))
        return (sig / peak * target) if peak > 0 else sig

    song_scaled  = norm(song,  bg_vol)
    ticks_scaled = norm(ticks, tick_vol)

    # ── Mix ───────────────────────────────────────────────────────────────────
    mixed = song_scaled + ticks_scaled

    # Soft limiter — prevents clipping
    mixed = np.tanh(mixed * 1.2) / 1.2 * 0.90

    # ── Save mixed WAV ────────────────────────────────────────────────────────
    out_path  = "quiz_audio_mixed.wav"
    audio_int = (mixed * 32767).astype(np.int16)
    with wave.open(out_path, "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(audio_int.tobytes())

    print(f"[AUDIO] Mixed audio saved → {out_path} "
          f"(song {bg_vol:.0%} + ticks {tick_vol:.0%})")
    return out_path


def _render_frames(quiz: dict, cfg: dict) -> tuple:
    """
    Render all animation frames + answer frame + audio.
    Returns (quiz_frames_list, answer_frame_path, audio_path).
    Frames are rendered at base 1080x1920 — resize happens at export.
    """
    fps   = cfg["fps"]
    q_sec = cfg["quiz_display_sec"]
    a_sec = cfg["answer_display_sec"]

    print("\n[VIDEO] Rendering animated quiz frames (this may take ~30s)...")

    quiz_frames       = []
    total_quiz_frames = int(fps * q_sec)

    for f in range(total_quiz_frames):
        elapsed    = f / fps
        frame_img  = render_quiz_frame_at(quiz, cfg, elapsed, q_sec)
        frame_path = f"_qframe_{f:05d}.png"
        frame_img.save(frame_path)
        quiz_frames.append(frame_path)
        # Save first frame separately for Instagram/Facebook image post
        if f == 0:
            # Absolute path so upload_make can always find it
            script_dir       = os.path.dirname(os.path.abspath(__file__))
            first_frame_path = os.path.join(script_dir, "quiz_first_frame.jpg")
            frame_img.convert("RGB").save(
                first_frame_path, "JPEG", quality=95
            )
            cfg["_first_frame_path"] = first_frame_path
            print(f"[VIDEO] First frame → {first_frame_path}")
        if f % fps == 0:
            print(f"  Rendered {f//fps}/{int(q_sec)}s of quiz animation...")

    print(f"[VIDEO] {total_quiz_frames} frames done. Building answer frame...")
    answer_frame_path = render_answer_frame(quiz, cfg)

    print("[AUDIO] Synthesizing tick/buzzer soundtrack...")
    audio_path = generate_audio(q_sec, a_sec, cfg)

    # ── Pick background song (alternates every run) ───────────────────────────
    bg_music_path = _pick_bg_music(cfg)
    if bg_music_path:
        print(f"[AUDIO] Mixing song: {os.path.basename(bg_music_path)}")
        mixed = _mix_audio(audio_path, bg_music_path, cfg)
        if mixed:
            audio_path = mixed   # use the mixed version

    # ── Render promo frame (shown between quiz and answer) ────────────────────
    promo_frame_path = render_promo_frame(cfg)

    return quiz_frames, answer_frame_path, audio_path, promo_frame_path


def _assemble_video(quiz_frames: list, answer_frame_path: str,
                    audio_path: str, output_path: str,
                    platform: str, cfg: dict,
                    promo_frame_path: str = None) -> str:
    """
    Assemble frames into a platform-optimised MP4.
    Applies correct bitrate and resolution for the target platform.
    """
    spec  = PLATFORM_SPECS.get(platform, PLATFORM_SPECS["youtube"])
    fps   = spec["fps"]
    brate = spec["bitrate"]
    W     = spec["width"]
    H     = spec["height"]
    a_sec = cfg["answer_display_sec"]

    try:
        from moviepy import ImageSequenceClip, AudioFileClip, concatenate_videoclips
    except ImportError:
        from moviepy.editor import ImageSequenceClip, AudioFileClip, concatenate_videoclips

    PROMO_SEC   = 2   # promo frame duration in seconds
    quiz_clip   = ImageSequenceClip(quiz_frames, fps=fps)
    answer_clip = _make_image_clip(answer_frame_path, a_sec, fps)

    # Insert promo frame between quiz and answer
    if promo_frame_path and os.path.exists(promo_frame_path):
        promo_clip = _make_image_clip(promo_frame_path, PROMO_SEC, fps)
        video      = concatenate_videoclips(
            [quiz_clip, promo_clip, answer_clip], method="compose"
        )
        print(f"[VIDEO] Sequence: quiz({cfg['quiz_display_sec']}s) → "
              f"promo({PROMO_SEC}s) → answer({a_sec}s)")
    else:
        video = concatenate_videoclips([quiz_clip, answer_clip], method="compose")

    # Resize if platform needs different dimensions (future-proofing)
    if video.w != W or video.h != H:
        try:
            video = video.resized((W, H))
        except AttributeError:
            video = video.resize((W, H))

    # Attach audio
    audio_clip = AudioFileClip(audio_path)
    if audio_clip.duration > video.duration:
        try:
            audio_clip = audio_clip.subclipped(0, video.duration)
        except AttributeError:
            audio_clip = audio_clip.subclip(0, video.duration)
    try:
        video = video.with_audio(audio_clip)
    except AttributeError:
        video = video.set_audio(audio_clip)

    write_kwargs = dict(
        fps=fps,
        codec="libx264",
        audio_codec="aac",
        bitrate=brate,
        logger="bar",
    )
    try:
        video.write_videofile(output_path, **write_kwargs)
    except Exception:
        write_kwargs.pop("audio_codec", None)
        write_kwargs.pop("bitrate",     None)
        video.write_videofile(output_path, **write_kwargs)

    size_mb = os.path.getsize(output_path) / (1024*1024)
    print(f"[VIDEO] {platform.upper()} → {output_path} ({size_mb:.1f} MB, "
          f"{W}x{H} @ {fps}fps, bitrate={brate})")

    # Warn if over platform size limit
    max_mb = spec.get("max_mb")
    if max_mb and size_mb > max_mb:
        print(f"[VIDEO] WARNING: {size_mb:.1f}MB exceeds {platform} limit of {max_mb}MB!")

    return output_path


def create_video(quiz: dict, cfg: dict) -> str:
    """
    Render frames ONCE, then export platform-specific MP4 files.

    Returns path to the PRIMARY video (used for YouTube + desktop save).
    Platform-specific copies are stored as:
      quiz_output_youtube.mp4
      quiz_output_instagram.mp4  (also used for Make.com webhook)
      quiz_output_facebook.mp4

    Each copy has the correct bitrate/size for that platform.
    """
    # Determine which platforms are active
    active = []
    if cfg.get("youtube_upload"):   active.append("youtube")
    if cfg.get("facebook_upload"):  active.append("facebook")
    if cfg.get("instagram_upload"): active.append("instagram")
    if cfg.get("make_upload"):      active.append("make")
    if not active:
        active = ["youtube"]   # default — always render at least one

    # Render frames ONCE (shared across all platforms)
    quiz_frames, answer_frame_path, audio_path, promo_frame_path = _render_frames(quiz, cfg)

    print(f"\n[VIDEO] Exporting for platforms: {', '.join(active)}")

    outputs = {}
    base    = os.path.splitext(cfg["output_video"])[0]   # e.g. "quiz_output"

    for platform in active:
        out_path = f"{base}_{platform}.mp4"
        _assemble_video(quiz_frames, answer_frame_path, audio_path,
                        out_path, platform, cfg, promo_frame_path)
        outputs[platform] = out_path

    # Cleanup shared temp files
    for f in quiz_frames:
        if os.path.exists(f): os.remove(f)
    for f in [answer_frame_path, audio_path, "quiz_audio_mixed.wav",
              promo_frame_path if promo_frame_path else ""]:
        if f and os.path.exists(f): os.remove(f)

    # Store platform paths for uploaders to use
    cfg["_platform_videos"] = outputs

    # Primary output = youtube version (or first available)
    primary = outputs.get("youtube") or next(iter(outputs.values()))
    return primary


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║                  STEP 3 — PLATFORM UPLOADERS                            ║
# ╚══════════════════════════════════════════════════════════════════════════╝

def _build_description(quiz: dict) -> str:
    """Build a clean plain-text description safe for all platform APIs."""
    import re

    explanation = quiz.get("explanation", "")
    lang        = quiz.get("language", "").lower()
    qtype       = quiz.get("question_type", "")

    # Strip emojis and non-ASCII characters that YouTube rejects
    def clean(text: str) -> str:
        # Remove emoji and special Unicode symbols
        text = re.sub(r'[^\x00-\x7F]+', '', text)
        # Collapse excess whitespace
        text = re.sub(r'\n{3,}', '\n\n', text).strip()
        return text

    raw = (
        f"{qtype} -- {quiz['language']} Quiz!\n\n"
        f"Can you figure it out? Drop your answer in the comments!\n\n"
        f"--- ANSWER (scroll to reveal) ---\n\n"
        f"{explanation}\n\n"
        f"------------------------\n"
        f"Need a Website or Web App?\n"
        f"I am a Fullstack Developer!\n\n"
        f"Services: Websites, Web Apps, AI Chatbots & Automation\n\n"
        f"Visit my agency: https://agency-website.mustufaaijaz1234.workers.dev\n"
        f"Email: mustufaaijaz1234@gmail.com\n"
        f"------------------------\n\n"
        f"#coding #quiz #{lang} #programming #developer "
        f"#codingquiz #learntocode #techquiz #shorts "
        f"#webdeveloper #fullstackdeveloper #webdev #freelancer"
    )
    return clean(raw)


# ── YouTube Shorts ────────────────────────────────────────────────────────────

YOUTUBE_SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.force-ssl",
]


def upload_youtube(video_path: str, quiz: dict, cfg: dict):
    """Upload video as a YouTube Short using OAuth2 (console/manual flow)."""
    import pickle
    from google.auth.transport.requests import Request

    token_path = os.path.join(os.path.dirname(cfg["youtube_secrets_file"]), "token.pickle")

    credentials = None

    # ── Load saved token if it exists ────────────────────────────────────────
    if os.path.exists(token_path):
        with open(token_path, "rb") as f:
            credentials = pickle.load(f)

    # ── Refresh if expired ────────────────────────────────────────────────────
    if credentials and credentials.expired and credentials.refresh_token:
        print("[YOUTUBE] Refreshing expired token...")
        credentials.refresh(Request())

    # ── First-time auth: show URL, user pastes code ───────────────────────────
    if not credentials or not credentials.valid:
        print("\n[YOUTUBE] Authenticating...")
        flow = google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file(
            cfg["youtube_secrets_file"], YOUTUBE_SCOPES
        )

        # Use console flow — no browser redirect, no localhost server needed
        flow.redirect_uri = "urn:ietf:wg:oauth:2.0:oob"
        auth_url, _ = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            prompt="consent",
        )

        print("\n" + "="*60)
        print("  YOUTUBE AUTH — Follow these steps:")
        print("="*60)
        print("1. Copy this URL and open it in your browser:")
        print(f"\n   {auth_url}\n")
        print("2. Log in with mustufaaijaz1234@gmail.com")
        print("3. Click Advanced → Go to QuizAgent (unsafe) → Allow")
        print("4. Copy the CODE shown on the final page")
        print("="*60)

        code = input("\nPaste the code here and press Enter: ").strip()
        flow.fetch_token(code=code)
        credentials = flow.credentials

        # Save token for future runs
        with open(token_path, "wb") as f:
            pickle.dump(credentials, f)
        print("[YOUTUBE] ✅ Token saved — won't ask again next run!")

    youtube = googleapiclient.discovery.build("youtube", "v3", credentials=credentials)

    import re
    def _clean(text: str) -> str:
        return re.sub(r'[^\x00-\x7F]+', '', text).strip()

    title       = _clean(f"Can You {quiz['question_type']}? {quiz['language']} Quiz #Shorts")
    description = _build_description(quiz)

    request_body = {
        "snippet": {
            "title":       title[:100],
            "description": description[:4900],   # safe buffer below 5000 limit
            "tags":        ["coding", "quiz", quiz["language"], "shorts", "programming",
                            "codingquiz", "learntocode"],
            "categoryId":  "28",                 # Science & Technology
            "defaultLanguage": "en",
        },
        "status": {
            "privacyStatus":            "public",
            "selfDeclaredMadeForKids":  False,
            "madeForKids":              False,
        },
    }

    media = MediaFileUpload(video_path, mimetype="video/mp4", resumable=True)

    print(f"[YOUTUBE] Uploading '{title}'...")
    try:
        response = youtube.videos().insert(
            part="snippet,status",
            body=request_body,
            media_body=media,
        ).execute()
    except Exception as e:
        # Print full error details for easier debugging
        print(f"[YOUTUBE] Upload error details: {e}")
        raise

    video_id = response.get("id", "unknown")
    print(f"[YOUTUBE] ✅ Upload successful! https://youtu.be/{video_id}")
    return video_id


# ── Facebook Reels ────────────────────────────────────────────────────────────

def upload_facebook(video_path: str, quiz: dict, cfg: dict):
    """Upload video as a Facebook Reel using Graph API."""
    token   = cfg["fb_access_token"]
    page_id = cfg["fb_page_id"]
    desc    = _build_description(quiz)

    print("\n[FACEBOOK] Initiating upload session...")

    # Step 1: Initialize upload
    init_url = f"https://graph.facebook.com/v19.0/{page_id}/video_reels"
    init_resp = requests.post(init_url, data={
        "upload_phase": "start",
        "access_token": token,
    })
    init_data = init_resp.json()
    if "video_id" not in init_data:
        print(f"[FACEBOOK] ❌ Init failed: {init_data}")
        return None

    video_id     = init_data["video_id"]
    upload_url   = init_data.get("upload_url")
    file_size    = os.path.getsize(video_path)

    # Step 2: Upload binary
    print(f"[FACEBOOK] Uploading video (id={video_id})...")
    with open(video_path, "rb") as f:
        upload_resp = requests.post(
            upload_url,
            headers={
                "Authorization": f"OAuth {token}",
                "offset": "0",
                "file_size": str(file_size),
            },
            data=f,
        )
    if upload_resp.status_code not in (200, 201):
        print(f"[FACEBOOK] ❌ Upload failed: {upload_resp.text}")
        return None

    # Step 3: Finish & publish
    finish_resp = requests.post(init_url, data={
        "upload_phase": "finish",
        "video_id":     video_id,
        "access_token": token,
        "video_state":  "PUBLISHED",
        "description":  desc[:2200],
    })
    finish_data = finish_resp.json()
    if finish_data.get("success"):
        print(f"[FACEBOOK] ✅ Reel published! Video ID: {video_id}")
    else:
        print(f"[FACEBOOK] ⚠️  Finish response: {finish_data}")

    return video_id


# ── Instagram Reels ───────────────────────────────────────────────────────────

def upload_instagram(video_path: str, quiz: dict, cfg: dict):
    """Upload video as an Instagram Reel using Graph API (2-step: create + publish)."""
    token   = cfg["ig_access_token"]
    user_id = cfg["ig_user_id"]
    caption = _build_description(quiz)[:2200]

    # NOTE: Instagram requires a PUBLICLY ACCESSIBLE video URL.
    # For local testing, you need to host the file first (e.g., via ngrok or a CDN).
    # Replace VIDEO_URL below with the actual public URL of your uploaded video.
    # If your video is already hosted (e.g., after Facebook upload), use that URL.
    VIDEO_URL = "https://YOUR_PUBLIC_VIDEO_URL/quiz_output.mp4"

    print("\n[INSTAGRAM] Creating media container...")
    create_url = f"https://graph.facebook.com/v19.0/{user_id}/media"
    create_resp = requests.post(create_url, data={
        "media_type":  "REELS",
        "video_url":   VIDEO_URL,
        "caption":     caption,
        "access_token": token,
    })
    create_data = create_resp.json()

    if "id" not in create_data:
        print(f"[INSTAGRAM] ❌ Container creation failed: {create_data}")
        return None

    container_id = create_data["id"]
    print(f"[INSTAGRAM] Container created (id={container_id}). Waiting for processing...")

    # Poll until video is ready
    for attempt in range(10):
        time.sleep(10)
        status_resp = requests.get(
            f"https://graph.facebook.com/v19.0/{container_id}",
            params={"fields": "status_code", "access_token": token},
        )
        status = status_resp.json().get("status_code", "")
        print(f"[INSTAGRAM] Status: {status} (attempt {attempt + 1})")
        if status == "FINISHED":
            break
        if status == "ERROR":
            print("[INSTAGRAM] ❌ Processing error.")
            return None

    # Publish
    pub_url = f"https://graph.facebook.com/v19.0/{user_id}/media_publish"
    pub_resp = requests.post(pub_url, data={
        "creation_id":  container_id,
        "access_token": token,
    })
    pub_data = pub_resp.json()
    media_id = pub_data.get("id")
    if media_id:
        print(f"[INSTAGRAM] ✅ Reel published! Media ID: {media_id}")
    else:
        print(f"[INSTAGRAM] ⚠️  Publish response: {pub_data}")

    return media_id


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║                          MAIN ORCHESTRATOR                              ║
# ╚══════════════════════════════════════════════════════════════════════════╝


# ── Make.com Webhook Uploader ────────────────────────────────────────────

def upload_to_host(video_path: str) -> str:
    """
    Upload video to a free public host so Make.com/Instagram can access it.
    Tries 4 different hosts in order — stops at first success.

    Hosts tried:
      1. file.io       — simple POST, returns JSON with link
      2. litterbox.catbox.moe — reliable, 72h expiry
      3. 0x0.st        — simple POST
      4. uguu.se        — anime file host, works globally
    """
    filename = os.path.basename(video_path)
    file_size_mb = os.path.getsize(video_path) / (1024 * 1024)
    print(f"[HOST] Uploading {filename} ({file_size_mb:.1f} MB) to public host...")

    # ── 1. file.io ────────────────────────────────────────────────────────────
    try:
        print("[HOST] Trying file.io...")
        with open(video_path, "rb") as f:
            resp = requests.post(
                "https://file.io",
                files={"file": (filename, f, "video/mp4")},
                data={"expires": "14d", "maxDownloads": 100},
                timeout=120,
            )
        if resp.status_code == 200:
            data = resp.json()
            if data.get("success") and data.get("link"):
                url = data["link"]
                print(f"[HOST] file.io URL: {url}")
                return url
            print(f"[HOST] file.io response: {data}")
    except Exception as e:
        print(f"[HOST] file.io failed: {e}")

    # ── 2. litterbox.catbox.moe ───────────────────────────────────────────────
    try:
        print("[HOST] Trying litterbox.catbox.moe...")
        with open(video_path, "rb") as f:
            resp = requests.post(
                "https://litterbox.catbox.moe/resources/internals/api.php",
                data={"reqtype": "fileupload", "time": "72h"},
                files={"fileToUpload": (filename, f, "video/mp4")},
                timeout=180,
            )
        if resp.status_code == 200 and resp.text.startswith("http"):
            url = resp.text.strip()
            print(f"[HOST] litterbox URL: {url}")
            return url
        print(f"[HOST] litterbox response: {resp.text[:100]}")
    except Exception as e:
        print(f"[HOST] litterbox failed: {e}")

    # ── 3. 0x0.st ─────────────────────────────────────────────────────────────
    try:
        print("[HOST] Trying 0x0.st...")
        with open(video_path, "rb") as f:
            resp = requests.post(
                "https://0x0.st",
                files={"file": (filename, f, "video/mp4")},
                timeout=120,
            )
        if resp.status_code == 200 and resp.text.startswith("http"):
            url = resp.text.strip()
            print(f"[HOST] 0x0.st URL: {url}")
            return url
        print(f"[HOST] 0x0.st response: {resp.text[:100]}")
    except Exception as e:
        print(f"[HOST] 0x0.st failed: {e}")

    # ── 4. uguu.se ────────────────────────────────────────────────────────────
    try:
        print("[HOST] Trying uguu.se...")
        with open(video_path, "rb") as f:
            resp = requests.post(
                "https://uguu.se/upload",
                files={"files[]": (filename, f, "video/mp4")},
                timeout=120,
            )
        if resp.status_code == 200:
            data = resp.json()
            files = data.get("files", [])
            if files and files[0].get("url"):
                url = files[0]["url"]
                print(f"[HOST] uguu.se URL: {url}")
                return url
        print(f"[HOST] uguu.se response: {resp.text[:100]}")
    except Exception as e:
        print(f"[HOST] uguu.se failed: {e}")

    raise RuntimeError(
        "All free hosts failed. Check your internet connection or "
        "set a custom host URL in CONFIG['make_webhook_url'] setup."
    )


def upload_make(video_path: str, quiz: dict, cfg: dict) -> str:
    """
    Send to Make.com webhook → posts as REEL on Instagram + Facebook.

    PAYLOAD SENT:
      video_url   — public MP4 URL  → {{1.video_url}}
      caption     — post caption    → {{1.caption}}
      pin_comment — A/B/C/D votes   → {{1.pin_comment}}
      song        — song name       → {{1.song}}

    MAKE.COM SCENARIO SETUP (5 modules):
    ─────────────────────────────────────────────────
    Module 1 — Webhooks > Custom Webhook (trigger)

    Module 2 — Instagram for Business > Create a Reel
               Connection : your TechLearning account
               Video URL  : {{1.video_url}}
               Caption    : {{1.caption}}
               Share to Feed: Yes

    Module 3 — Instagram for Business > Create a Comment
               Connection : your TechLearning account
               Post ID    : {{2.id}}
               Message    : {{1.pin_comment}}

    Module 4 — Facebook Pages > Create a Video Post
               Connection : TechLearning Page
               Video URL  : {{1.video_url}}
               Description: {{1.caption}}

    Module 5 — Facebook Pages > Create a Comment
               Connection : TechLearning Page
               Post ID    : {{4.id}}
               Message    : {{1.pin_comment}}
    ─────────────────────────────────────────────────
    NOTE: {{1.video_url}} is the public MP4 file with the
    background song already baked in — no manual audio needed.
    """
    import re

    webhook_url = cfg["make_webhook_url"]
    if not webhook_url or webhook_url == "YOUR_MAKE_WEBHOOK_URL":
        raise ValueError("make_webhook_url not configured in CONFIG")

    image_only = cfg.get("make_image_only", True)
    # Use whichever song was actually mixed into the video this run
    songs_list = ["INSONAMIA (SLOWED)", "LUZ ROJA by bxkq"]
    try:
        conn = db_connect()
        cur  = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM askedquestion")
        cnt  = cur.fetchone()[0]
        conn.close()
        song = songs_list[cnt % len(songs_list)]
    except Exception:
        song = cfg.get("make_song", "INSONAMIA (SLOWED)")
    pin        = cfg.get("make_pin_comment", True)

    def clean(text):
        return re.sub(r'[^\x00-\x7F]+', '', text).strip()

    # ── Upload full video — this is what Instagram/Facebook Reel uses ──────────
    size_mb = os.path.getsize(video_path) / (1024*1024)
    print(f"[MAKE] Uploading Reel video: {os.path.basename(video_path)} ({size_mb:.1f} MB)")
    video_url = upload_to_host(video_path)
    print(f"[MAKE] Video URL: {video_url[:80]}")
    image_url = None   # not needed for Reels

    # ── Build caption ─────────────────────────────────────────────────────────
    lang  = quiz["language"]
    qtype = quiz["question_type"]
    opts  = quiz["options"]

    caption = clean(
        f"{qtype} -- {lang} Quiz!\n\n"
        f"Can you figure it out?\n"
        f"Comment A / B / C / D below!\n\n"
        f"Need a website? I am a Fullstack Dev!\n"
        f"https://agency-website.mustufaaijaz1234.workers.dev\n"
        f"DM or Email: mustufaaijaz1234@gmail.com\n\n"
        f"Music: {song}\n\n"
        f"#coding #quiz #{lang.lower()} #programming "
        f"#developer #codingquiz #learntocode #techquiz "
        f"#webdeveloper #fullstackdeveloper #freelancer"
    )[:2200]

    # ── Build pinned vote poll comment ──────────────────────────────────────────
    # Uses emoji letters so followers tap the LIKE on each reply = vote poll
    # Format looks like a real poll in comments section
    emoji_map = {
        "A": "A",
        "B": "B",
        "C": "C",
        "D": "D",
    }
    vote_lines = [
        "VOTE YOUR ANSWER BELOW!",
        "Like the comment that matches your answer!",
        "",
    ]
    for opt in opts:
        letter   = opt[0] if opt else "?"
        text     = opt[3:] if len(opt) > 2 and opt[1] == ")" else opt
        text     = text if len(text) <= 35 else text[:33] + ".."
        emoji    = emoji_map.get(letter, letter)
        vote_lines.append(f"{emoji}) {text}")
    vote_lines += [
        "",
        "Comment your answer!",
        "Answer reveals in next post!",
        "",
        "Follow for daily coding quizzes!",
    ]
    pin_comment = "\n".join(vote_lines)[:500]

    # ── Send webhook ──────────────────────────────────────────────────────────
    # Payload field names match Make.com module variables exactly:
    # {{1.video_url}}   → Instagram Reel video URL
    # {{1.caption}}     → Reel caption
    # {{1.pin_comment}} → pinned comment with vote options
    payload = {
        "video_url":   video_url,       # ← Make.com uses {{1.video_url}}
        "caption":     caption,          # ← Make.com uses {{1.caption}}
        "image_url":   image_url,        # thumbnail (optional)
        "pin_comment": pin_comment if pin else "",
        "song":        song,
        "language":    lang,
        "quiz_type":   qtype,
        "correct":     quiz.get("correct", ""),
        "timestamp":   time.strftime("%Y-%m-%d %H:%M:%S"),
    }

    print(f"\n[MAKE] Sending to webhook: {webhook_url[:50]}...")
    print(f"[MAKE] Video URL: {str(video_url)[:70]}")
    print(f"[MAKE] Song: {song}")
    print(f"[MAKE] Caption preview: {caption[:80]}...")
    print(f"[MAKE] Pin comment:\n{pin_comment[:200]}")

    resp = requests.post(webhook_url, json=payload, timeout=30)

    if resp.status_code in (200, 201, 204):
        print(f"[MAKE] Webhook triggered! Make.com posting Reel to Instagram + Facebook")
        return video_url
    else:
        raise RuntimeError(
            f"Webhook failed: {resp.status_code} — {resp.text[:200]}"
        )

def main():
    print("=" * 65)
    print("  AUTONOMOUS CODING QUIZ AGENT  |  Zero-Cost Edition")
    print(f"  DB: [{DB_SERVER}].[{DB_NAME}].askedquestion")
    print("=" * 65)

    cfg = CONFIG

    # ── 1. Generate quiz (checks DB — never repeats) ──────────────────────────
    quiz = generate_quiz()

    # ── 2. Create video ───────────────────────────────────────────────────────
    video_path = create_video(quiz, cfg)

    # ── 3. Upload to platforms ────────────────────────────────────────────────
    results = {}

    # ── Get platform-specific video paths ────────────────────────────────────
    platform_videos = cfg.get("_platform_videos", {})

    def get_video(platform):
        """Return platform-specific video, falling back to primary."""
        return platform_videos.get(platform, video_path)

    if cfg["youtube_upload"]:
        try:
            yt_video = get_video("youtube")
            print(f"[YOUTUBE] Using: {yt_video}")
            results["youtube"] = upload_youtube(yt_video, quiz, cfg)
        except Exception as e:
            print(f"[YOUTUBE] ❌ Error: {e}")

    if cfg["facebook_upload"]:
        try:
            fb_video = get_video("facebook")
            print(f"[FACEBOOK] Using: {fb_video}")
            results["facebook"] = upload_facebook(fb_video, quiz, cfg)
        except Exception as e:
            print(f"[FACEBOOK] ❌ Error: {e}")

    if cfg["instagram_upload"]:
        try:
            ig_video = get_video("instagram")
            print(f"[INSTAGRAM] Using: {ig_video}")
            results["instagram"] = upload_instagram(ig_video, quiz, cfg)
        except Exception as e:
            print(f"[INSTAGRAM] ❌ Error: {e}")

    if cfg.get("make_upload"):
        try:
            make_video = get_video("make")
            print(f"[MAKE] Using: {make_video}")
            results["make"] = upload_make(make_video, quiz, cfg)
        except Exception as e:
            print(f"[MAKE] ❌ Error: {e}")

    # ── 4. Save to DB — mark as success with platform IDs ─────────────────────
    if any(v for v in results.values() if v):
        mark_quiz_uploaded(quiz, results)
    else:
        print("[DB] ⚠️  No successful uploads — record stays as 'pending'")

    # ── 5. Delete all platform videos from Desktop after upload ─────────────
    platform_videos = cfg.get("_platform_videos", {})
    deleted = []
    if platform_videos:
        for plat, path in platform_videos.items():
            if os.path.exists(path):
                try:
                    os.remove(path)
                    deleted.append(path)
                except Exception as e:
                    print(f"[CLEANUP] Could not delete {path}: {e}")
        if deleted:
            print(f"[CLEANUP] Deleted {len(deleted)} video file(s) from Desktop.")
    # Also delete primary video if it exists separately
    if os.path.exists(video_path) and video_path not in deleted:
        try:
            os.remove(video_path)
            print(f"[CLEANUP] Deleted {video_path}")
        except Exception as e:
            print(f"[CLEANUP] Could not delete {video_path}: {e}")
    # Also delete first frame jpg
    first_frame = cfg.get("_first_frame_path", "")
    if first_frame and os.path.exists(first_frame):
        try:
            os.remove(first_frame)
            print(f"[CLEANUP] Deleted {first_frame}")
        except Exception as e:
            print(f"[CLEANUP] Could not delete {first_frame}: {e}")

    # ── Summary ───────────────────────────────────────────────────────────────
    print("\n" + "=" * 65)
    print("  AGENT RUN COMPLETE")
    print("=" * 65)
    print(f"  Quiz     : {quiz['question_type']} | {quiz['language']}")
    print(f"  Video    : {video_path}")
    for platform, result in results.items():
        status = f"✅ ID: {result}" if result else "❌ Failed"
        print(f"  {platform.capitalize():<12}: {status}")
    print(f"  Database : [{DB_NAME}] → askedquestion")
    print("=" * 65)


if __name__ == "__main__":
    main()
