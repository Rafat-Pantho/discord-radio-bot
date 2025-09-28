import discord
from discord.ext import commands
import asyncio
import os
import yt_dlp
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
from dotenv import load_dotenv
import re
from collections import deque
import random

# Load environment variables
load_dotenv()

# Bot configuration
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
SPOTIFY_CLIENT_ID = os.getenv('SPOTIFY_CLIENT_ID')
SPOTIFY_CLIENT_SECRET = os.getenv('SPOTIFY_CLIENT_SECRET')

# Optional yt-dlp cookie support (helps with age/region restricted videos)
YTDLP_COOKIE_FILE = os.getenv('YTDLP_COOKIE_FILE')  # Path to cookies.txt (Netscape format)
YTDLP_COOKIES_FROM_BROWSER = os.getenv('YTDLP_COOKIES_FROM_BROWSER', '').lower() in ('1', 'true', 'yes', 'y')
YTDLP_BROWSER = os.getenv('YTDLP_BROWSER', 'chrome')  # chrome|edge|firefox (used only if above is true)

# A realistic User-Agent to reduce HTTP 403/format issues
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/127.0.0.0 Safari/537.36"
)

# Initialize Spotify client
spotify = spotipy.Spotify(client_credentials_manager=SpotifyClientCredentials(
    client_id=SPOTIFY_CLIENT_ID,
    client_secret=SPOTIFY_CLIENT_SECRET
))

# yt-dlp configuration (robust defaults + retries + headers)
ytdl_format_options = {
    # Let yt-dlp choose the best available audio; avoid over-constraining formats
    'format': 'bestaudio/best',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'ytsearch',
    'source_address': '0.0.0.0',
    'extract_flat': False,
    'geo_bypass': True,
    'extractor_retries': 3,
    'concurrent_fragment_downloads': 1,
    'http_headers': {
        'User-Agent': USER_AGENT,
        'Accept': '*/*',
        'Accept-Language': 'en-US,en;q=0.9'
    },
    # Use android/web player clients to avoid throttling on some videos
    'extractor_args': {
        'youtube': {
            'player_client': ['android', 'web']
        }
    }
}

# Apply optional cookies configuration
if YTDLP_COOKIE_FILE:
    ytdl_format_options['cookiefile'] = YTDLP_COOKIE_FILE
elif YTDLP_COOKIES_FROM_BROWSER:
    # Best effort: use cookies from installed browser
    ytdl_format_options['cookiesfrombrowser'] = (YTDLP_BROWSER, )

# FFmpeg configuration with explicit headers and user-agent
ffmpeg_before_headers = (
    f'-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 '
    f'-user_agent "{USER_AGENT}" '
    f'-headers "User-Agent: {USER_AGENT}\r\nAccept-Language: en-US,en;q=0.9" '
    f'-nostdin'
)

ffmpeg_options = {
    'before_options': ffmpeg_before_headers,
    'options': '-vn'
}

ytdl = yt_dlp.YoutubeDL(ytdl_format_options)

class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get('title')
        self.url = data.get('url')
        self.duration = data.get('duration')
        self.thumbnail = data.get('thumbnail')
        self.uploader = data.get('uploader')

    @classmethod
    async def from_url(cls, url, *, loop=None, stream=False):
        loop = loop or asyncio.get_event_loop()
        
        try:
            # First attempt with current settings
            data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=not stream))
        except Exception as e:
            print(f"First extraction attempt failed: {e}")
            # Fallback with more permissive settings
            fallback_opts = {
                'format': 'bestaudio/best/18/worst',
                'quiet': True,
                'no_warnings': True,
                'default_search': 'ytsearch',
                'source_address': '0.0.0.0',
                'http_headers': ytdl_format_options.get('http_headers'),
                'extractor_args': ytdl_format_options.get('extractor_args'),
                'geo_bypass': True,
                'extractor_retries': 2
            }
            # propagate cookies settings if any
            if 'cookiefile' in ytdl_format_options:
                fallback_opts['cookiefile'] = ytdl_format_options['cookiefile']
            if 'cookiesfrombrowser' in ytdl_format_options:
                fallback_opts['cookiesfrombrowser'] = ytdl_format_options['cookiesfrombrowser']
            fallback_ytdl = yt_dlp.YoutubeDL(fallback_opts)
            try:
                data = await loop.run_in_executor(None, lambda: fallback_ytdl.extract_info(url, download=not stream))
            except Exception as e2:
                print(f"Fallback extraction also failed: {e2}")
                raise e2
        
        if 'entries' in data:
            data = data['entries'][0]
        
        filename = data['url'] if stream else ytdl.prepare_filename(data)
        return cls(discord.FFmpegPCMAudio(filename, **ffmpeg_options), data=data)

class MusicBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix='!', intents=intents, help_command=None)
        
        # Music queue and state
        self.queues = {}
        self.current_song = {}
        self.loop_mode = {}  # 0: no loop, 1: loop song, 2: loop queue
        # Track control panel messages per guild for later cleanup
        self.control_messages = {}
        # Track scheduled cleanup tasks per guild
        self._cleanup_tasks = {}
        
    async def on_ready(self):
        print(f'🎵 {self.user} has connected to Discord!')
        print(f'Bot is ready in {len(self.guilds)} guilds')
        
        # Set bot status
        activity = discord.Activity(type=discord.ActivityType.listening, name="!commands for help")
        await self.change_presence(activity=activity)

    def get_queue(self, guild_id):
        if guild_id not in self.queues:
            self.queues[guild_id] = deque()
        return self.queues[guild_id]

    def register_control_message(self, guild_id: int, message: discord.Message):
        arr = self.control_messages.get(guild_id)
        if arr is None:
            arr = []
            self.control_messages[guild_id] = arr
        arr.append(message)

    async def remove_controls(self, guild_id: int):
        arr = self.control_messages.get(guild_id) or []
        self.control_messages[guild_id] = []
        for msg in arr:
            try:
                await msg.edit(view=None)
            except Exception:
                pass

    def cancel_cleanup(self, guild_id: int):
        task = self._cleanup_tasks.get(guild_id)
        if task and not task.done():
            task.cancel()
        self._cleanup_tasks[guild_id] = None

    def schedule_cleanup(self, guild_id: int, delay_seconds: int):
        # Cancel any existing
        self.cancel_cleanup(guild_id)
        async def _job():
            try:
                await asyncio.sleep(delay_seconds)
                await self.remove_controls(guild_id)
            except asyncio.CancelledError:
                return
        self._cleanup_tasks[guild_id] = self.loop.create_task(_job())

bot = MusicBot()

