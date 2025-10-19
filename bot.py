import os
import asyncio
import aiosqlite
import discord
from discord import app_commands
from dotenv import load_dotenv

# --- KEEP ALIVE SERVER ---
import os
from flask import Flask
from threading import Thread

app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running!"

def run():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

def keep_alive():
    t = Thread(target=run, daemon=True)
    t.start()

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = os.getenv("GUILD_ID")

intents = discord.Intents.default()

class MangaBot(discord.Client):
    def __init__(self):
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        self.db: aiosqlite.Connection | None = None

    async def setup_hook(self):
        # Slash-Commands schnell verfügbar machen (Guild-Scoped)
        if GUILD_ID:
            guild = discord.Object(id=int(GUILD_ID))
            await self.tree.sync(guild=guild)
        else:
            # Global sync (kann Minuten dauern)
            await self.tree.sync()

client = MangaBot()

# ------------------------ DB-Setup ------------------------
@client.event
async def on_ready():
    client.db = await aiosqlite.connect("manga.db")
    await client.db.execute("""
        CREATE TABLE IF NOT EXISTS wishlist (
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            norm_title TEXT NOT NULL,
            UNIQUE(user_id, norm_title)
        )
    """)
    await client.db.execute("""
        CREATE TABLE IF NOT EXISTS tradelist (
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            norm_title TEXT NOT NULL,
            UNIQUE(user_id, norm_title)
        )
    """)
    await client.db.execute("CREATE INDEX IF NOT EXISTS idx_wish_norm ON wishlist(norm_title)")
    await client.db.execute("CREATE INDEX IF NOT EXISTS idx_trade_norm ON tradelist(norm_title)")
    await client.db.commit()
    print(f"✅ Eingeloggt als {client.user} (ready)")

# Hilfsfunktionen
def normalize_title(s: str) -> str:
    # Einfache Normalisierung: trimmen, mehrfaches Leerzeichen reduzieren, lower
    return " ".join(s.strip().split()).lower()

async def add_entry(table: str, user_id: int, title: str):
    norm = normalize_title(title)
    await client.db.execute(
        f"INSERT OR IGNORE INTO {table} (user_id, title, norm_title) VALUES (?, ?, ?)",
        (user_id, title, norm),
    )
    await client.db.commit()

async def remove_entry(table: str, user_id: int, title: str) -> int:
    norm = normalize_title(title)
    cur = await client.db.execute(
        f"DELETE FROM {table} WHERE user_id=? AND norm_title=?",
        (user_id, norm),
    )
    await client.db.commit()
    return cur.rowcount

async def list_entries(table: str, user_id: int) -> list[str]:
    cur = await client.db.execute(
        f"SELECT title FROM {table} WHERE user_id=? ORDER BY title COLLATE NOCASE",
        (user_id,),
    )
    rows = await cur.fetchall()
    return [r[0] for r in rows]

# ------------------------ Slash Groups ------------------------
wishlist_group = app_commands.Group(name="wishlist", description="Verwalte deine Wunschliste.")
tradelist_group = app_commands.Group(name="tradelist", description="Verwalte deine Tauschliste.")

# --- Wishlist ---
@wishlist_group.command(name="add", description="Füge einen Manga zu deiner Wishlist hinzu.")
@app_commands.describe(titel="z. B. 'Innocent 7'")
async def wishlist_add(interaction: discord.Interaction, titel: str):
    await add_entry("wishlist", interaction.user.id, titel)
    await interaction.response.send_message(f"📝 `{titel}` wurde zu deiner **Wishlist** hinzugefügt.", ephemeral=True)

@wishlist_group.command(name="remove", description="Entferne einen Manga aus deiner Wishlist.")
@app_commands.describe(titel="Genau der gespeicherte Titel")
async def wishlist_remove(interaction: discord.Interaction, titel: str):
    deleted = await remove_entry("wishlist", interaction.user.id, titel)
    if deleted:
        msg = f"🗑️ `{titel}` wurde aus deiner **Wishlist** entfernt."
    else:
        msg = f"ℹ️ `{titel}` war nicht in deiner **Wishlist**."
    await interaction.response.send_message(msg, ephemeral=True)

