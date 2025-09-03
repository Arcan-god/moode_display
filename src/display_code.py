# Moode Audio Display for Pico Display Pack 2.8"
# Copyright (C) 2025 [M Lake]
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.


import network
import time
import socket
import json
import gc
from secrets import WIFI_SSID, WIFI_PASSWORD, MOODE_IP
from picographics import PicoGraphics, DISPLAY_PICO_DISPLAY_2

# Set up display - Pico Display Pack 2.8" (320x240 pixels)
display = PicoGraphics(display=DISPLAY_PICO_DISPLAY_2)
WIDTH, HEIGHT = display.get_bounds()

# Define colours using RGB values (0-255)
BLACK = display.create_pen(0, 0, 0)
WHITE = display.create_pen(255, 255, 255)
GREEN = display.create_pen(0, 255, 0)
BLUE = display.create_pen(0, 150, 255)
ORANGE = display.create_pen(255, 165, 0)
RED = display.create_pen(255, 50, 50)
CYAN = display.create_pen(0, 255, 255)
YELLOW = display.create_pen(255, 255, 0)
PURPLE = display.create_pen(160, 80, 255)
LIME = display.create_pen(50, 255, 50)

# Track display state to manage power consumption
display_is_on = True
last_state = None
last_song_data = None

def connect_wifi():
    """Connect to WiFi network with timeout and error handling"""
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    wlan.connect(WIFI_SSID, WIFI_PASSWORD)
    
    # Wait up to 20 seconds for connection
    max_wait = 20
    while max_wait > 0:
        if wlan.status() < 0 or wlan.status() >= 3:
            break
        max_wait -= 1
        print('=== Waiting for connection ===')
        time.sleep(1)
    
    if wlan.status() != 3:
        raise RuntimeError('Network connection failed')
    else:
        print('=== Connected ===')
        status = wlan.ifconfig()
        print(f'=== IP: {status[0]} ===')
        return True

def get_moode_status():
    """
    Fetch current song data from Moode Audio API
    Uses raw socket connection to handle chunked HTTP responses
    Returns parsed JSON data or None if connection fails
    """
    # Free up memory before making HTTP request (important on Pico W)
    gc.collect()
    
    try:
        # Create socket connection to Moode's web server
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(5)  # 5 second timeout to prevent hanging
        s.connect((MOODE_IP, 80))
        
        # Request current song data from Moode's API endpoint
        request = f"GET /command/?cmd=get_currentsong HTTP/1.1\r\nHost: {MOODE_IP}\r\nConnection: close\r\n\r\n"
        s.send(request.encode())
        
        # Read response in chunks to avoid memory overflow on Pico W
        response_parts = []
        total_size = 0
        max_size = 8192  # 8KB limit - sufficient for song metadata, protects against large responses
        
        while total_size < max_size:
            try:
                data = s.recv(1024)  # Read 1KB chunks
                if not data:
                    break
                response_parts.append(data)
                total_size += len(data)
            except:
                break
        
        s.close()
        
        # Join chunks and parse HTTP response
        response = b''.join(response_parts)
        response_str = response.decode('utf-8')
        
        # Split HTTP headers from body
        if '\r\n\r\n' in response_str:
            headers, body = response_str.split('\r\n\r\n', 1)
            
            if '200 OK' in headers:
                # Moode returns chunked encoding - extract JSON from chunks
                json_data = parse_chunked_response(body)
                if json_data:
                    song_data = json.loads(json_data)
                    
                    # Clean up memory after successful parsing
                    del response_parts
                    del response
                    gc.collect()
                    
                    return song_data
                else:
                    print("=== Could not parse chunked response ===")
                    return None
            else:
                print(f"=== HTTP Error: {headers.split(chr(13)+chr(10))[0]} ===")
                return None
        else:
            print("=== Invalid HTTP response ===")
            return None
            
    except Exception as e:
        print(f"=== Moode connection error: {e} ===")
        return None