# ===== Button-based Controls (UI View) =====
class MusicControlView(discord.ui.View):
    def __init__(self, bot: MusicBot):
        super().__init__(timeout=300)
        self.bot = bot

    def _same_voice(self, interaction: discord.Interaction) -> tuple[bool, str | None]:
        user_voice = getattr(interaction.user, 'voice', None)
        vc = interaction.guild.voice_client if interaction.guild else None
        if not interaction.guild or not vc:
            return False, "I'm not connected to a voice channel."
        if not user_voice or not user_voice.channel:
            return False, "You need to be in a voice channel to use the controls."
        if user_voice.channel != vc.channel:
            return False, "You must be in the same voice channel as me."
        return True, None

    async def _send_ephemeral(self, interaction: discord.Interaction, content: str):
        if interaction.response.is_done():
            await interaction.followup.send(content, ephemeral=True)
        else:
            await interaction.response.send_message(content, ephemeral=True)

    @discord.ui.button(label="Play/Pause", style=discord.ButtonStyle.primary, emoji="⏯️")
    async def play_pause(self, interaction: discord.Interaction, button: discord.ui.Button):
        ok, msg = self._same_voice(interaction)
        if not ok:
            return await self._send_ephemeral(interaction, f"❌ {msg}")
        vc = interaction.guild.voice_client
        if vc.is_paused():
            vc.resume()
            await self._send_ephemeral(interaction, "▶️ Resumed")
        elif vc.is_playing():
            vc.pause()
            await self._send_ephemeral(interaction, "⏸️ Paused")
        else:
            await self._send_ephemeral(interaction, "ℹ️ Nothing to play or already stopped.")

    @discord.ui.button(label="Skip", style=discord.ButtonStyle.secondary, emoji="⏭️")
    async def skip_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        ok, msg = self._same_voice(interaction)
        if not ok:
            return await self._send_ephemeral(interaction, f"❌ {msg}")
        vc = interaction.guild.voice_client
        if vc and (vc.is_playing() or vc.is_paused()):
            vc.stop()
            await self._send_ephemeral(interaction, "⏭️ Skipped")
        else:
            await self._send_ephemeral(interaction, "ℹ️ Nothing to skip.")

    @discord.ui.button(label="Stop", style=discord.ButtonStyle.danger, emoji="⏹️")
    async def stop_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        ok, msg = self._same_voice(interaction)
        if not ok:
            return await self._send_ephemeral(interaction, f"❌ {msg}")
        vc = interaction.guild.voice_client
        if vc:
            vc.stop()
            self.bot.get_queue(interaction.guild.id).clear()
            await self._send_ephemeral(interaction, "⏹️ Stopped and cleared queue")
        else:
            await self._send_ephemeral(interaction, "ℹ️ I'm not connected.")

    @discord.ui.button(label="Loop", style=discord.ButtonStyle.secondary, emoji="🔁")
    async def loop_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        ok, msg = self._same_voice(interaction)
        if not ok:
            return await self._send_ephemeral(interaction, f"❌ {msg}")
        gid = interaction.guild.id
        mode = self.bot.loop_mode.get(gid, 0)
        mode = (mode + 1) % 3
        self.bot.loop_mode[gid] = mode
        modes = {0: "Off", 1: "Song", 2: "Queue"}
        await self._send_ephemeral(interaction, f"🔁 Loop mode: {modes[mode]}")

    @discord.ui.button(label="Shuffle", style=discord.ButtonStyle.secondary, emoji="🔀")
    async def shuffle_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        ok, msg = self._same_voice(interaction)
        if not ok:
            return await self._send_ephemeral(interaction, f"❌ {msg}")
        q = self.bot.get_queue(interaction.guild.id)
        if len(q) < 2:
            return await self._send_ephemeral(interaction, "ℹ️ Need at least 2 songs to shuffle.")
        import random as _rand
        _list = list(q)
        _rand.shuffle(_list)
        q.clear()
        q.extend(_list)
        await self._send_ephemeral(interaction, "🔀 Queue shuffled")

    @discord.ui.button(label="Vol -", style=discord.ButtonStyle.secondary, emoji="🔉")
    async def vol_down(self, interaction: discord.Interaction, button: discord.ui.Button):
        ok, msg = self._same_voice(interaction)
        if not ok:
            return await self._send_ephemeral(interaction, f"❌ {msg}")
        vc = interaction.guild.voice_client
        if not vc or not vc.source:
            return await self._send_ephemeral(interaction, "ℹ️ Nothing is playing.")
        vol = getattr(vc.source, 'volume', 0.5)
        new = max(0.0, vol - 0.1)
        vc.source.volume = new
        await self._send_ephemeral(interaction, f"🔉 Volume: {int(new*100)}%")

    @discord.ui.button(label="Vol +", style=discord.ButtonStyle.secondary, emoji="🔊")
    async def vol_up(self, interaction: discord.Interaction, button: discord.ui.Button):
        ok, msg = self._same_voice(interaction)
        if not ok:
            return await self._send_ephemeral(interaction, f"❌ {msg}")
        vc = interaction.guild.voice_client
        if not vc or not vc.source:
            return await self._send_ephemeral(interaction, "ℹ️ Nothing is playing.")
        vol = getattr(vc.source, 'volume', 0.5)
        new = min(1.0, vol + 0.1)
        vc.source.volume = new
        await self._send_ephemeral(interaction, f"🔊 Volume: {int(new*100)}%")

    @discord.ui.button(label="Queue", style=discord.ButtonStyle.secondary, emoji="📜")
    async def queue_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        q = self.bot.get_queue(interaction.guild.id)
        if not q:
            return await self._send_ephemeral(interaction, "📝 Queue is empty.")
        out = []
        for i, s in enumerate(list(q)[:10], 1):
            out.append(f"{i}. {s['title']}")
        text = "\n".join(out)
        await self._send_ephemeral(interaction, f"📝 Up Next:\n{text}")

    @discord.ui.button(label="Now", style=discord.ButtonStyle.secondary, emoji="🎵")
    async def now_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        current = self.bot.current_song.get(interaction.guild.id)
        vc = interaction.guild.voice_client
        if not current or not vc or not (vc.is_playing() or vc.is_paused()):
            return await self._send_ephemeral(interaction, "ℹ️ Nothing is currently playing.")
        embed = discord.Embed(title="🎵 Now Playing", description=f"**{current['title']}**", color=0x00ff00)
        if current.get('duration'):
            embed.add_field(name="Duration", value=f"{current['duration'] // 60}:{current['duration'] % 60:02d}", inline=True)
        if current.get('uploader'):
            embed.add_field(name="Uploader", value=current['uploader'], inline=True)
        if current.get('thumbnail'):
            embed.set_thumbnail(url=current['thumbnail'])
        if interaction.response.is_done():
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="Leave", style=discord.ButtonStyle.danger, emoji="🚪")
    async def leave_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        ok, msg = self._same_voice(interaction)
        if not ok:
            return await self._send_ephemeral(interaction, f"❌ {msg}")
        vc = interaction.guild.voice_client
        if vc:
            await vc.disconnect()
            await self._send_ephemeral(interaction, "👋 Disconnected")
        else:
            await self._send_ephemeral(interaction, "ℹ️ I'm not connected.")

@bot.command(name='join', aliases=['connect'])
async def join(ctx):
    """Join the voice channel"""
    if not ctx.author.voice:
        embed = discord.Embed(title="❌ Error", description="You need to be in a voice channel!", color=0xff0000)
        await ctx.send(embed=embed)
        return
    
    channel = ctx.author.voice.channel
    
    if ctx.voice_client:
        if ctx.voice_client.channel == channel:
            embed = discord.Embed(title="✅ Already Connected", description=f"Already connected to {channel.name}", color=0x00ff00)
            await ctx.send(embed=embed)
            return
        await ctx.voice_client.move_to(channel)
    else:
        await channel.connect()
    
    embed = discord.Embed(title="🎵 Joined Voice Channel", description=f"Connected to {channel.name}", color=0x00ff00)
    await ctx.send(embed=embed)

