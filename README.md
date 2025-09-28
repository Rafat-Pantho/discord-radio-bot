# Discord Music Bot

A feature-rich Discord music bot that supports both YouTube and Spotify playback with an interactive command interface.

## Features

### 🎵 Music Playback
- **YouTube Support**: Direct URLs, playlists, and search queries
- **Spotify Integration**: Track and playlist support (searches YouTube for actual playback)
- **High-Quality Audio**: Optimized for clear sound
- **Queue Management**: Add, skip, shuffle, and clear songs

### 🎛️ Controls
- **Volume Control**: Adjust volume from 0-100%
- **Loop Modes**: Loop off/single song/entire queue
- **Pause/Resume**: Full playback control
- **Skip**: Skip current song instantly

### 📝 Queue Features
- **View Queue**: See current and upcoming songs
- **Shuffle**: Randomize queue order
- **Clear Queue**: Remove all queued songs
- **Position Display**: Shows queue position for new songs

### 🎨 Interactive Interface
- **Rich Embeds**: Beautiful Discord embeds with thumbnails
- **Real-time Updates**: Live status updates
- **Song Information**: Title, duration, uploader details
- **User Attribution**: Shows who requested each song

## Commands

### Basic Commands
- `!play <song/url>` - Play music (YouTube/Spotify URLs or search terms)
- `!skip` - Skip current song
- `!pause` - Pause playback
- `!resume` - Resume playback
- `!stop` - Stop and clear queue
- `!queue` - Show current queue
- `!nowplaying` - Show current song info

### Advanced Commands
- `!volume <0-100>` - Set volume level
- `!loop <off/song/queue>` - Set loop mode
- `!shuffle` - Shuffle the queue
- `!clear` - Clear entire queue
- `!join` - Join your voice channel
- `!leave` - Leave voice channel
- `!help` - Show all commands

## Requirements

- Python 3.8+ (Recommended: 3.10+)
- FFmpeg installed on system
- Discord Bot Token
- Spotify Client ID & Secret (for Spotify features)

## Quick Start

### 1. Install Dependencies
```bash
# Activate virtual environment
discord_bot_env\Scripts\activate

# Install packages
pip install -r requirements.txt
```

### 2. Configure Environment
Edit `.env` file with your tokens:
```
DISCORD_TOKEN=your_discord_bot_token
SPOTIFY_CLIENT_ID=your_spotify_client_id
SPOTIFY_CLIENT_SECRET=your_spotify_client_secret
```

### 3. Run the Bot
```bash
# Using the launcher
start_bot.bat

# Or directly
python music_bot.py
```

## Usage Examples

### Playing Music
```
!play never gonna give you up
!play https://www.youtube.com/watch?v=dQw4w9WgXcQ
!play https://open.spotify.com/track/4cOdK2wGLETKBW3PvgPWqT
!play https://open.spotify.com/playlist/1SWfXiGiNnJXezDOcwiDns
```

### Queue Management
```
!queue          # View current queue
!skip           # Skip current song
!shuffle        # Shuffle queue
!clear          # Clear all songs
!loop queue     # Loop entire queue
```

### Controls
```
!volume 75      # Set volume to 75%
!pause          # Pause current song
!resume         # Resume playback
!nowplaying     # Show current song info
```

## Technical Details

### Architecture
- **Asynchronous**: Built with discord.py for efficient handling
- **Queue System**: Per-guild queues with deque for optimal performance
- **Stream Processing**: Real-time audio streaming without downloads
- **Error Handling**: Comprehensive error management and recovery

### Audio Processing
- **yt-dlp**: Latest YouTube extraction library
- **FFmpeg**: Professional audio processing
- **PCM Audio**: High-quality audio streaming
- **Volume Transform**: Real-time volume adjustment

### Spotify Integration
- **Search & Play**: Converts Spotify tracks to YouTube searches
- **Playlist Support**: Bulk import from Spotify playlists
- **Metadata Extraction**: Rich song information display
- **Rate Limiting**: Respectful API usage

## Troubleshooting

### Common Issues
1. **Bot doesn't respond**: Check Discord token and bot permissions
2. **No audio**: Ensure FFmpeg is installed and accessible
3. **Spotify not working**: Verify Client ID and Secret
4. **Connection issues**: Check voice channel permissions

### Performance Tips
- Use `!clear` to free memory if queue gets very large
- Restart bot periodically for optimal performance
- Ensure stable internet connection for streaming

## Development

### Project Structure
```
discord bot/
├── music_bot.py           # Main bot file
├── requirements.txt       # Python dependencies
├── .env                  # Environment variables
├── start_bot.bat         # Windows launcher
└── README.md             # This file
```

### Contributing
1. Fork the repository
2. Create feature branch
3. Test thoroughly
4. Submit pull request

## License

This project is for educational purposes. Ensure compliance with Discord ToS, YouTube ToS, and Spotify ToS when using.