def parse_chunked_response(body):
    """
    Parse HTTP chunked transfer encoding to extract JSON payload
    
    Chunked encoding format:
    [hex chunk size]\r\n
    [chunk data]\r\n
    [hex chunk size]\r\n
    [chunk data]\r\n
    0\r\n
    \r\n
    
    Returns the JSON string or None if parsing fails
    """
    try:
        lines = body.split('\r\n')
        json_content = ""
        
        for line in lines:
            # Skip empty lines and whitespace
            if line and not line.isspace():
                # Check if line is a hex chunk size marker
                try:
                    int(line, 16)  # If this succeeds, it's a chunk size
                    continue
                except ValueError:
                    # Not a hex number, likely content data
                    # Look for JSON objects (start with { and end with })
                    if line.startswith('{') and line.endswith('}'):
                        json_content = line
                        break
        
        return json_content if json_content else None
        
    except Exception as e:
        print(f"=== Error parsing chunks: {e} ===")
        return None

def sleep_display():
    """Turn off display backlight and show black screen to save power"""
    global display_is_on
    if display_is_on:
        display.set_backlight(0)  # Turn off backlight completely
        display.set_pen(BLACK)
        display.clear()
        display.update()
        display_is_on = False
        print("=== Display sleeping ===")

def wake_display():
    """Wake up display by restoring backlight"""
    global display_is_on
    if not display_is_on:
        display.set_backlight(0.8)  # 80% brightness - adjust as needed
        display_is_on = True
        print("=== Display waking ===")

def show_startup_screen():
    """Display welcome message during system startup"""
    display.set_pen(BLACK)
    display.clear()
    display.set_font("bitmap8")
    
    # Show startup message in lime green
    display.set_pen(LIME)
    display.text("Welcome to moode", 20, 60, scale=3)
    display.text("Starting...", 20, 120, scale=2)
    
    display.update()
    time.sleep(2)

def display_song_info(song_data):
    """
    Display current song information with adaptive layout
    
    Layout varies based on content type:
    - Radio stations: Station name (top), current track (middle), status (bottom)
    - Music files: Title (top), artist/album (middle), status (bottom)
    
    Power management: sleeps display when music stops
    """
    global last_state, last_song_data
    
    # Handle connection errors
    if song_data is None:
        wake_display()
        display.set_pen(BLACK)
        display.clear()
        display.set_pen(RED)
        display.set_font("bitmap8")
        display.text("No connection", 20, 80, scale=3)
        display.text("to Moode", 20, 120, scale=3)
        display.update()
        time.sleep(2)
        sleep_display()
        return
    
    # Extract playback state
    state = song_data.get('state', 'stopped')
    
    # Sleep display when music stops to save power
    if state in ['stop', 'stopped']:
        if state != last_state:
            wake_display()
            display.set_pen(BLACK)
            display.clear()
            display.set_pen(ORANGE)
            display.set_font("bitmap8")
            display.text("STOPPED", 10, 200, scale=3)  # Bottom left position
            display.update()
            time.sleep(3)
        
        sleep_display()
        last_state = state
        return
    
    # Wake display for active playback
    wake_display()
    display.set_pen(BLACK)
    display.clear()
    display.set_font("bitmap8")  # 8x8 pixel bitmap font
    
    # Extract metadata from Moode API response
    title = song_data.get('title', 'Unknown')
    artist = song_data.get('artist', 'Unknown Artist')
    album = song_data.get('album', '')
    bitrate = song_data.get('bitrate', '')
    
    # Radio station layout (detected by artist="Radio station" and album=station name)
    if artist == "Radio station" and album:
        
        # TOP SECTION: Radio station name in large green text
        display.set_pen(GREEN)
        # Wrap station name to fit display width (18 chars per line at scale=3)
        station_lines = wrap_text(album, 18)
        for i, line in enumerate(station_lines[:2]):  # Maximum 2 lines
            display.text(line, 10, 15 + (i * 25), scale=3)  # Y position: 15, 40
        
        # MIDDLE SECTION: Current track information or listening message
        has_song_info = (title != "Radio station" and title != album and len(title) > 3)
        
        if has_song_info:
            # Display actual song/track information
            display.set_pen(WHITE)
            song_lines = wrap_text(title, 20)  # 20 chars per line at scale=3
            middle_y = 90  # Start position for middle section
            for i, line in enumerate(song_lines[:3]):  # Up to 3 lines
                display.text(line, 10, middle_y + (i * 25), scale=3)
        else:
            # No specific track info - show generic listening message
            display.set_pen(CYAN)
            display.text("Listening to", 10, 90, scale=2)
            display.text("Radio", 10, 115, scale=4)

        
        # BOTTOM LEFT: Playback status
        if state == 'pause':
            display.set_pen(YELLOW)
            display.text("PAUSED", 10, 200, scale=2)
        else:
            display.set_pen(GREEN)
            display.text("PLAYING", 10, 200, scale=2)
        
        # BOTTOM RIGHT: Audio bitrate (if available)
        if bitrate:
            display.set_pen(CYAN)
            # Right-align bitrate text (rough calculation: 6 pixels per char * scale)
            bitrate_width = len(bitrate) * 6 * 2
            display.text(bitrate, WIDTH - bitrate_width - 10, 200, scale=2)
    
    else:
        # Music file layout - title, artist, album hierarchy
        
        # TOP SECTION: Song title in large white text
        display.set_pen(WHITE)
        title_lines = wrap_text(title, 18)  # 18 chars per line at scale=4
        for i, line in enumerate(title_lines[:2]):  # Maximum 2 lines for title
            display.text(line, 10, 15 + (i * 25), scale=4)  # Larger scale for emphasis
        
        # MIDDLE SECTION: Artist in green
        display.set_pen(GREEN)
        artist_lines = wrap_text(artist, 20)
        for i, line in enumerate(artist_lines[:1]):  # Single line for artist
            display.text(line, 10, 90, scale=3)
        
        # Album information (if available and space permits)
        if album:
            display.set_pen(BLUE)
            album_lines = wrap_text(album, 22)  # Smaller text for album
            for i, line in enumerate(album_lines[:1]):  # Single line for album
                display.text(line, 10, 125, scale=2)
        
        # BOTTOM LEFT: Playback status
        if state == 'pause':
            display.set_pen(YELLOW)
            display.text("PAUSED", 10, 200, scale=2)
        else:
            display.set_pen(GREEN)
            display.text("PLAYING", 10, 200, scale=2)
        
        # BOTTOM RIGHT: Audio bitrate
        if bitrate:
            display.set_pen(CYAN)
            bitrate_width = len(bitrate) * 6 * 2  # Character width calculation
            display.text(bitrate, WIDTH - bitrate_width - 10, 200, scale=2)
    
    display.update()
    last_state = state
    last_song_data = song_data