@bot.command(name='leave', aliases=['disconnect'])
async def leave(ctx):
    """Leave the voice channel"""
    if not ctx.voice_client:
        embed = discord.Embed(title="❌ Error", description="I'm not connected to any voice channel!", color=0xff0000)
        await ctx.send(embed=embed)
        return
    
    # Clear queue and stop current song
    if ctx.guild.id in bot.queues:
        bot.queues[ctx.guild.id].clear()
    
    await ctx.voice_client.disconnect()
    # Remove controls right away and cancel any pending cleanup
    await bot.remove_controls(ctx.guild.id)
    bot.cancel_cleanup(ctx.guild.id)
    
    embed = discord.Embed(title="👋 Disconnected", description="Left the voice channel", color=0xff9900)
    await ctx.send(embed=embed)

def extract_spotify_info(url):
    """Extract Spotify track/playlist info"""
    try:
        if 'track/' in url:
            track_id = url.split('track/')[-1].split('?')[0]
            track = spotify.track(track_id)
            return {
                'type': 'track',
                'name': track['name'],
                'artist': ', '.join([artist['name'] for artist in track['artists']]),
                'search_query': f"{track['name']} {track['artists'][0]['name']}"
            }
        elif 'playlist/' in url:
            playlist_id = url.split('playlist/')[-1].split('?')[0]
            playlist = spotify.playlist(playlist_id)
            tracks = []
            for item in playlist['tracks']['items']:
                if item['track']:
                    track = item['track']
                    tracks.append({
                        'name': track['name'],
                        'artist': ', '.join([artist['name'] for artist in track['artists']]),
                        'search_query': f"{track['name']} {track['artists'][0]['name']}"
                    })
            return {
                'type': 'playlist',
                'name': playlist['name'],
                'tracks': tracks
            }
    except Exception as e:
        print(f"Spotify error: {e}")
        return None

async def search_youtube(query):
    """Search YouTube for a query"""
    try:
        loop = asyncio.get_event_loop()
        
        # Try with main ytdl instance
        try:
            data = await loop.run_in_executor(None, lambda: ytdl.extract_info(f"ytsearch:{query}", download=False))
        except Exception as e:
            print(f"Main search failed: {e}")
            # Fallback search with simpler options
            fallback_ytdl = yt_dlp.YoutubeDL({
                'format': 'bestaudio/best/18/worst',
                'quiet': True,
                'no_warnings': True,
                'default_search': 'ytsearch',
                'http_headers': ytdl_format_options.get('http_headers'),
                'extractor_args': ytdl_format_options.get('extractor_args'),
                'geo_bypass': True
            })
            data = await loop.run_in_executor(None, lambda: fallback_ytdl.extract_info(f"ytsearch:{query}", download=False))
        
        if 'entries' in data and data['entries']:
            return data['entries'][0]['webpage_url']
    except Exception as e:
        print(f"YouTube search error: {e}")
    return None

async def add_to_queue(ctx, query: str, custom_title: str | None = None, silent: bool = False):
    """Resolve a query/URL to a song and add it to the guild queue. Starts playback if idle."""
    try:
        loop = asyncio.get_event_loop()
        # Primary extraction
        try:
            data = await loop.run_in_executor(None, lambda: ytdl.extract_info(query, download=False))
        except Exception as e:
            print(f"Primary extraction failed: {e}")
            # Fallback extraction
            fallback_opts = {
                'format': 'bestaudio/best/18/worst',
                'quiet': True,
                'no_warnings': True,
                'default_search': 'ytsearch',
                'extract_flat': False,
                'ignoreerrors': True,
                'http_headers': ytdl_format_options.get('http_headers'),
                'extractor_args': ytdl_format_options.get('extractor_args'),
                'geo_bypass': True
            }
            if 'cookiefile' in ytdl_format_options:
                fallback_opts['cookiefile'] = ytdl_format_options['cookiefile']
            if 'cookiesfrombrowser' in ytdl_format_options:
                fallback_opts['cookiesfrombrowser'] = ytdl_format_options['cookiesfrombrowser']
            fallback_ytdl = yt_dlp.YoutubeDL(fallback_opts)
            try:
                data = await loop.run_in_executor(None, lambda: fallback_ytdl.extract_info(query, download=False))
            except Exception as e2:
                print(f"Fallback extraction failed: {e2}")
                raise Exception("Could not extract video information. The video might be unavailable or restricted.")

        if 'entries' in data:
            data = data['entries'][0]

        if not data or not data.get('webpage_url'):
            raise Exception("No valid video data found")

        song_info = {
            'url': data['webpage_url'],
            'title': custom_title or data.get('title', 'Unknown'),
            'duration': data.get('duration', 0),
            'thumbnail': data.get('thumbnail'),
            'uploader': data.get('uploader', 'Unknown'),
            'requester': ctx.author
        }

        queue = bot.get_queue(ctx.guild.id)
        queue.append(song_info)

        # If something is already playing or there are items ahead, just acknowledge
        if not silent:
            vc = ctx.voice_client
            position = len(queue)
            if (vc and (vc.is_playing() or vc.is_paused())) or position > 1:
                embed = discord.Embed(
                    title="📝 Added to Queue",
                    description=f"**{song_info['title']}**\nPosition in queue: {position}",
                    color=0x00ff00,
                )
                if song_info.get('thumbnail'):
                    embed.set_thumbnail(url=song_info['thumbnail'])
                embed.set_footer(text=f"Requested by {ctx.author.display_name}")
                await ctx.send(embed=embed)

        # Start playback if idle
        vc = ctx.voice_client
        if vc and not (vc.is_playing() or vc.is_paused()):
            await play_next(ctx)

    except Exception as e:
        print(f"Error adding to queue: {e}")
        embed = discord.Embed(
            title="❌ Error",
            description=f"Could not add song to queue: {str(e)[:200]}...",
            color=0xff0000,
        )
        await ctx.send(embed=embed)