@wishlist_group.command(name="list", description="Zeigt deine Wishlist.")
async def wishlist_list(interaction: discord.Interaction):
    items = await list_entries("wishlist", interaction.user.id)
    if not items:
        await interaction.response.send_message("📭 Deine **Wishlist** ist leer.", ephemeral=True)
        return
    content = "\n".join(f"• {t}" for t in items[:50])
    more = f"\n… und {len(items)-50} weitere." if len(items) > 50 else ""
    await interaction.response.send_message(f"💖 **Deine Wishlist:**\n{content}{more}", ephemeral=True)

# --- Tradelist ---
@tradelist_group.command(name="add", description="Füge einen Manga zu deiner Tradelist hinzu.")
@app_commands.describe(titel="z. B. 'Innocent 7'")
async def tradelist_add(interaction: discord.Interaction, titel: str):
    await add_entry("tradelist", interaction.user.id, titel)
    await interaction.response.send_message(f"📦 `{titel}` wurde zu deiner **Tradelist** hinzugefügt.", ephemeral=True)

@tradelist_group.command(name="remove", description="Entferne einen Manga aus deiner Tradelist.")
@app_commands.describe(titel="Genau der gespeicherte Titel")
async def tradelist_remove(interaction: discord.Interaction, titel: str):
    deleted = await remove_entry("tradelist", interaction.user.id, titel)
    if deleted:
        msg = f"🗑️ `{titel}` wurde aus deiner **Tradelist** entfernt."
    else:
        msg = f"ℹ️ `{titel}` war nicht in deiner **Tradelist**."
    await interaction.response.send_message(msg, ephemeral=True)

@tradelist_group.command(name="list", description="Zeigt deine Tradelist.")
async def tradelist_list(interaction: discord.Interaction):
    items = await list_entries("tradelist", interaction.user.id)
    if not items:
        await interaction.response.send_message("📭 Deine **Tradelist** ist leer.", ephemeral=True)
        return
    content = "\n".join(f"• {t}" for t in items[:50])
    more = f"\n… und {len(items)-50} weitere." if len(items) > 50 else ""
    await interaction.response.send_message(f"🔁 **Deine Tradelist:**\n{content}{more}", ephemeral=True)

# ------------------------ Matches ------------------------
@client.tree.command(name="matches", description="Finde Tauschpartner für deine Wishlist/Tradelist.")
async def matches(interaction: discord.Interaction):
    user_id = interaction.user.id

    # Meine normalisierten Titel
    cur = await client.db.execute("SELECT norm_title, title FROM wishlist WHERE user_id=?", (user_id,))
    my_wishes = await cur.fetchall()
    cur = await client.db.execute("SELECT norm_title, title FROM tradelist WHERE user_id=?", (user_id,))
    my_trades = await cur.fetchall()

    if not my_wishes and not my_trades:
        await interaction.response.send_message("ℹ️ Du hast noch keine Wishlist/Tradelist gepflegt.", ephemeral=True)
        return

    # Wer bietet, was ich suche?
    wish_norms = tuple([w[0] for w in my_wishes])
    wish_section = []
    if wish_norms:
        q_marks = ",".join("?" * len(wish_norms))
        query = f"""
            SELECT t.user_id, t.title, t.norm_title
            FROM tradelist t
            WHERE t.user_id != ? AND t.norm_title IN ({q_marks})
            ORDER BY t.title COLLATE NOCASE
        """
        cur = await client.db.execute(query, (user_id, *wish_norms))
        rows = await cur.fetchall()
        # Gruppieren nach Titel
        by_title = {}
        for uid, title, norm in rows:
            by_title.setdefault(title, set()).add(uid)
        for title, uids in by_title.items():
            mentions = ", ".join(f"<@{u}>" for u in sorted(uids))
            wish_section.append(f"✅ **{title}** wird angeboten von: {mentions}")

    # Wer sucht, was ich biete?
    trade_norms = tuple([t[0] for t in my_trades])
    trade_section = []
    if trade_norms:
        q_marks = ",".join("?" * len(trade_norms))
        query = f"""
            SELECT w.user_id, w.title, w.norm_title
            FROM wishlist w
            WHERE w.user_id != ? AND w.norm_title IN ({q_marks})
            ORDER BY w.title COLLATE NOCASE
        """
        cur = await client.db.execute(query, (user_id, *trade_norms))
        rows = await cur.fetchall()
        by_title = {}
        for uid, title, norm in rows:
            by_title.setdefault(title, set()).add(uid)
        for title, uids in by_title.items():
            mentions = ", ".join(f"<@{u}>" for u in sorted(uids))
            trade_section.append(f"🔎 **{title}** wird gesucht von: {mentions}")

    if not wish_section and not trade_section:
        await interaction.response.send_message("😕 Keine Matches gefunden – vielleicht später nochmal versuchen.", ephemeral=True)
        return

    # Hübsch ausgeben
    parts = []
    if wish_section:
        parts.append("### 🎯 Treffer für deine **Wishlist**\n" + "\n".join(wish_section))
    if trade_section:
        parts.append("### 🤝 Nutzer, die deine **Tradelist** suchen\n" + "\n".join(trade_section))

    text = "\n\n".join(parts)
    await interaction.response.send_message(text, ephemeral=True)