def wrap_text(text, max_chars):
    """
    Wrap text to fit display width with word boundary respect
    
    Args:
        text: String to wrap
        max_chars: Maximum characters per line
        
    Returns:
        List of wrapped text lines
    """
    if len(text) <= max_chars:
        return [text]
    
    # Split on word boundaries when possible
    words = text.split(' ')
    lines = []
    current_line = ""
    
    for word in words:
        # Check if adding this word would exceed line length
        if len(current_line + " " + word) <= max_chars:
            if current_line:
                current_line += " " + word
            else:
                current_line = word
        else:
            # Start new line
            if current_line:
                lines.append(current_line)
                current_line = word
            else:
                # Single word too long - truncate it
                lines.append(word[:max_chars])
                current_line = ""
    
    # Add final line if not empty
    if current_line:
        lines.append(current_line)
    
    return lines

# Main program
def main():
    """
    Main program loop
    
    1. Connect to WiFi
    2. Continuously fetch and display Moode status
    3. Update frequency depends on display state (5s active, 15s sleeping)
    """
    global display_is_on
    
    print("=== Moode display starting ===")
    
    # Show welcome screen during startup
    show_startup_screen()
    
    print("=== Connecting to WiFi ===")
    try:
        if connect_wifi():
            print("=== WiFi connected! Starting Moode display ===")
            # Show connection success message
            display.set_pen(BLACK)
            display.clear()
            display.set_pen(LIME)
            display.set_font("bitmap8")
            display.text("WIFI Connected", 20, 60, scale=3)
            display.text("Starting...", 20, 120, scale=2)
            
            display.update()
            time.sleep(2)
            
            # Main display loop
            while True:
                # Fetch current playing information from Moode
                song_data = get_moode_status()
                display_song_info(song_data)
                
                # Adaptive update frequency for power efficiency
                if display_is_on:
                    time.sleep(5)   # Update every 5 seconds when active
                else:
                    time.sleep(15)  # Check every 15 seconds when sleeping
                    
    except Exception as e:
        print(f"=== Main error: {e} ===")
        # Display error message on screen
        display.set_pen(BLACK)
        display.clear()
        display.set_pen(RED)
        display.set_font("bitmap8")
        display.text("ERROR:", 10, 10, scale=2)
        display.text(str(e)[:20], 10, 40, scale=1)  # Truncate long error messages
        display.update()

if __name__ == "__main__":
    main()