@bot.command(name='play', aliases=['p'])
async def play(ctx, *, query):
    """Play music from YouTube or Spotify"""
    if not ctx.author.voice:
        embed = discord.Embed(title="❌ Error", description="You need to be in a voice channel!", color=0xff0000)
        await ctx.send(embed=embed)
        return
    
    if not ctx.voice_client:
        await join(ctx)

    # Check if it's a Spotify URL
    if 'spotify.com' in query:
        spotify_info = extract_spotify_info(query)
        if not spotify_info:
            embed = discord.Embed(title="❌ Error", description="Invalid Spotify URL!", color=0xff0000)
            await ctx.send(embed=embed)
            return
        
        if spotify_info['type'] == 'track':
            # Single track
            youtube_url = await search_youtube(spotify_info['search_query'])
            if youtube_url:
                await add_to_queue(ctx, youtube_url, f"🎵 {spotify_info['name']} - {spotify_info['artist']}")
            else:
                embed = discord.Embed(title="❌ Error", description="Couldn't find this track on YouTube!", color=0xff0000)
                await ctx.send(embed=embed)
        
        elif spotify_info['type'] == 'playlist':
            # Playlist
            embed = discord.Embed(title="🎵 Adding Spotify Playlist", 
                                description=f"Adding {len(spotify_info['tracks'])} tracks from **{spotify_info['name']}**...", 
                                color=0x1db954)
            await ctx.send(embed=embed)
            
            added = 0
            for track in spotify_info['tracks'][:50]:  # Limit to 50 tracks to avoid spam
                youtube_url = await search_youtube(track['search_query'])
                if youtube_url:
                    await add_to_queue(ctx, youtube_url, f"🎵 {track['name']} - {track['artist']}", silent=True)
                    added += 1
            
            embed = discord.Embed(title="✅ Playlist Added", 
                                description=f"Added {added} tracks from **{spotify_info['name']}**", 
                                color=0x00ff00)
            await ctx.send(embed=embed)
    
    else:
        # YouTube URL or search query
        await add_to_queue(ctx, query)

async def play_next(ctx):
    """Play the next song in queue"""
    queue = bot.get_queue(ctx.guild.id)
    vc = ctx.voice_client

    if not vc:
        return

    if not queue:
        # Nothing to play; schedule cleanup if we're idle
        if not vc.is_playing() and not vc.is_paused():
            bot.schedule_cleanup(ctx.guild.id, random.randint(60, 120))
        return

    song_info = queue.popleft()
    bot.current_song[ctx.guild.id] = song_info

    try:
        source = await YTDLSource.from_url(song_info['url'], loop=bot.loop, stream=True)

        # Cancel any pending cleanup since music is resuming
        bot.cancel_cleanup(ctx.guild.id)

        # Remove any previous control panels so only the new message has buttons
        await bot.remove_controls(ctx.guild.id)

        def after_playing(error):
            if error:
                print(f'Player error: {error}')

            # Handle loop mode
            loop_mode = bot.loop_mode.get(ctx.guild.id, 0)
            if loop_mode == 1:  # Loop current song
                queue.appendleft(song_info)
            elif loop_mode == 2:  # Loop queue
                queue.append(song_info)

            # Play next song (or schedule cleanup if ended)
            coro = play_next(ctx)
            fut = asyncio.run_coroutine_threadsafe(coro, bot.loop)
            try:
                fut.result()
            except Exception as e:
                print(f'Error in after_playing: {e}')

        vc.play(source, after=after_playing)

        # Send now playing message with control panel
        embed = discord.Embed(
            title="🎵 Now Playing",
            description=f"**{song_info['title']}**",
            color=0x00ff00,
        )
        if song_info.get('duration'):
            embed.add_field(
                name="Duration",
                value=f"{song_info['duration'] // 60}:{song_info['duration'] % 60:02d}",
                inline=True,
            )
        if song_info.get('uploader'):
            embed.add_field(name="Uploader", value=song_info['uploader'], inline=True)
        if song_info.get('thumbnail'):
            embed.set_thumbnail(url=song_info['thumbnail'])
        embed.set_footer(text=f"Requested by {song_info['requester'].display_name}")

        view = MusicControlView(bot)
        msg = await ctx.send(embed=embed, view=view)
        bot.register_control_message(ctx.guild.id, msg)

    except Exception as e:
        print(f"Error playing song: {e}")
        await play_next(ctx)  # Try next song

