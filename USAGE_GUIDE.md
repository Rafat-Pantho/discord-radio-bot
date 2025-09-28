# Discord Music Bot - Quick Usage Guide

## 🚀 Your Bot is Ready!

Your Discord music bot is now running and connected to Discord successfully!

## 🎵 How to Use Your Bot

### 1. **Invite the Bot to Your Server**
- Make sure your bot is added to your Discord server with the following permissions:
  - Read Messages
  - Send Messages
  - Connect (to voice channels)
  - Speak (in voice channels)
  - Use Voice Activity

### 2. **Basic Commands**

#### **Playing Music**
```
!play never gonna give you up          # Search YouTube
!play https://youtu.be/dQw4w9WgXcQ    # YouTube URL
!play https://open.spotify.com/track/... # Spotify track
!play https://open.spotify.com/playlist/... # Spotify playlist
```

#### **Queue Management**
```
!queue          # Show current queue
!skip           # Skip current song
!pause          # Pause playback
!resume         # Resume playback
!stop           # Stop and clear queue
!clear          # Clear queue without stopping
```

#### **Controls**
```
!volume 75      # Set volume (0-100)
!shuffle        # Shuffle the queue
!loop off       # Turn off looping
!loop song      # Loop current song
!loop queue     # Loop entire queue
!nowplaying     # Show current song info
```

#### **Bot Management**
```
!join           # Join your voice channel
!leave          # Leave voice channel
!commands       # Show all commands
```

### 3. **Spotify Integration**
- **Single Tracks**: Paste any Spotify track URL - the bot will find it on YouTube
- **Playlists**: Paste any Spotify playlist URL - the bot will add all songs to queue
- **Search Quality**: The bot searches for "Song Name Artist" on YouTube for best results

### 4. **Pro Tips**
- Join a voice channel before using `!play`
- Use `!queue` to see what's coming up next
- The bot shows rich information with thumbnails and duration
- Spotify playlists are limited to 50 songs to avoid spam
- Use `!shuffle` after adding a playlist for variety

## 🎨 Features Showcase

### Rich Embeds
- Beautiful Discord embeds with song thumbnails
- Shows song duration, uploader, and requester
- Queue position indicators
- Loop mode status

### Smart Queue System
- Add multiple songs instantly
- Skip songs seamlessly
- Loop individual songs or entire queue
- Shuffle for random playback order

### Multi-Platform Support
- YouTube videos and playlists
- Spotify tracks and playlists
- YouTube Music compatibility
- Search queries work perfectly

## 🔧 Troubleshooting

### Bot Not Responding?
1. Check if bot is online in your server
2. Verify bot has message permissions
3. Make sure you're using the correct prefix: `!`

### No Audio?
1. Join a voice channel first
2. Check if bot has voice permissions
3. Verify FFmpeg is installed correctly
4. Try `!volume 100` to increase volume

### Spotify Not Working?
1. Check your SPOTIFY_CLIENT_ID in .env
2. Verify SPOTIFY_CLIENT_SECRET in .env
3. Ensure Spotify URLs are public (not private playlists)

## 🎵 Example Session

```
User: !join
Bot: 🎵 Joined Voice Channel - Connected to General

User: !play bohemian rhapsody queen
Bot: 🎵 Now Playing - Bohemian Rhapsody - Queen

User: !play https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M
Bot: 🎵 Adding Spotify Playlist - Adding 50 tracks from Today's Top Hits...

User: !queue
Bot: 📝 Music Queue
     🎵 Now Playing: Bohemian Rhapsody - Queen
     ⏭️ Up Next:
     1. Song 1 from playlist
     2. Song 2 from playlist
     ... and 48 more songs

User: !shuffle
Bot: 🔀 Queue Shuffled - Shuffled the music queue

User: !loop queue
Bot: 🔁 Loop Mode - Loop mode: Queue
```

## 🎉 Enjoy Your Music Bot!

Your Discord music bot is fully featured and ready to use. It supports:
- ✅ YouTube playback
- ✅ Spotify integration  
- ✅ Rich queue management
- ✅ Volume controls
- ✅ Loop modes
- ✅ Interactive commands
- ✅ Beautiful Discord embeds

Have fun listening to music with your friends! 🎵