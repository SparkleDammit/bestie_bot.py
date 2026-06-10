import discord
from discord import app_commands
import os
import sqlite3
import uuid
import asyncio
import threading
import base64
import io
from datetime import datetime, timedelta
from flask import Flask, abort
from PIL import Image, ImageDraw, ImageFont

# ── Flask app ──────────────────────────────────────────────────────────────────
flask_app = Flask(__name__)

def get_db():
    conn = sqlite3.connect("selfies.db")
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS selfies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                uploader_id TEXT NOT NULL,
                uploader_name TEXT NOT NULL,
                image_data BLOB NOT NULL,
                content_type TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tokens (
                token TEXT PRIMARY KEY,
                selfie_id INTEGER NOT NULL,
                user_id TEXT NOT NULL,
                viewer_name TEXT NOT NULL DEFAULT '',
                viewed INTEGER DEFAULT 0,
                screenshot_notified INTEGER DEFAULT 0,
                FOREIGN KEY (selfie_id) REFERENCES selfies(id)
            )
        """)
        conn.commit()

def watermark_image(image_data, content_type, viewer_name, timestamp):
    img = Image.open(io.BytesIO(image_data)).convert("RGBA")
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 28)
        small_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 20)
    except Exception:
        font = ImageFont.load_default()
        small_font = font

    text = f"{viewer_name}"
    subtext = f"viewed {timestamp}"

    w, h = img.size
    margin = 20

    # Semi-transparent background box
    bbox = draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]

    bbox2 = draw.textbbox((0, 0), subtext, font=small_font)
    sub_w = bbox2[2] - bbox2[0]

    box_w = max(text_w, sub_w) + 20
    box_h = text_h + 30 + 10
    box_x = w - box_w - margin
    box_y = h - box_h - margin

    draw.rectangle(
        [box_x - 10, box_y - 10, box_x + box_w, box_y + box_h],
        fill=(0, 0, 0, 120)
    )

    draw.text((box_x, box_y), text, font=font, fill=(255, 255, 255, 180))
    draw.text((box_x, box_y + text_h + 8), subtext, font=small_font, fill=(200, 200, 200, 150))

    watermarked = Image.alpha_composite(img, overlay)

    output = io.BytesIO()
    watermarked = watermarked.convert("RGB")
    watermarked.save(output, format="JPEG", quality=90)
    return output.getvalue()

@flask_app.route("/view/<token>")
def view_image(token):
    with get_db() as conn:
        row = conn.execute("""
            SELECT t.viewed, s.uploader_name, s.expires_at
            FROM tokens t
            JOIN selfies s ON t.selfie_id = s.id
            WHERE t.token = ?
        """, (token,)).fetchone()

        if not row:
            return "<h2>This link is invalid.</h2>", 404

        if row["viewed"]:
            return "<h2>This image has already been viewed and is no longer available.</h2>", 410

        if datetime.utcnow() > datetime.fromisoformat(row["expires_at"]):
            return "<h2>This link has expired.</h2>", 410

        return f"""
        <html>
        <head><title>Selfie</title></head>
        <body style="background:#111;display:flex;flex-direction:column;justify-content:center;align-items:center;height:100vh;margin:0;font-family:sans-serif;color:white;">
        <p style="margin-bottom:20px;">{row['uploader_name']} posted a selfie for you. Once you view it, it's gone.</p>
        <a href="/open/{token}" style="background:#e05;color:white;padding:14px 32px;border-radius:8px;text-decoration:none;font-size:18px;">View Selfie</a>
        </body>
        </html>
        """

@flask_app.route("/open/<token>")
def open_image(token):
    with get_db() as conn:
        row = conn.execute("""
            SELECT t.viewed, t.selfie_id, s.image_data, s.content_type, s.expires_at, s.uploader_id, t.user_id, t.viewer_name
            FROM tokens t
            JOIN selfies s ON t.selfie_id = s.id
            WHERE t.token = ?
        """, (token,)).fetchone()

        if not row:
            return "<h2>This link is invalid.</h2>", 404

        if row["viewed"]:
            return "<h2>This image has already been viewed and is no longer available.</h2>", 410

        if datetime.utcnow() > datetime.fromisoformat(row["expires_at"]):
            return "<h2>This link has expired.</h2>", 410

        conn.execute("UPDATE tokens SET viewed = 1 WHERE token = ?", (token,))
        conn.commit()

        timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
        viewer_name = row["viewer_name"] or "unknown"

        try:
            wm_data = watermark_image(row["image_data"], row["content_type"], viewer_name, timestamp)
            b64 = base64.b64encode(wm_data).decode("utf-8")
            mime = "image/jpeg"
        except Exception:
            b64 = base64.b64encode(row["image_data"]).decode("utf-8")
            mime = row["content_type"]

        return f"""
        <html>
        <head>
        <title>Selfie</title>
        <style>
            * {{ margin: 0; padding: 0; box-sizing: border-box; }}
            body {{
                background: #000;
                display: flex;
                flex-direction: column;
                justify-content: center;
                align-items: center;
                height: 100vh;
                font-family: sans-serif;
                color: white;
                user-select: none;
                -webkit-user-select: none;
            }}
            #countdown {{
                font-size: 22px;
                margin-bottom: 16px;
                letter-spacing: 2px;
                color: #e05;
            }}
            #img-wrap img {{
                max-width: 100vw;
                max-height: 85vh;
                pointer-events: none;
            }}
            #gone {{
                display: none;
                font-size: 28px;
                color: #555;
                text-align: center;
            }}
        </style>
        </head>
        <body oncontextmenu="return false" ondragstart="return false">
        <div id="countdown">This image will self-destruct in <span id="timer">10</span>s</div>
        <div id="img-wrap">
            <img id="selfie-img" src="data:{mime};base64,{b64}" draggable="false">
        </div>
        <div id="gone">This image has been destroyed.</div>

        <script>
            // Block save shortcuts
            document.addEventListener("keydown", function(e) {{
                if (
                    e.key === "PrintScreen" ||
                    (e.ctrlKey && ["s","u","p","a"].includes(e.key.toLowerCase())) ||
                    e.key === "F12"
                ) {{
                    e.preventDefault();
                    notifyScreenshot();
                }}
            }});

            // Visibility change (tab switch, screen lock, screenshot tools)
            document.addEventListener("visibilitychange", function() {{
                if (document.hidden) {{
                    notifyScreenshot();
                }}
            }});

            let seconds = 10;
            const timerEl = document.getElementById("timer");
            const imgWrap = document.getElementById("img-wrap");
            const gone = document.getElementById("gone");
            const countdown = document.getElementById("countdown");

            const interval = setInterval(() => {{
                seconds--;
                timerEl.textContent = seconds;
                if (seconds <= 0) {{
                    clearInterval(interval);
                    imgWrap.style.display = "none";
                    countdown.style.display = "none";
                    gone.style.display = "block";
                    document.getElementById("selfie-img").src = "";
                }}
            }}, 1000);

            function notifyScreenshot() {{
                fetch("/screenshot/{token}", {{ method: "POST" }});
            }}
        </script>
        </body>
        </html>
        """

@flask_app.route("/screenshot/<token>", methods=["POST"])
def screenshot_detected(token):
    with get_db() as conn:
        row = conn.execute("""
            SELECT s.uploader_id, t.user_id, t.viewer_name
            FROM tokens t
            JOIN selfies s ON t.selfie_id = s.id
            WHERE t.token = ?
        """, (token,)).fetchone()

        if not row:
            return "", 204

        existing = conn.execute(
            "SELECT 1 FROM tokens WHERE token = ? AND screenshot_notified = 1", (token,)
        ).fetchone()
        if existing:
            return "", 204

        conn.execute("UPDATE tokens SET screenshot_notified = 1 WHERE token = ?", (token,))
        conn.commit()

    asyncio.run_coroutine_threadsafe(
        notify_screenshot(row["uploader_id"], row["viewer_name"]),
        client.loop
    )
    return "", 204

async def notify_screenshot(uploader_id, viewer_name):
    try:
        guild = client.guilds[0]
        channel = guild.get_channel(1490667068113031178)
        if channel:
            await channel.send(
                f"⚠️ <@&1487455965409448106> **{viewer_name}** may have taken a screenshot of a selfie."
            )
    except Exception:
        pass

def run_flask():
    flask_app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))

# ── Discord bot ────────────────────────────────────────────────────────────────
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

SELFIE_CHANNEL_ID = 1514310860926095470
BASE_URL = os.environ.get("BASE_URL", "https://bestiebotpy-production.up.railway.app")

async def purge_expired():
    await client.wait_until_ready()
    while not client.is_closed():
        with get_db() as conn:
            conn.execute("""
                DELETE FROM tokens WHERE selfie_id IN (
                    SELECT id FROM selfies WHERE expires_at < datetime('now')
                )
            """)
            conn.execute("DELETE FROM selfies WHERE expires_at < datetime('now')")
            conn.commit()
        await asyncio.sleep(3600)

@client.event
async def on_message(message):
    if message.author.bot:
        return
    if message.channel.id != SELFIE_CHANNEL_ID:
        return
    if not message.attachments:
        return

    attachment = message.attachments[0]

    if not attachment.content_type or not attachment.content_type.startswith("image/"):
        return

    # Download image FIRST before deleting
    image_data = await attachment.read()

    await message.delete()

    content_type = attachment.content_type
    uploader_id = str(message.author.id)
    uploader_name = message.author.display_name
    expires_at = datetime.utcnow() + timedelta(hours=12)

    with get_db() as conn:
        cursor = conn.execute("""
            INSERT INTO selfies (uploader_id, uploader_name, image_data, content_type, expires_at)
            VALUES (?, ?, ?, ?, ?)
        """, (uploader_id, uploader_name, image_data, content_type, expires_at.isoformat()))
        selfie_id = cursor.lastrowid

        guild = message.guild
        members = [m for m in guild.members if not m.bot]

        tokens_created = 0
        for member in members:
            token = str(uuid.uuid4())
            conn.execute("""
                INSERT INTO tokens (token, selfie_id, user_id, viewer_name)
                VALUES (?, ?, ?, ?)
            """, (token, selfie_id, str(member.id), member.display_name))
            tokens_created += 1

        conn.commit()

    try:
        await message.channel.send(
            f"{message.author.mention} Your selfie has been sent to **{tokens_created} members**. "
            f"Use `/views` to check how many have opened it. *(This message deletes in 10 seconds)*",
            delete_after=10
        )
    except Exception:
        pass

    try:
        await message.channel.send(
            f"📸 **{uploader_name}** posted a selfie — use `/selfie` to claim your one-time link. Expires in 12 hours."
        )
    except Exception:
        pass

@tree.command(name="selfie", description="Check if there's a selfie waiting for you")
async def selfie(interaction: discord.Interaction):
    user_id = str(interaction.user.id)

    with get_db() as conn:
        row = conn.execute("""
            SELECT t.token, s.uploader_name, s.expires_at
            FROM tokens t
            JOIN selfies s ON t.selfie_id = s.id
            WHERE t.user_id = ? AND t.viewed = 0
            AND s.expires_at > datetime('now')
            ORDER BY s.created_at DESC
            LIMIT 1
        """, (user_id,)).fetchone()

    if not row:
        await interaction.response.send_message(
            "No selfies waiting for you right now.",
            ephemeral=True
        )
        return

    link = f"{BASE_URL}/view/{row['token']}"
    uploader = row["uploader_name"]
    expires = datetime.fromisoformat(row["expires_at"]).strftime("%H:%M UTC")

    await interaction.response.send_message(
        f"**{uploader}** posted a selfie for you.\n"
        f"[View it here]({link})\n"
        f"*Expires at {expires} — one view only.*",
        ephemeral=True
    )

@tree.command(name="views", description="See how many people have viewed your most recent selfie")
async def views(interaction: discord.Interaction):
    user_id = str(interaction.user.id)

    with get_db() as conn:
        row = conn.execute("""
            SELECT id, uploader_name, created_at FROM selfies
            WHERE uploader_id = ?
            ORDER BY created_at DESC
            LIMIT 1
        """, (user_id,)).fetchone()

        if not row:
            await interaction.response.send_message(
                "You haven't posted any selfies yet.",
                ephemeral=True
            )
            return

        selfie_id = row["id"]
        total = conn.execute("SELECT COUNT(*) FROM tokens WHERE selfie_id = ?", (selfie_id,)).fetchone()[0]
        viewed = conn.execute("SELECT COUNT(*) FROM tokens WHERE selfie_id = ? AND viewed = 1", (selfie_id,)).fetchone()[0]

    await interaction.response.send_message(
        f"**{viewed}** out of **{total}** people have viewed your selfie.",
        ephemeral=True
    )

# ── Existing commands ──────────────────────────────────────────────────────────

@tree.command(name="check", description="Trigger an anonymous comfort check")
@app_commands.describe(color="Optional: signal a specific light without a full check-in")
@app_commands.choices(color=[
    app_commands.Choice(name="green", value="green"),
    app_commands.Choice(name="yellow", value="yellow"),
    app_commands.Choice(name="red", value="red"),
])
async def check(interaction: discord.Interaction, color: app_commands.Choice[str] = None):
    await interaction.response.send_message(
        "Your comfort check has been sent.",
        ephemeral=True
    )

    if color is None:
        await interaction.channel.send(
            "**COMFORT CHECK IN**\n\n"
            "<:GO:1490423634366304428> **Good to go.** I'm present, I'm in, keep going.\n"
            "<:WAIT:1490423509812511084> **Please wait.** Something shifted. I'm not sure. Pause here. Check in. Pull back.\n"
            "<:STOP:1490423467500109994> **Please stop.** This ends now."
        )
    elif color.value == "green":
        await interaction.channel.send("<:GO:1490423634366304428>")
    elif color.value == "yellow":
        await interaction.channel.send("<:WAIT:1490423509812511084>")
    elif color.value == "red":
        await interaction.channel.send("<:STOP:1490423467500109994>")

@tree.command(name="linkdrop", description="Anonymously post a link or message, with an optional role ping")
@app_commands.describe(
    message="Your message or link",
    role="Optional: ping a role"
)
@app_commands.choices(role=[
    app_commands.Choice(name="Cocktroller", value="Cocktroller"),
    app_commands.Choice(name="Cuntroller", value="Cuntroller"),
    app_commands.Choice(name="Both", value="both"),
])
async def linkdrop(interaction: discord.Interaction, message: str, role: app_commands.Choice[str] = None):
    await interaction.response.send_message(
        "Your link drop has been posted.",
        ephemeral=True
    )

    ping_text = ""
    if role is not None:
        if role.value in ("Cocktroller", "both"):
            r = discord.utils.get(interaction.guild.roles, name="Cocktroller")
            if r:
                ping_text += r.mention + " "
        if role.value in ("Cuntroller", "both"):
            r = discord.utils.get(interaction.guild.roles, name="Cuntroller")
            if r:
                ping_text += r.mention + " "

    await interaction.channel.send(
        f"{ping_text}\n{message}".strip()
    )

@client.event
async def on_ready():
    init_db()
    guild = discord.Object(id=1487446782219911241)
    tree.copy_global_to(guild=guild)
    await tree.sync(guild=guild)
    client.loop.create_task(purge_expired())
    print(f"Logged in as {client.user}")

# ── Run both Flask and Discord together ───────────────────────────────────────
flask_thread = threading.Thread(target=run_flask, daemon=True)
flask_thread.start()

client.run(os.environ["DISCORD_TOKEN"])