@bot.command(name='skip', aliases=['s'])
async def skip(ctx):
    """Skip the current song"""
    if not ctx.voice_client or not ctx.voice_client.is_playing():
        embed = discord.Embed(title="❌ Error", description="Nothing is currently playing!", color=0xff0000)
        await ctx.send(embed=embed)
        return
    
    ctx.voice_client.stop()
    embed = discord.Embed(title="⏭️ Skipped", description="Skipped the current song", color=0xff9900)
    await ctx.send(embed=embed)

@bot.command(name='queue', aliases=['q'])
async def show_queue(ctx):
    """Show the current queue"""
    queue = bot.get_queue(ctx.guild.id)
    
    if not queue:
        embed = discord.Embed(title="📝 Queue", description="The queue is empty!", color=0xff9900)
        await ctx.send(embed=embed)
        return
    
    # Show current song
    current = bot.current_song.get(ctx.guild.id)
    embed = discord.Embed(title="📝 Music Queue", color=0x00ff00)
    
    if current:
        embed.add_field(name="🎵 Now Playing", value=f"**{current['title']}**", inline=False)
    
    # Show next 10 songs in queue
    queue_text = ""
    for i, song in enumerate(list(queue)[:10], 1):
        queue_text += f"{i}. **{song['title']}**\n"
    
    if queue_text:
        embed.add_field(name="⏭️ Up Next", value=queue_text, inline=False)
    
    if len(queue) > 10:
        embed.add_field(name="", value=f"... and {len(queue) - 10} more songs", inline=False)
    
    await ctx.send(embed=embed)

@bot.command(name='clear')
async def clear_queue(ctx):
    """Clear the queue"""
    queue = bot.get_queue(ctx.guild.id)
    queue.clear()
    
    embed = discord.Embed(title="🗑️ Queue Cleared", description="Cleared all songs from the queue", color=0xff9900)
    await ctx.send(embed=embed)

@bot.command(name='pause')
async def pause(ctx):
    """Pause the current song"""
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.pause()
        embed = discord.Embed(title="⏸️ Paused", description="Paused the current song", color=0xff9900)
        await ctx.send(embed=embed)
    else:
        embed = discord.Embed(title="❌ Error", description="Nothing is currently playing!", color=0xff0000)
        await ctx.send(embed=embed)

@bot.command(name='resume')
async def resume(ctx):
    """Resume the current song"""
    if ctx.voice_client and ctx.voice_client.is_paused():
        ctx.voice_client.resume()
        embed = discord.Embed(title="▶️ Resumed", description="Resumed the current song", color=0x00ff00)
        await ctx.send(embed=embed)
    else:
        embed = discord.Embed(title="❌ Error", description="Nothing is currently paused!", color=0xff0000)
        await ctx.send(embed=embed)

@bot.command(name='stop')
async def stop(ctx):
    """Stop the current song and clear queue"""
    if ctx.voice_client:
        ctx.voice_client.stop()
        bot.get_queue(ctx.guild.id).clear()
        
        embed = discord.Embed(title="⏹️ Stopped", description="Stopped playing and cleared the queue", color=0xff9900)
        await ctx.send(embed=embed)
    else:
        embed = discord.Embed(title="❌ Error", description="Nothing is currently playing!", color=0xff0000)
        await ctx.send(embed=embed)

@bot.command(name='volume', aliases=['vol'])
async def volume(ctx, volume: int = None):
    """Change the volume (0-100)"""
    if not ctx.voice_client or not ctx.voice_client.source:
        embed = discord.Embed(title="❌ Error", description="Nothing is currently playing!", color=0xff0000)
        await ctx.send(embed=embed)
        return
    
    if volume is None:
        current_volume = int(ctx.voice_client.source.volume * 100)
        embed = discord.Embed(title="🔊 Current Volume", description=f"Volume is set to {current_volume}%", color=0x00ff00)
        await ctx.send(embed=embed)
        return
    
    if volume < 0 or volume > 100:
        embed = discord.Embed(title="❌ Error", description="Volume must be between 0 and 100!", color=0xff0000)
        await ctx.send(embed=embed)
        return
    
    ctx.voice_client.source.volume = volume / 100
    embed = discord.Embed(title="🔊 Volume Changed", description=f"Set volume to {volume}%", color=0x00ff00)
    await ctx.send(embed=embed)

