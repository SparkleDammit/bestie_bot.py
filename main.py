import discord
from discord import app_commands
import os
import sqlite3
import uuid
import asyncio
import threading
from datetime import datetime, timedelta
from flask import Flask, send_file, abort
import io

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
                viewed INTEGER DEFAULT 0,
                FOREIGN KEY (selfie_id) REFERENCES selfies(id)
            )
        """)
        conn.commit()

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
            SELECT t.viewed, t.selfie_id, s.image_data, s.content_type, s.expires_at
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

        import base64
        b64 = base64.b64encode(row["image_data"]).decode("utf-8")
        mime = row["content_type"]

        return f"""
        <html>
        <head><title>Selfie</title></head>
        <body style="background:#000;display:flex;justify-content:center;align-items:center;height:100vh;margin:0;">
        <img src="data:{mime};base64,{b64}" style="max-width:100%;max-height:100vh;">
        </body>
        </html>
        """

def run_flask():
    flask_app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))

# ── Discord bot ────────────────────────────────────────────────────────────────
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

SELFIE_CHANNEL_ID = 1490693842553409786

BASE_URL = os.environ.get("BASE_URL", "https://bestiebotpy-production.up.railway.app")

async def purge_expired():
    """Background task: delete expired selfies and tokens every hour."""
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

    # Only handle images
    if not attachment.content_type or not attachment.content_type.startswith("image/"):
        return

    image_data = await attachment.read()

    # Download image
    await message.delete()
    content_type = attachment.content_type
    uploader_id = str(message.author.id)
    uploader_name = message.author.display_name
    expires_at = datetime.utcnow() + timedelta(hours=12)

    # Save to DB
    with get_db() as conn:
        cursor = conn.execute("""
            INSERT INTO selfies (uploader_id, uploader_name, image_data, content_type, expires_at)
            VALUES (?, ?, ?, ?, ?)
        """, (uploader_id, uploader_name, image_data, content_type, expires_at.isoformat()))
        selfie_id = cursor.lastrowid

        # Get all members in the guild who can see the channel
        guild = message.guild
        members = [m for m in guild.members if not m.bot]

        tokens_created = 0
        for member in members:
            token = str(uuid.uuid4())
            conn.execute("""
                INSERT INTO tokens (token, selfie_id, user_id)
                VALUES (?, ?, ?)
            """, (token, selfie_id, str(member.id)))
            tokens_created += 1

        conn.commit()

    # Confirm to uploader
    try:
        await message.channel.send(
            f"{message.author.mention} Your selfie has been sent to **{tokens_created} members**. "
            f"Use `/views` to check how many have opened it. *(This message deletes in 10 seconds)*",
            delete_after=10
        )
    except Exception:
        pass

    # Post public notification in the selfie channel
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