# Gruppen registrieren
if GUILD_ID:
    client.tree.add_command(wishlist_group, guild=discord.Object(id=int(GUILD_ID)))
    client.tree.add_command(tradelist_group, guild=discord.Object(id=int(GUILD_ID)))
else:
    client.tree.add_command(wishlist_group)
    client.tree.add_command(tradelist_group)


async def clear_entries(table: str, user_id: int) -> int:
    cur = await client.db.execute(f"DELETE FROM {table} WHERE user_id=?", (user_id,))
    await client.db.commit()
    return cur.rowcount

async def search_entries(table: str, user_id: int, needle: str) -> list[str]:
    # Sucht per LIKE in Original-Titeln und per Normalisierung
    like = f"%{needle}%"
    norm = f"%{normalize_title(needle)}%"
    cur = await client.db.execute(
        f"""
        SELECT title FROM {table}
        WHERE user_id=?
          AND (title LIKE ? OR norm_title LIKE ?)
        ORDER BY title COLLATE NOCASE
        """,
        (user_id, like, norm),
    )
    rows = await cur.fetchall()
    return [r[0] for r in rows]

async def find_duplicates(user_id: int):
    # Duplikate innerhalb jeder Liste (gleicher norm_title mehrfach)
    cur = await client.db.execute("""
        SELECT title, norm_title, COUNT(*)
        FROM wishlist
        WHERE user_id=?
        GROUP BY norm_title
        HAVING COUNT(*) > 1
        ORDER BY title COLLATE NOCASE
    """, (user_id,))
    dup_wish = await cur.fetchall()

    cur = await client.db.execute("""
        SELECT title, norm_title, COUNT(*)
        FROM tradelist
        WHERE user_id=?
        GROUP BY norm_title
        HAVING COUNT(*) > 1
        ORDER BY title COLLATE NOCASE
    """, (user_id,))
    dup_trade = await cur.fetchall()

    # Konflikte: gleicher norm_title in Wishlist **und** Tradelist
    cur = await client.db.execute("""
        SELECT w.title, t.title, w.norm_title
        FROM wishlist w
        JOIN tradelist t
          ON t.user_id = w.user_id
         AND t.norm_title = w.norm_title
        WHERE w.user_id=?
        ORDER BY w.title COLLATE NOCASE
    """, (user_id,))
    conflicts = await cur.fetchall()

    return dup_wish, dup_trade, conflicts

@wishlist_group.command(name="clear", description="Leert deine komplette Wishlist.")
async def wishlist_clear(interaction: discord.Interaction):
    count = await clear_entries("wishlist", interaction.user.id)
    await interaction.response.send_message(f"🧹 Deine **Wishlist** wurde geleert ({count} Einträge entfernt).", ephemeral=True)