@bot.command(name='shuffle')
async def shuffle(ctx):
    """Shuffle the queue"""
    queue = bot.get_queue(ctx.guild.id)
    
    if len(queue) < 2:
        embed = discord.Embed(title="❌ Error", description="Need at least 2 songs in queue to shuffle!", color=0xff0000)
        await ctx.send(embed=embed)
        return
    
    queue_list = list(queue)
    random.shuffle(queue_list)
    queue.clear()
    queue.extend(queue_list)
    
    embed = discord.Embed(title="🔀 Queue Shuffled", description="Shuffled the music queue", color=0x00ff00)
    await ctx.send(embed=embed)

@bot.command(name='panel')
async def control_panel(ctx):
    """Show the music control buttons panel."""
    view = MusicControlView(bot)
    msg = await ctx.send("🎛️ Music Controls", view=view)
    bot.register_control_message(ctx.guild.id, msg)

@bot.command(name='loop')
async def loop_command(ctx, mode: str = None):
    """Set loop mode: off, song, queue"""
    if mode is None:
        current_mode = bot.loop_mode.get(ctx.guild.id, 0)
        modes = {0: "Off", 1: "Song", 2: "Queue"}
        embed = discord.Embed(title="🔁 Loop Mode", description=f"Current loop mode: **{modes[current_mode]}**", color=0x00ff00)
        await ctx.send(embed=embed)
        return
    
    mode = mode.lower()
    if mode in ['off', '0']:
        bot.loop_mode[ctx.guild.id] = 0
        embed = discord.Embed(title="🔁 Loop Mode", description="Loop mode: **Off**", color=0xff9900)
    elif mode in ['song', '1']:
        bot.loop_mode[ctx.guild.id] = 1
        embed = discord.Embed(title="🔁 Loop Mode", description="Loop mode: **Song**", color=0x00ff00)
    elif mode in ['queue', '2']:
        bot.loop_mode[ctx.guild.id] = 2
        embed = discord.Embed(title="🔁 Loop Mode", description="Loop mode: **Queue**", color=0x00ff00)
    else:
        embed = discord.Embed(title="❌ Error", description="Invalid loop mode! Use: `off`, `song`, or `queue`", color=0xff0000)
    
    await ctx.send(embed=embed)

@bot.command(name='nowplaying', aliases=['np'])
async def now_playing(ctx):
    """Show the currently playing song"""
    current = bot.current_song.get(ctx.guild.id)
    
    if not current or not ctx.voice_client or not ctx.voice_client.is_playing():
        embed = discord.Embed(title="❌ Error", description="Nothing is currently playing!", color=0xff0000)
        await ctx.send(embed=embed)
        return
    
    embed = discord.Embed(title="🎵 Now Playing", 
                        description=f"**{current['title']}**", 
                        color=0x00ff00)
    
    if current.get('duration'):
        embed.add_field(name="Duration", value=f"{current['duration'] // 60}:{current['duration'] % 60:02d}", inline=True)
    if current.get('uploader'):
        embed.add_field(name="Uploader", value=current['uploader'], inline=True)
    
    # Show loop mode
    loop_mode = bot.loop_mode.get(ctx.guild.id, 0)
    loop_modes = {0: "Off", 1: "Song", 2: "Queue"}
    embed.add_field(name="Loop", value=loop_modes[loop_mode], inline=True)
    
    if current.get('thumbnail'):
        embed.set_thumbnail(url=current['thumbnail'])
    embed.set_footer(text=f"Requested by {current['requester'].display_name}")
    
    await ctx.send(embed=embed)

@bot.command(name='forceplay', aliases=['fp'])
async def force_play(ctx, *, query):
    """Force play with alternative extraction method"""
    if not ctx.author.voice:
        embed = discord.Embed(title="❌ Error", description="You need to be in a voice channel!", color=0xff0000)
        await ctx.send(embed=embed)
        return
    
    if not ctx.voice_client:
        await join(ctx)
    
    # Use alternative ytdl settings for problematic videos
    alternative_ytdl = yt_dlp.YoutubeDL({
        'format': 'worst[ext=mp4]/worst[ext=webm]/worst',
        'quiet': True,
        'no_warnings': True,
        'default_search': 'ytsearch',
        'ignoreerrors': True,
        'extract_flat': False
    })
    
    try:
        loop = asyncio.get_event_loop()
        data = await loop.run_in_executor(None, lambda: alternative_ytdl.extract_info(query, download=False))
        
        if 'entries' in data:
            data = data['entries'][0]
        
        song_info = {
            'url': data['webpage_url'],
            'title': data.get('title', 'Unknown'),
            'duration': data.get('duration', 0),
            'thumbnail': data.get('thumbnail'),
            'uploader': data.get('uploader', 'Unknown'),
            'requester': ctx.author
        }
        
        queue = bot.get_queue(ctx.guild.id)
        queue.append(song_info)
        
        embed = discord.Embed(title="🔧 Force Added to Queue", 
                            description=f"**{song_info['title']}**\nUsed alternative extraction method", 
                            color=0x00ff00)
        await ctx.send(embed=embed)
        
        if not ctx.voice_client.is_playing():
            await play_next(ctx)
            
    except Exception as e:
        embed = discord.Embed(title="❌ Force Play Failed", 
                            description=f"Even alternative method failed: {str(e)[:100]}...", 
                            color=0xff0000)
        await ctx.send(embed=embed)

@bot.command(name='test')
async def test_video(ctx, *, url):
    """Test if a video URL works"""
    try:
        loop = asyncio.get_event_loop()
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=False))
        
        if 'entries' in data:
            data = data['entries'][0]
        
        embed = discord.Embed(title="✅ Video Test Successful", color=0x00ff00)
        embed.add_field(name="Title", value=data.get('title', 'Unknown'), inline=False)
        embed.add_field(name="Duration", value=f"{data.get('duration', 0) // 60}:{data.get('duration', 0) % 60:02d}", inline=True)
        embed.add_field(name="Uploader", value=data.get('uploader', 'Unknown'), inline=True)
        
        if data.get('thumbnail'):
            embed.set_thumbnail(url=data['thumbnail'])
        
        await ctx.send(embed=embed)
        
    except Exception as e:
        embed = discord.Embed(title="❌ Video Test Failed", 
                            description=f"Error: {str(e)[:200]}...", 
                            color=0xff0000)
        await ctx.send(embed=embed)

@bot.command(name='formats')
async def list_formats(ctx, *, url: str):
    """List available formats for a YouTube URL (debugging helper)."""
    try:
        loop = asyncio.get_event_loop()
        info = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=False))
        if 'formats' not in info:
            raise Exception('No formats available')
        lines = []
        for f in info['formats'][-25:]:  # limit output
            abr = f.get('abr') or f.get('tbr')
            acodec = f.get('acodec')
            ext = f.get('ext')
            vcodec = f.get('vcodec')
            fmt_id = f.get('format_id')
            lines.append(f"id={fmt_id} ext={ext} acodec={acodec} vcodec={vcodec} br={abr}")
        text = "\n".join(lines) or 'No format lines.'
        if len(text) > 1900:
            text = text[:1900] + '\n...'
        # Send as a code block without using an f-string to avoid quoting issues
        await ctx.send("```\n" + text + "\n```")
    except Exception as e:
        await ctx.send(f"Failed to list formats: {e}")

@bot.command(name='commands')
async def help_command(ctx):
    """Show all available commands"""
    embed = discord.Embed(title="🎵 Music Bot Commands", 
                        description="Here are all available commands:", 
                        color=0x00ff00)
    
    commands_list = [
        ("**Music Commands**", ""),
        ("`!play <song/url>`", "Play music from YouTube or Spotify"),
        ("`!forceplay <song/url>`", "Force play with alternative method"),
        ("`!skip`", "Skip the current song"),
        ("`!pause`", "Pause the current song"),
        ("`!resume`", "Resume the paused song"),
        ("`!stop`", "Stop playing and clear queue"),
        ("`!queue`", "Show the current queue"),
        ("`!clear`", "Clear the entire queue"),
        ("`!shuffle`", "Shuffle the queue"),
    ("`!panel`", "Show button controls panel"),
        ("`!nowplaying`", "Show current song info"),
        ("", ""),
        ("**Controls**", ""),
        ("`!volume <0-100>`", "Set the volume"),
        ("`!loop <off/song/queue>`", "Set loop mode"),
        ("`!join`", "Join your voice channel"),
        ("`!leave`", "Leave the voice channel"),
        ("", ""),
        ("**Utilities**", ""),
        ("`!test <url>`", "Test if a video URL works"),
        ("`!commands`", "Show this help message")
    ]
    
    for name, value in commands_list:
        embed.add_field(name=name, value=value, inline=False)
    
    embed.set_footer(text="Supports YouTube URLs, YouTube searches, Spotify tracks, and Spotify playlists!")
    await ctx.send(embed=embed)

# Error handling
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        embed = discord.Embed(title="❌ Command Not Found", 
                            description="Use `!commands` to see all available commands", 
                            color=0xff0000)
        await ctx.send(embed=embed)
    elif isinstance(error, commands.MissingRequiredArgument):
        embed = discord.Embed(title="❌ Missing Argument", 
                            description=f"Missing required argument: {error.param}", 
                            color=0xff0000)
        await ctx.send(embed=embed)
    else:
        print(f"An error occurred: {error}")

if __name__ == "__main__":
    if not DISCORD_TOKEN:
        print("ERROR: Discord token not found! Please check your .env file.")
    else:
        print("🚀 Starting Discord Music Bot...")
        bot.run(DISCORD_TOKEN)