@tradelist_group.command(name="clear", description="Leert deine komplette Tradelist.")
async def tradelist_clear(interaction: discord.Interaction):
    count = await clear_entries("tradelist", interaction.user.id)
    await interaction.response.send_message(f"🧹 Deine **Tradelist** wurde geleert ({count} Einträge entfernt).", ephemeral=True)

@wishlist_group.command(name="search", description="Durchsucht deine Wishlist.")
@app_commands.describe(text="Suchtext, z. B. 'Innocent' oder 'Naruto 1'")
async def wishlist_search(interaction: discord.Interaction, text: str):
    hits = await search_entries("wishlist", interaction.user.id, text)
    if not hits:
        await interaction.response.send_message(f"🔍 Keine Treffer in deiner Wishlist für „{text}“.", ephemeral=True)
        return
    out = "\n".join(f"• {t}" for t in hits[:50])
    more = f"\n… und {len(hits)-50} weitere." if len(hits) > 50 else ""
    await interaction.response.send_message(f"🔍 **Treffer (Wishlist) für „{text}“:**\n{out}{more}", ephemeral=True)

@tradelist_group.command(name="search", description="Durchsucht deine Tradelist.")
@app_commands.describe(text="Suchtext, z. B. 'AOT 3' oder 'Bleach'")
async def tradelist_search(interaction: discord.Interaction, text: str):
    hits = await search_entries("tradelist", interaction.user.id, text)
    if not hits:
        await interaction.response.send_message(f"🔍 Keine Treffer in deiner Tradelist für „{text}“.", ephemeral=True)
        return
    out = "\n".join(f"• {t}" for t in hits[:50])
    more = f"\n… und {len(hits)-50} weitere." if len(hits) > 50 else ""
    await interaction.response.send_message(f"🔍 **Treffer (Tradelist) für „{text}“:**\n{out}{more}", ephemeral=True)

@client.tree.command(name="duplicates", description="Zeigt doppelte Einträge und Wishlist/Tradelist-Konflikte.")
async def duplicates(interaction: discord.Interaction):
    dup_wish, dup_trade, conflicts = await find_duplicates(interaction.user.id)

    parts = []
    if dup_wish:
        lines = "\n".join(f"• {row[0]}  (x{row[2]})" for row in dup_wish[:30])
        more = f"\n… und {len(dup_wish)-30} weitere." if len(dup_wish) > 30 else ""
        parts.append(f"📚 **Duplikate in deiner Wishlist:**\n{lines}{more}")
    if dup_trade:
        lines = "\n".join(f"• {row[0]}  (x{row[2]})" for row in dup_trade[:30])
        more = f"\n… und {len(dup_trade)-30} weitere." if len(dup_trade) > 30 else ""
        parts.append(f"📦 **Duplikate in deiner Tradelist:**\n{lines}{more}")
    if conflicts:
        # row = (wish_title, trade_title, norm)
        lines = "\n".join(f"• Wishlist: **{w}**  |  Tradelist: **{t}**" for (w, t, _) in conflicts[:30])
        more = f"\n… und {len(conflicts)-30} weitere." if len(conflicts) > 30 else ""
        parts.append(f"⚠️ **Konflikte (gleiches Werk in beiden Listen):**\n{lines}{more}")

    if not parts:
        await interaction.response.send_message("✅ Keine Duplikate oder Konflikte gefunden.", ephemeral=True)
        return

    await interaction.response.send_message("\n\n".join(parts), ephemeral=True)






@client.tree.command(name="sync", description="Slash-Commands neu synchronisieren.")
async def sync_cmd(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    if GUILD_ID:
        guild = discord.Object(id=int(GUILD_ID))
        synced = await client.tree.sync(guild=guild)
    else:
        synced = await client.tree.sync()
    await interaction.followup.send(f"🔄 {len(synced)} Commands synchronisiert.", ephemeral=True)

if __name__ == "__main__":
    keep_alive()
    client.run(TOKEN)

