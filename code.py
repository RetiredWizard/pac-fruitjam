"""
Pac-Man Clone for Adafruit Fruit Jam
CircuitPython - 640x480 display, SNES USB controller, I2S audio
"""

import sys
import gc
import time
import random
import os
import board
import displayio
import audiobusio
import supervisor
import synthio
import bitmaptools
from adafruit_fruitjam.peripherals import Peripherals, request_display_config, VALID_DISPLAY_SIZES
import adafruit_imageload
import relic_usb_host_gamepad

# get Fruit Jam OS config if available
try:
    import launcher_config

    config = launcher_config.LauncherConfig()
except ImportError:
    config = None

try:
    from adafruit_bitmap_font import bitmap_font
    from adafruit_display_text import label
except ImportError:
    bitmap_font = None
    label = None

# =============================================================================
# CONSTANTS
# =============================================================================

# Tile dimensions
TILE_SIZE = 6
TILE_SIZE_X_2 = TILE_SIZE * 2
TILE_SIZE__2 = TILE_SIZE // 2

# Maze dimensions in tiles
MAZE_COLS = 28
MAZE_ROWS = 31

# Game area dimensions (from sprite sheet)
GAME_WIDTH = MAZE_COLS * TILE_SIZE
GAME_HEIGHT = MAZE_ROWS * TILE_SIZE

# Screen dimensions (Fruit Jam native)
if (SCREEN_WIDTH := os.getenv("CIRCUITPY_DISPLAY_WIDTH")) is not None:
    SCREEN_HEIGHT = next((h for w, h in VALID_DISPLAY_SIZES if SCREEN_WIDTH == w))
else:
    SCREEN_WIDTH = 320
    SCREEN_HEIGHT = 240
SCREEN_WIDE = (SCREEN_WIDTH / SCREEN_HEIGHT) >= 1.5

# Scale factor for display (2x looks good on 640x480)
SCORE_SCALE = GAME_SCALE = round(SCREEN_WIDTH / 320)

# Force lower resolution for better performance
if SCORE_SCALE > 1:
    SCREEN_WIDTH //= SCORE_SCALE
    SCREEN_HEIGHT //= SCORE_SCALE
    SCORE_SCALE = GAME_SCALE = 1

# Display dimensions
DISPLAY_ROTATION = os.getenv("CIRCUITPY_DISPLAY_ROTATION", 0)
DISPLAY_VERTICAL = DISPLAY_ROTATION in (90, 270)  # Tate mode / vertical orientation

DISPLAY_WIDTH = SCREEN_HEIGHT if DISPLAY_VERTICAL else SCREEN_WIDTH
DISPLAY_HEIGHT = SCREEN_WIDTH if DISPLAY_VERTICAL else SCREEN_HEIGHT

# Offset to position game on right side of screen
# Right side: 640 - (224*2) = 192 pixels from right edge
OFFSET_X = (DISPLAY_WIDTH - GAME_WIDTH * GAME_SCALE) // 2
OFFSET_Y = (DISPLAY_HEIGHT - GAME_HEIGHT * GAME_SCALE) // 2  # Centered vertically

# Movement speeds (pixels per frame at game resolution)
PACMAN_SPEED = 1.3 * TILE_SIZE / 8 # was 1.3
GHOST_SPEED = 1.22 * TILE_SIZE / 8 # was 1.22
FRAME_DELAY = 0.016  # ~60 FPS target  was 0.016

# Directions
DIR_NONE = 0
DIR_UP = 1
DIR_DOWN = 2
DIR_LEFT = 3
DIR_RIGHT = 4

# Maze tile types
EMPTY = 0
WALL = 1
DOT = 2
POWER = 3
GATE = 4

# Ghost Modes
MODE_SCATTER = 0
MODE_CHASE = 1
MODE_FRIGHTENED = 2
MODE_EATEN = 3

# Game States
STATE_PLAY = 0
STATE_DYING = 1
STATE_EATING_GHOST = 2
STATE_GAME_OVER = 3
STATE_LEVEL_COMPLETE = 4
STATE_EATING_FRUIT = 5
STATE_READY = 6

# Fruit point values per level
FRUIT_POINTS = [100, 300, 500, 500, 700, 700, 1000, 1000, 2000, 2000, 3000, 3000, 5000]

# Mode Timings (seconds)
MODE_TIMES = [7, 20, 7, 20, 5, 20, 5, 999999]

# Frightened Mode Duration (Frames at 60fps)
FRIGHTENED_DURATION = 360

# High score file path
HIGH_SCORE_FILE = "/saves/highscores.txt"

# Sprite coordinates
# fmt: off
SPRITE_LIFE = (16 * TILE_SIZE, TILE_SIZE_X_2)
FRUIT_LEVELS = [
    (4 * TILE_SIZE, 6 * TILE_SIZE), (6 * TILE_SIZE, 6 * TILE_SIZE),
    (8 * TILE_SIZE, 6 * TILE_SIZE), (8 * TILE_SIZE, 6 * TILE_SIZE),
    (10 * TILE_SIZE, 6 * TILE_SIZE), (10 * TILE_SIZE, 6 * TILE_SIZE),
    (12 * TILE_SIZE, 6 * TILE_SIZE), (12 * TILE_SIZE, 6 * TILE_SIZE),
    (14 * TILE_SIZE, 6 * TILE_SIZE), (14 * TILE_SIZE, 6 * TILE_SIZE),
    (16 * TILE_SIZE, 6 * TILE_SIZE), (16 * TILE_SIZE, 6 * TILE_SIZE),
    (18 * TILE_SIZE, 6 * TILE_SIZE)
]

# =============================================================================
# MAZE DATA
# =============================================================================

MAZE_DATA = [
    [1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1],
    [1,0,0,0,0,0,0,0,0,0,0,0,0,1,1,0,0,0,0,0,0,0,0,0,0,0,0,1],
    [1,0,1,1,1,1,0,1,1,1,1,1,0,1,1,0,1,1,1,1,1,0,1,1,1,1,0,1],
    [1,0,1,0,0,1,0,1,0,0,0,1,0,1,1,0,1,0,0,0,1,0,1,0,0,1,0,1],
    [1,0,1,1,1,1,0,1,1,1,1,1,0,1,1,0,1,1,1,1,1,0,1,1,1,1,0,1],
    [1,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,1],
    [1,0,1,1,1,1,0,1,1,0,1,1,1,1,1,1,1,1,0,1,1,0,1,1,1,1,0,1],
    [1,0,1,1,1,1,0,1,1,0,1,1,1,1,1,1,1,1,0,1,1,0,1,1,1,1,0,1],
    [1,0,0,0,0,0,0,1,1,0,0,0,0,1,1,0,0,0,0,1,1,0,0,0,0,0,0,1],
    [1,1,1,1,1,1,0,1,1,1,1,1,0,1,1,0,1,1,1,1,1,0,1,1,1,1,1,1],
    [0,0,0,0,0,1,0,1,1,1,1,1,0,1,1,0,1,1,1,1,1,0,1,0,0,0,0,0],
    [0,0,0,0,0,1,0,1,1,0,0,0,0,0,0,0,0,0,0,1,1,0,1,0,0,0,0,0],
    [0,0,0,0,0,1,0,1,1,0,1,1,1,0,0,1,1,1,0,1,1,0,1,0,0,0,0,0],
    [1,1,1,1,1,1,0,1,1,0,1,1,1,0,0,1,1,1,0,1,1,0,1,1,1,1,1,1],
    [0,0,0,0,0,0,0,0,0,0,1,0,0,0,0,0,0,1,0,0,0,0,0,0,0,0,0,0],
    [1,1,1,1,1,1,0,1,1,0,1,1,1,1,1,1,1,1,0,1,1,0,1,1,1,1,1,1],
    [0,0,0,0,0,1,0,1,1,0,1,1,1,1,1,1,1,1,0,1,1,0,1,0,0,0,0,0],
    [0,0,0,0,0,1,0,1,1,0,0,0,0,0,0,0,0,0,0,1,1,0,1,0,0,0,0,0],
    [0,0,0,0,0,1,0,1,1,0,1,1,1,1,1,1,1,1,0,1,1,0,1,0,0,0,0,0],
    [1,1,1,1,1,1,0,1,1,0,1,1,1,1,1,1,1,1,0,1,1,0,1,1,1,1,1,1],
    [1,0,0,0,0,0,0,0,0,0,0,0,0,1,1,0,0,0,0,0,0,0,0,0,0,0,0,1],
    [1,0,1,1,1,1,0,1,1,1,1,1,0,1,1,0,1,1,1,1,1,0,1,1,1,1,0,1],
    [1,0,1,1,1,1,0,1,1,1,1,1,0,1,1,0,1,1,1,1,1,0,1,1,1,1,0,1],
    [1,0,0,0,1,1,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,1,1,0,0,0,1],
    [1,1,1,0,1,1,0,1,1,0,1,1,1,1,1,1,1,1,0,1,1,0,1,1,0,1,1,1],
    [1,1,1,0,1,1,0,1,1,0,1,1,1,1,1,1,1,1,0,1,1,0,1,1,0,1,1,1],
    [1,0,0,0,0,0,0,1,1,0,0,0,0,1,1,0,0,0,0,1,1,0,0,0,0,0,0,1],
    [1,0,1,1,1,1,1,1,1,1,1,1,0,1,1,0,1,1,1,1,1,1,1,1,1,1,0,1],
    [1,0,1,1,1,1,1,1,1,1,1,1,0,1,1,0,1,1,1,1,1,1,1,1,1,1,0,1],
    [1,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,1],
    [1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1],
]

POWER_PELLETS = [(1, 3), (26, 3), (1, 23), (26, 23)]
# fmt: on


# =============================================================================
# SOUND ENGINE (I2S + Synthio)
# =============================================================================


class SoundEngine:
    """I2S audio output using TLV320DAC3100 DAC for Pac-Man sounds."""

    def __init__(self):
        self.enabled = True
        self.synth = None
        self.peripherals = None
        self.audio = None
        self.dac = None
        self._setup_audio()

        # Waka frequencies
        self.waka_freq_1 = 261  # C4
        self.waka_freq_2 = 392  # G4
        self.waka_toggle = False

    def _setup_audio(self):
        """Initialize TLV320DAC3100 I2S DAC on Fruit Jam."""
        try:
            # Fruit Jam TLV320DAC3100 I2S DAC pinout:
            # I2S_DIN = GPIO24 (board.I2S_DIN)
            # I2S_BCLK = GPIO26 (board.I2S_BCLK)
            # I2S_WS = GPIO27 (board.I2S_WS)
            # PERIPH_RESET = GPIO22 (board.PERIPH_RESET) - shared with ESP32-C6

            self.peripherals = Peripherals(
                audio_output=(config.audio_output if config else "speaker"),
                safe_volume_limit=(
                    config.audio_volume_override_danger if config else 0.75
                ),
                sample_rate=22050,
                bit_depth=16,
            )
            self.peripherals.volume = config.audio_volume if config else 0.35

            # Try to use adafruit_tlv320 library if available
            if self.peripherals.dac is not None:
                # Create I2S output
                self.audio = self.peripherals.audio
                print("TLV320DAC3100 audio initialized with library")

            else:
                # Fallback: try basic I2S without DAC library
                print("TLV320 library not found, trying basic I2S")
                self.audio = audiobusio.I2SOut(
                    board.I2S_BCLK, board.I2S_WS, board.I2S_DIN
                )
                print("Basic I2S audio initialized")

            # Create synthio synthesizer
            self.synth = synthio.Synthesizer(sample_rate=22050)
            self.audio.play(self.synth)

        except Exception as e:
            print(f"Audio init error: {e}")
            self.enabled = False

    def play_tone(self, frequency):
        """Play a simple tone."""
        if not self.enabled or not self.synth:
            return
        try:
            self.stop()
            self.synth.release_all_then_press(synthio.Note(frequency))
        except Exception:
            pass

    def stop(self):
        """Stop current sound."""
        if self.synth:
            try:
                self.synth.release_all()
            except:
                pass

    def play_waka(self):
        """Play the alternating waka sound."""
        freq = self.waka_freq_2 if self.waka_toggle else self.waka_freq_1
        self.waka_toggle = not self.waka_toggle
        self.play_tone(freq)

    def play_death_note(self, frame_idx):
        """Play descending death sound."""
        freq = max(500 - (frame_idx * 35), 100)
        self.play_tone(freq)

    def play_eat_ghost(self):
        """Play ghost eating sound - quick ascending."""
        if not self.enabled or not self.synth:
            return
        for freq in range(200, 800, 150):
            self.play_tone(freq)
            time.sleep(0.02)
        self.stop()

    def play_startup(self):
        """Play startup jingle."""
        if not self.enabled or not self.synth:
            return

        T = 0.08
        H = T * 2

        # fmt: off
        melody = [
            (494, T), (988, T), (740, T), (622, T), (988, T), (740, T), (622, H),
            (523, T), (1047, T), (784, T), (659, T), (1047, T), (784, T), (659, H),
            (494, T), (988, T), (740, T), (622, T), (988, T), (740, T), (622, H),
            (622, T), (659, T), (698, T), (698, T), (740, T), (784, T),
            (784, T), (831, T), (880, T), (988, H)
        ]
        # fmt: on

        for freq, duration in melody:
            self.play_tone(freq)
            time.sleep(duration)
            self.stop()
            time.sleep(0.015)

        self.stop()

    def toggle(self):
        """Toggle sound on/off."""
        if self.enabled:
            self.stop()
        self.enabled = not self.enabled
        return self.enabled
    
    def deinit(self):
        self.stop()
        if self.audio and (self.peripherals is None or self.peripherals.dac is None):
            self.audio.stop()
        if self.peripherals:
            self.peripherals.deinit()


# =============================================================================
# HIGH SCORE MANAGER
# =============================================================================


class HighScoreManager:
    """Manages top 10 high scores saved to file."""

    def __init__(self, filepath=HIGH_SCORE_FILE):
        self.filepath = filepath
        self.scores = []
        self._ensure_directory()
        self.load()

    def _ensure_directory(self):
        """Ensure SAVES directory exists."""
        try:
            os.listdir("/saves")
        except OSError:
            try:
                os.mkdir("/saves")
            except OSError:
                pass

    def load(self):
        """Load scores from file."""
        self.scores = []
        try:
            with open(self.filepath, "r") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        parts = line.split(",")
                        if len(parts) >= 2:
                            try:
                                name = parts[1][:3].upper()
                                self.scores.append((int(parts[0]), name))
                            except ValueError:
                                continue
            self.scores.sort(key=lambda x: x[0], reverse=True)
            self.scores = self.scores[:10]
        except OSError:
            self.scores = [(10000, "AAA")]  # Default high score

    def save(self):
        """Save scores to file."""
        try:
            with open(self.filepath, "w") as f:
                for _score, name in self.scores[:10]:
                    f.write(f"{_score},{name}\n")
        except OSError as e:
            print(f"Error saving scores: {e}")

    def add_score(self, _score, name="PAC"):
        """Add a new score if it qualifies."""
        name = name[:3].upper()
        self.scores.append((_score, name))
        self.scores.sort(key=lambda x: x[0], reverse=True)
        self.scores = self.scores[:10]
        self.save()

    def is_high_score(self, _score):
        """Check if score qualifies for top 10."""
        if len(self.scores) < 10:
            return True
        return _score > self.scores[-1][0]

    def get_high_score(self):
        """Get the highest score."""
        return self.scores[0][0] if self.scores else 0


# =============================================================================
# DISPLAY SETUP
# =============================================================================

# Get the display from board (Fruit Jam has built-in display support)
print("Initializing DVI display...")
try:
    # Initialize Fruit Jam display (640x480 DVI)
    request_display_config(SCREEN_WIDTH, SCREEN_HEIGHT)
    display = supervisor.runtime.display
    print(f"Display: {display.width}x{display.height}")
except Exception as e:
    print(f"Display init error: {e}")

    sys.exit()
finally:
    display.rotation = DISPLAY_ROTATION

main_group = displayio.Group()
display.root_group = main_group

# Game group with 2x scaling positioned on right side
game_group = displayio.Group(scale=GAME_SCALE, x=OFFSET_X, y=OFFSET_Y)

# Background for left side (score panel)
score_group = displayio.Group(scale=SCORE_SCALE)
main_group.append(score_group)

if not DISPLAY_VERTICAL:
    left_panel_bmp = displayio.Bitmap(OFFSET_X // SCORE_SCALE, DISPLAY_HEIGHT // SCORE_SCALE, 1)
    left_panel_palette = displayio.Palette(1)
    left_panel_palette[0] = 0x000000
    left_panel_bg = displayio.TileGrid(
        left_panel_bmp, pixel_shader=left_panel_palette, x=0, y=0
    )
    score_group.append(left_panel_bg)

# =============================================================================
# LOAD MAZE BACKGROUND
# =============================================================================

_maze_bmp, maze_palette = adafruit_imageload.load("images/maze_empty.bmp")
if TILE_SIZE != 6:
    maze_bmp = displayio.Bitmap(GAME_WIDTH, GAME_HEIGHT, 2 ** _maze_bmp.bits_per_value)
    bitmaptools.rotozoom(maze_bmp, _maze_bmp, scale = TILE_SIZE / 6)
else:
    maze_bmp = _maze_bmp

maze_bg = displayio.TileGrid(maze_bmp, pixel_shader=maze_palette, x=0, y=0)
game_group.append(maze_bg)

# =============================================================================
# ITEMS GRID (DOTS & POWER PELLETS)
# =============================================================================

items_bitmap = displayio.Bitmap(TILE_SIZE, TILE_SIZE * 3, 3)

# Small Dot (Tile 1)
items_bitmap[TILE_SIZE__2 - 1, TILE_SIZE + TILE_SIZE__2 - 1] = 1
items_bitmap[TILE_SIZE__2, TILE_SIZE + TILE_SIZE__2 - 1] = 1
items_bitmap[TILE_SIZE__2 - 1, TILE_SIZE + TILE_SIZE__2] = 1
items_bitmap[TILE_SIZE__2, TILE_SIZE + TILE_SIZE__2] = 1

# Power Pellet (Tile 2)
for x in range(1, TILE_SIZE - 1):
    for y in range(TILE_SIZE_X_2 + 1, TILE_SIZE * 3 - 1):
        if x in (1, TILE_SIZE - 2) and y in (TILE_SIZE_X_2 + 1, TILE_SIZE * 3 - 2):
            continue
        items_bitmap[x, y] = 2

items_palette = displayio.Palette(3)
items_palette[0] = 0x000000
items_palette[1] = 0xFFB8AE
items_palette[2] = 0xFFB8AE
items_palette.make_transparent(0)

items_grid = displayio.TileGrid(
    items_bitmap,
    pixel_shader=items_palette,
    width=MAZE_COLS,
    height=MAZE_ROWS,
    tile_width=TILE_SIZE,
    tile_height=TILE_SIZE,
    x=0,
    y=0,
)

# Flood fill reachable tiles
reachable = set()
queue = [(14, 23)]
reachable.add((14, 23))
while queue:
    cx, cy = queue.pop(0)
    for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
        nx, ny = cx + dx, cy + dy
        if 0 <= nx < MAZE_COLS and 0 <= ny < MAZE_ROWS:
            if MAZE_DATA[ny][nx] != WALL and (nx, ny) not in reachable:
                reachable.add((nx, ny))
                queue.append((nx, ny))


def reset_dots():
    """Reset all dots."""
    global dots_eaten
    dots_eaten = 0
    for y in range(MAZE_ROWS):
        for x in range(MAZE_COLS):
            if MAZE_DATA[y][x] == 0 and (x, y) in reachable:
                is_ghost_area = (7 <= x <= 20) and (9 <= y <= 19)
                is_player_area = (y == 23) and (13 <= x <= 14)
                is_tunnel = (y == 14) and (x < 6 or x > 21)

                if (x, y) in POWER_PELLETS:
                    items_grid[x, y] = 2
                elif not is_ghost_area and not is_player_area and not is_tunnel:
                    items_grid[x, y] = 1
                else:
                    items_grid[x, y] = 0
            else:
                items_grid[x, y] = 0


reset_dots()
game_group.append(items_grid)

# Count total dots
TOTAL_DOTS = sum(
    1 for y in range(MAZE_ROWS) for x in range(MAZE_COLS) if items_grid[x, y] in (1, 2)
)
print(f"Total dots: {TOTAL_DOTS}")

# Power pellet covers for blinking
cover_bmp = displayio.Bitmap(TILE_SIZE, TILE_SIZE, 1)
cover_palette = displayio.Palette(1)
cover_palette[0] = 0x000000

pellet_covers = []
for tx, ty in POWER_PELLETS:
    tg = displayio.TileGrid(
        cover_bmp, pixel_shader=cover_palette, x=tx * TILE_SIZE, y=ty * TILE_SIZE
    )
    tg.hidden = True
    game_group.append(tg)
    pellet_covers.append(tg)

# =============================================================================
# LOAD SPRITE SHEET
# =============================================================================

_sprite_sheet, sprite_palette = adafruit_imageload.load("images/sprites.bmp")
if TILE_SIZE != 8:
    sprite_sheet = displayio.Bitmap(GAME_WIDTH, GAME_HEIGHT, 2 ** _sprite_sheet.bits_per_value)
    bitmaptools.rotozoom(sprite_sheet, _sprite_sheet, scale = TILE_SIZE / 8)
else:
    sprite_sheet = _sprite_sheet

sprite_palette.make_transparent(0)

gc.collect()

# =============================================================================
# PAC-MAN CLASS
# =============================================================================


class PacMan:
    """Pac-Man player character."""

    # TILE_SIZE = 8: 0, 8, 16, 24, 32, 40, 48   Faster than doing the math each time
    _dir = [(i * TILE_SIZE) for i in range(7)]
    _dir.append(16 * TILE_SIZE)

    FRAMES = {
        DIR_RIGHT: [(0, 0), (_dir[2], 0), (_dir[4], 0)],
        DIR_LEFT: [(0, _dir[4]), (_dir[2], _dir[2]), (_dir[4], 0)],
        DIR_UP: [(0, _dir[4]), (_dir[2], _dir[4]), (_dir[4], 0)],
        DIR_DOWN: [(0, _dir[6]), (_dir[2], _dir[6]), (_dir[4], 0)],
    }

    #DEATH_FRAMES = [(_dir[6] + i * _dir[2], 0) for i in range(11)]
    DEATH_FRAMES = [((TILE_SIZE * 6) + i * TILE_SIZE_X_2, 0) for i in range(11)]
    SCORE_FRAMES = [(0, _dir[7]), (_dir[2], _dir[7]), (_dir[4], _dir[7]), (_dir[6], _dir[7])]

    def __init__(self):
        self.sprite = displayio.TileGrid(
            sprite_sheet,
            pixel_shader=sprite_palette,
            width=1,
            height=2,
            tile_width=TILE_SIZE_X_2,
            tile_height=TILE_SIZE,
        )
        self.reset()

    def reset(self):
        self.tile_x = 14
        self.tile_y = 23
        self.x = self.tile_x * TILE_SIZE - TILE_SIZE__2
        self.y = self.tile_y * TILE_SIZE - TILE_SIZE__2
        self.direction = DIR_NONE
        self.next_direction = DIR_NONE
        self.anim_frame = 0
        self.anim_timer = 0
        self.saved_x = 0
        self.saved_y = 0
        self.set_frame(DIR_RIGHT, 0)
        self.update_sprite_pos()

    def set_frame(self, direction, frame_idx):
        if direction == DIR_NONE:
            direction = DIR_RIGHT
        frames = self.FRAMES.get(direction, self.FRAMES[DIR_RIGHT])
        fx, fy = frames[frame_idx % 3]
        tiles_per_row = sprite_sheet.width // TILE_SIZE_X_2
        base_tile = (fy // TILE_SIZE) * tiles_per_row + (fx // TILE_SIZE_X_2)
        self.sprite[0, 0] = base_tile
        self.sprite[0, 1] = base_tile + tiles_per_row

    def set_death_frame(self, frame_idx):
        if frame_idx >= len(self.DEATH_FRAMES):
            frame_idx = len(self.DEATH_FRAMES) - 1
        fx, fy = self.DEATH_FRAMES[frame_idx]
        tiles_per_row = sprite_sheet.width // TILE_SIZE_X_2
        base_tile = (fy // TILE_SIZE) * tiles_per_row + (fx // TILE_SIZE_X_2)
        self.sprite[0, 0] = base_tile
        self.sprite[0, 1] = base_tile + tiles_per_row

    def set_score_frame(self, score_idx):
        if score_idx >= len(self.SCORE_FRAMES):
            score_idx = len(self.SCORE_FRAMES) - 1
        fx, fy = self.SCORE_FRAMES[score_idx]
        tiles_per_row = sprite_sheet.width // TILE_SIZE_X_2
        base_tile = (fy // TILE_SIZE) * tiles_per_row + (fx // TILE_SIZE_X_2)
        self.sprite[0, 0] = base_tile
        self.sprite[0, 1] = base_tile + tiles_per_row

    def update_sprite_pos(self):
        self.sprite.x = int(self.x)
        self.sprite.y = int(self.y)

    def can_move(self, direction):
        next_x, next_y = self.x, self.y
        if direction == DIR_UP:
            next_y -= PACMAN_SPEED
        elif direction == DIR_DOWN:
            next_y += PACMAN_SPEED
        elif direction == DIR_LEFT:
            next_x -= PACMAN_SPEED
        elif direction == DIR_RIGHT:
            next_x += PACMAN_SPEED
        else:
            print(
                f"Checked if could move in None? {direction} direction - Returned False!"
            )
            return False

        center_x = next_x + TILE_SIZE
        center_y = next_y + TILE_SIZE

        if center_x < 8 or center_x > (GAME_WIDTH - TILE_SIZE):
            if direction in (DIR_UP, DIR_DOWN):
                print(
                    "Tried to move up or down but center is too far left or right - Returned False"
                )
                return False

        if next_x < -TILE_SIZE or next_x >= (GAME_WIDTH - TILE_SIZE):
            # Using teleport tunnel
            return True

        SENSOR_OFFSET = 3
        if direction == DIR_UP:
            check_x, check_y = center_x, center_y - SENSOR_OFFSET
        elif direction == DIR_DOWN:
            check_x, check_y = center_x, center_y + SENSOR_OFFSET
        elif direction == DIR_LEFT:
            check_x, check_y = center_x - SENSOR_OFFSET, center_y
        elif direction == DIR_RIGHT:
            check_x, check_y = center_x + SENSOR_OFFSET, center_y

        tx = int(check_x // TILE_SIZE)
        ty = int(check_y // TILE_SIZE)

        # print(f"CAN_MOVE: x,y: {self.x},{self.y} next_x,y: {next_x},{next_y}
        #   check_x,y: {check_x},{check_y} tx,ty: {tx},{ty}")
        if tx < 0 or tx >= MAZE_COLS:
            return ty == 14
        if ty < 0 or ty >= MAZE_ROWS:
            return False
        if ty == 12 and tx in (13, 14):
            return False

        return MAZE_DATA[ty][tx] != WALL

    def can_turn(self, direction):
        target_tx, target_ty = int(self.tile_x), int(self.tile_y)
        if direction == DIR_UP:
            target_ty -= 1
        elif direction == DIR_DOWN:
            target_ty += 1
        elif direction == DIR_LEFT:
            target_tx -= 1
        elif direction == DIR_RIGHT:
            target_tx += 1

        if target_tx < 0 or target_tx >= MAZE_COLS:
            return target_ty == 14
        if target_ty < 0 or target_ty >= MAZE_ROWS:
            return False
        if target_ty == 12 and target_tx in (13, 14):
            return False

        return MAZE_DATA[target_ty][target_tx] != WALL

    def at_tile_center(self):
        center_x = self.x + TILE_SIZE
        center_y = self.y + TILE_SIZE
        dist_x = abs((center_x - TILE_SIZE__2) % TILE_SIZE)
        dist_y = abs((center_y - TILE_SIZE__2) % TILE_SIZE)
        dist_x = min(dist_x, TILE_SIZE - dist_x)
        dist_y = min(dist_y, TILE_SIZE - dist_y)
        return dist_x <= PACMAN_SPEED and dist_y <= PACMAN_SPEED

    def is_opposite(self, dir1, dir2):
        return (
            (dir1 == DIR_UP and dir2 == DIR_DOWN)
            or (dir1 == DIR_DOWN and dir2 == DIR_UP)
            or (dir1 == DIR_LEFT and dir2 == DIR_RIGHT)
            or (dir1 == DIR_RIGHT and dir2 == DIR_LEFT)
        )

    def update(self):
        # Handle reversals
        if self.next_direction != DIR_NONE and self.is_opposite(
            self.direction, self.next_direction
        ):
            if self.can_move(self.next_direction):
                self.direction = self.next_direction
                self.next_direction = DIR_NONE

        # Start from stop
        elif self.direction == DIR_NONE and self.next_direction != DIR_NONE:
            if self.can_move(self.next_direction):
                self.direction = self.next_direction
                self.next_direction = DIR_NONE

        # Handle turns at intersections
        elif self.at_tile_center():
            if (
                self.next_direction != DIR_NONE
                and self.next_direction != self.direction
            ):
                if self.can_turn(self.next_direction):
                    center_x = self.x + TILE_SIZE
                    center_y = self.y + TILE_SIZE
                    tile_x = int(center_x // TILE_SIZE)
                    tile_y = int(center_y // TILE_SIZE)
                    self.x = tile_x * TILE_SIZE + TILE_SIZE__2 - TILE_SIZE
                    self.y = tile_y * TILE_SIZE + TILE_SIZE__2 - TILE_SIZE
                    self.direction = self.next_direction
                    self.next_direction = DIR_NONE

            if self.direction != DIR_NONE and not self.can_move(self.direction):
                center_x = self.x + TILE_SIZE
                center_y = self.y + TILE_SIZE
                tile_x = int(center_x // TILE_SIZE)
                tile_y = int(center_y // TILE_SIZE)
                self.x = tile_x * TILE_SIZE + TILE_SIZE__2 - TILE_SIZE
                self.y = tile_y * TILE_SIZE + TILE_SIZE__2 - TILE_SIZE
                self.direction = DIR_NONE

        # Move
        if self.direction != DIR_NONE:
            if self.can_move(self.direction):
                if self.direction == DIR_UP:
                    self.y -= PACMAN_SPEED
                elif self.direction == DIR_DOWN:
                    self.y += PACMAN_SPEED
                elif self.direction == DIR_LEFT:
                    self.x -= PACMAN_SPEED
                elif self.direction == DIR_RIGHT:
                    self.x += PACMAN_SPEED

                if self.x < -TILE_SIZE_X_2:
                    self.x = GAME_WIDTH
                elif self.x >= GAME_WIDTH:
                    self.x = -TILE_SIZE_X_2

                self.anim_timer += 1
                if self.anim_timer >= 3:
                    self.anim_timer = 0
                    self.anim_frame = (self.anim_frame + 1) % 3
                    self.set_frame(self.direction, self.anim_frame)

        self.tile_x = int((self.x + TILE_SIZE) // TILE_SIZE)
        self.tile_y = int((self.y + TILE_SIZE) // TILE_SIZE)
        self.update_sprite_pos()


# =============================================================================
# GHOST CLASS
# =============================================================================


class Ghost:
    """Ghost enemy character."""

    TYPE_BLINKY = 8 * TILE_SIZE
    TYPE_PINKY = 10 * TILE_SIZE
    TYPE_INKY = 12 * TILE_SIZE
    TYPE_CLYDE = 14 * TILE_SIZE

    def __init__(self, ghost_type, start_tile_x, start_tile_y, x_offset=0):
        self.ghost_type = ghost_type
        self.start_params = (start_tile_x, start_tile_y, x_offset)

        self.sprite = displayio.TileGrid(
            sprite_sheet,
            pixel_shader=sprite_palette,
            width=1,
            height=2,
            tile_width=TILE_SIZE_X_2,
            tile_height=TILE_SIZE,
        )

        self.tile_x = start_tile_x
        self.tile_y = start_tile_y
        self.x = self.tile_x * TILE_SIZE - TILE_SIZE__2 + x_offset
        self.y = self.tile_y * TILE_SIZE - TILE_SIZE__2

        self.direction = DIR_LEFT
        self.next_direction = DIR_NONE

        self.in_house = ghost_type != Ghost.TYPE_BLINKY
        self.house_timer = 0
        if self.in_house:
            self.direction = DIR_DOWN if ghost_type == Ghost.TYPE_PINKY else DIR_UP

        self.anim_frame = 0
        self.anim_timer = 0
        self.mode = MODE_SCATTER
        self.reverse_pending = False
        self.frightened_timer = 0

        # Scatter targets
        if ghost_type == Ghost.TYPE_BLINKY:
            self.scatter_target = (25, -3)
        elif ghost_type == Ghost.TYPE_PINKY:
            self.scatter_target = (2, -3)
        elif ghost_type == Ghost.TYPE_INKY:
            self.scatter_target = (27, 31)
        else:
            self.scatter_target = (0, 31)

        self.set_frame(self.direction, 0)
        self.update_sprite_pos()

    def set_frame(self, direction, frame_idx):
        base_y = self.ghost_type
        base_x = 0

        if self.mode == MODE_FRIGHTENED:
            base_y = 8 * TILE_SIZE
            if (
                self.frightened_timer > (FRIGHTENED_DURATION - 120)
                and (self.frightened_timer // 10) % 2 == 0
            ):
                base_x = 20 * TILE_SIZE
            else:
                base_x = 16 * TILE_SIZE
            base_x += (frame_idx % 2) * TILE_SIZE_X_2
        elif self.mode == MODE_EATEN:
            base_y = 10 * TILE_SIZE
            if direction == DIR_RIGHT:
                base_x = 16 * TILE_SIZE
            elif direction == DIR_LEFT:
                base_x = 18 * TILE_SIZE
            elif direction == DIR_UP:
                base_x = 20 * TILE_SIZE
            else:
                base_x = 22 * TILE_SIZE
        else:
            if direction == DIR_RIGHT:
                base_x = 0
            elif direction == DIR_LEFT:
                base_x = 4 * TILE_SIZE
            elif direction == DIR_UP:
                base_x = 8 * TILE_SIZE
            else:
                base_x = 12 * TILE_SIZE
            base_x += (frame_idx % 2) * TILE_SIZE_X_2

        tiles_per_row = sprite_sheet.width // TILE_SIZE_X_2
        base_tile = (base_y // TILE_SIZE) * tiles_per_row + (base_x // TILE_SIZE_X_2)
        self.sprite[0, 0] = base_tile
        self.sprite[0, 1] = base_tile + tiles_per_row

    def update_sprite_pos(self):
        self.sprite.x = int(self.x)
        self.sprite.y = int(self.y)

    def can_move(self, direction):
        next_x, next_y = self.x, self.y
        speed = GHOST_SPEED if self.mode != MODE_EATEN else 2.0

        if direction == DIR_UP:
            next_y -= speed
        elif direction == DIR_DOWN:
            next_y += speed
        elif direction == DIR_LEFT:
            next_x -= speed
        elif direction == DIR_RIGHT:
            next_x += speed
        else:
            return False

        center_x = next_x + TILE_SIZE
        center_y = next_y + TILE_SIZE

        if center_x < TILE_SIZE or center_x > GAME_WIDTH - TILE_SIZE:
            if direction in (DIR_UP, DIR_DOWN):
                return False

        if next_x < -8 or next_x >= GAME_WIDTH - TILE_SIZE:
            return True

        SENSOR_OFFSET = TILE_SIZE__2 - 1
        if direction == DIR_UP:
            check_x, check_y = center_x, center_y - SENSOR_OFFSET
        elif direction == DIR_DOWN:
            check_x, check_y = center_x, center_y + SENSOR_OFFSET
        elif direction == DIR_LEFT:
            check_x, check_y = center_x - SENSOR_OFFSET, center_y
        else:
            check_x, check_y = center_x + SENSOR_OFFSET, center_y

        tx = int(check_x // TILE_SIZE)
        ty = int(check_y // TILE_SIZE)

        if tx < 0 or tx >= MAZE_COLS:
            return ty == 14
        if ty < 0 or ty >= MAZE_ROWS:
            return False

        if self.mode == MODE_EATEN and 11 <= ty <= 15 and 10 <= tx <= 17:
            return True

        if direction == DIR_DOWN and ty == 12 and tx in (13, 14):
            if not self.in_house and self.mode != MODE_EATEN:
                return False

        return MAZE_DATA[ty][tx] != WALL

    def at_tile_center(self):
        center_x = self.x + TILE_SIZE
        center_y = self.y + TILE_SIZE
        dist_x = min(
            abs((center_x - TILE_SIZE__2) % TILE_SIZE),
            TILE_SIZE - abs((center_x - TILE_SIZE__2) % TILE_SIZE)
        )
        dist_y = min(
            abs((center_y - TILE_SIZE__2) % TILE_SIZE),
            TILE_SIZE - abs((center_y - TILE_SIZE__2) % TILE_SIZE)
        )
        threshold = 1.5 * TILE_SIZE / 8 if self.mode == MODE_EATEN else 0.7 * TILE_SIZE / 8
        return dist_x <= threshold and dist_y <= threshold

    def get_chase_target(self, pacman, ghosts):
        px, py = pacman.tile_x, pacman.tile_y
        pd = pacman.direction

        if self.ghost_type == Ghost.TYPE_BLINKY:
            return (px, py)
        if self.ghost_type == Ghost.TYPE_PINKY:
            tx, ty = px, py
            if pd == DIR_UP:
                ty -= 4
                tx -= 4
            elif pd == DIR_DOWN:
                ty += 4
            elif pd == DIR_LEFT:
                tx -= 4
            elif pd == DIR_RIGHT:
                tx += 4
            return (tx, ty)
        elif self.ghost_type == Ghost.TYPE_INKY:
            tx, ty = px, py
            if pd == DIR_UP:
                ty -= 2
                tx -= 2
            elif pd == DIR_DOWN:
                ty += 2
            elif pd == DIR_LEFT:
                tx -= 2
            elif pd == DIR_RIGHT:
                tx += 2
            bx, by = 0, 0
            for g in ghosts:
                if g.ghost_type == Ghost.TYPE_BLINKY:
                    bx, by = g.tile_x, g.tile_y
                    break
            return (bx + (tx - bx) * 2, by + (ty - by) * 2)
        else:  # Clyde
            dist = (self.tile_x - px) ** 2 + (self.tile_y - py) ** 2
            return (px, py) if dist > 64 else self.scatter_target

    def update(self, pacman, ghosts, current_mode):
        if self.in_house:
            self.house_timer += 1
            should_exit = False

            if self.ghost_type == Ghost.TYPE_BLINKY:
                should_exit = self.house_timer > 60
            elif self.ghost_type == Ghost.TYPE_PINKY:
                should_exit = True
            elif self.ghost_type == Ghost.TYPE_INKY:
                should_exit = self.house_timer > 300
            elif self.ghost_type == Ghost.TYPE_CLYDE:
                should_exit = self.house_timer > 600

            if should_exit:
                target_x = 13 * TILE_SIZE
                target_y = 11 * TILE_SIZE - TILE_SIZE__2

                if abs(self.x - target_x) >= GHOST_SPEED:
                    self.x += GHOST_SPEED if self.x < target_x else -GHOST_SPEED
                    self.direction = DIR_RIGHT if self.x < target_x else DIR_LEFT
                else:
                    self.x = target_x
                    self.y -= GHOST_SPEED
                    self.direction = DIR_UP
                    if self.y <= target_y:
                        self.y = target_y
                        self.in_house = False
                        self.direction = DIR_LEFT
            else:
                center_y = 14 * TILE_SIZE - TILE_SIZE__2
                if self.direction == DIR_UP:
                    self.y -= GHOST_SPEED / 2
                    if self.y < center_y - (TILE_SIZE__2 - 1):
                        self.direction = DIR_DOWN
                else:
                    self.y += GHOST_SPEED / 2
                    if self.y > center_y + (TILE_SIZE__2 - 1):
                        self.direction = DIR_UP

            self.anim_timer += 1
            if self.anim_timer >= 10:
                self.anim_timer = 0
                self.anim_frame = (self.anim_frame + 1) % 2
                self.set_frame(self.direction, self.anim_frame)
            self.update_sprite_pos()
            return

        if self.reverse_pending:
            self.reverse_pending = False
            rev = {
                DIR_UP: DIR_DOWN,
                DIR_DOWN: DIR_UP,
                DIR_LEFT: DIR_RIGHT,
                DIR_RIGHT: DIR_LEFT,
            }.get(self.direction, DIR_NONE)
            if self.can_move(rev):
                self.direction = rev
                center_x, center_y = self.x + TILE_SIZE, self.y + TILE_SIZE
                self.x = (center_x // TILE_SIZE) * TILE_SIZE + TILE_SIZE__2 - TILE_SIZE
                self.y = (center_y // TILE_SIZE) * TILE_SIZE + TILE_SIZE__2 - TILE_SIZE
                return

        if self.at_tile_center():
            tx, ty = 0, 0
            if self.mode == MODE_CHASE:
                tx, ty = self.get_chase_target(pacman, ghosts)
            elif self.mode == MODE_SCATTER:
                tx, ty = self.scatter_target
            elif self.mode == MODE_EATEN:
                tx, ty = 13, 11
                if self.tile_y in (11, 12, 13) and self.tile_x in (13, 14):
                    tx, ty = 13, self.tile_y + 3
                if self.tile_y >= 14 and self.tile_x in (13, 14):
                    self.mode = current_mode
                    self.in_house = True
                    self.house_timer = 0
                    self.direction = DIR_UP
                    self.x = 13 * TILE_SIZE
                    self.y = 14 * TILE_SIZE - TILE_SIZE__2
                    self.update_sprite_pos()
                    return

            best_dist = 999999
            best_dir = self.direction
            valid_dirs = []

            for d in [DIR_UP, DIR_LEFT, DIR_DOWN, DIR_RIGHT]:
                if (
                    (d == DIR_UP and self.direction == DIR_DOWN)
                    or (d == DIR_DOWN and self.direction == DIR_UP)
                    or (d == DIR_LEFT and self.direction == DIR_RIGHT)
                    or (d == DIR_RIGHT and self.direction == DIR_LEFT)
                ):
                    continue

                nx, ny = int(self.tile_x), int(self.tile_y)
                if d == DIR_UP:
                    ny -= 1
                elif d == DIR_DOWN:
                    ny += 1
                elif d == DIR_LEFT:
                    nx -= 1
                elif d == DIR_RIGHT:
                    nx += 1

                is_valid = False
                if 0 <= nx < MAZE_COLS and 0 <= ny < MAZE_ROWS:
                    if MAZE_DATA[ny][nx] != WALL:
                        is_valid = True
                        if d == DIR_DOWN and ny == 12 and nx in (13, 14):
                            if not self.in_house and self.mode != MODE_EATEN:
                                is_valid = False
                elif ny == 14:
                    is_valid = True

                if is_valid:
                    valid_dirs.append(d)
                    if self.mode != MODE_FRIGHTENED:
                        dist = (nx - tx) ** 2 + (ny - ty) ** 2
                        if dist < best_dist:
                            best_dist = dist
                            best_dir = d

            if self.mode == MODE_FRIGHTENED:
                if valid_dirs:
                    self.direction = random.choice(valid_dirs)
            elif (
                self.mode == MODE_EATEN
                and self.tile_y in (11, 12)
                and self.tile_x in (13, 14)
            ):
                self.direction = DIR_DOWN
            else:
                self.direction = best_dir

            center_x, center_y = self.x + TILE_SIZE, self.y + TILE_SIZE
            self.x = (center_x // TILE_SIZE) * TILE_SIZE + TILE_SIZE__2 - TILE_SIZE
            self.y = (center_y // TILE_SIZE) * TILE_SIZE + TILE_SIZE__2 - TILE_SIZE

        if self.direction != DIR_NONE:
            speed = GHOST_SPEED
            if self.mode == MODE_FRIGHTENED:
                speed *= 0.6
            elif self.mode == MODE_EATEN:
                speed = 2.0

            if self.can_move(self.direction):
                if self.direction == DIR_UP:
                    self.y -= speed
                elif self.direction == DIR_DOWN:
                    self.y += speed
                elif self.direction == DIR_LEFT:
                    self.x -= speed
                elif self.direction == DIR_RIGHT:
                    self.x += speed

                if self.x < -TILE_SIZE_X_2:
                    self.x = GAME_WIDTH
                elif self.x >= GAME_WIDTH:
                    self.x = -TILE_SIZE_X_2

                self.anim_timer += 1
                if self.anim_timer >= 10:
                    self.anim_timer = 0
                    self.anim_frame = (self.anim_frame + 1) % 2
                    self.set_frame(self.direction, self.anim_frame)

        self.tile_x = int((self.x + TILE_SIZE) // TILE_SIZE)
        self.tile_y = int((self.y + TILE_SIZE) // TILE_SIZE)
        self.update_sprite_pos()

    def reset(self):
        start_tile_x, start_tile_y, x_offset = self.start_params
        self.tile_x = start_tile_x
        self.tile_y = start_tile_y
        self.x = self.tile_x * TILE_SIZE - TILE_SIZE__2 + x_offset
        self.y = self.tile_y * TILE_SIZE - TILE_SIZE__2
        self.direction = DIR_LEFT
        self.in_house = self.ghost_type != Ghost.TYPE_BLINKY
        self.house_timer = 0
        if self.in_house:
            self.direction = DIR_DOWN if self.ghost_type == Ghost.TYPE_PINKY else DIR_UP
        self.anim_frame = 0
        self.anim_timer = 0
        self.mode = MODE_SCATTER
        self.reverse_pending = False
        self.frightened_timer = 0
        self.set_frame(self.direction, 0)
        self.update_sprite_pos()


# =============================================================================
# CREATE GAME OBJECTS
# =============================================================================

pacman = PacMan()
game_group.append(pacman.sprite)

ghosts = []
spawn_points = [
    (13, 11, 0),  # Blinky
    (13, 14, 4),  # Pinky
    (11, 14, 4),  # Inky
    (15, 14, 4),  # Clyde
]

for i, (gx, gy, x_off) in enumerate(spawn_points):
    ghost_type = [
        Ghost.TYPE_BLINKY,
        Ghost.TYPE_PINKY,
        Ghost.TYPE_INKY,
        Ghost.TYPE_CLYDE,
    ][i]
    ghost = Ghost(ghost_type, gx, gy, x_off)
    ghosts.append(ghost)
    game_group.append(ghost.sprite)


# Bonus fruit
def get_tile_index(px, py):
    tiles_per_row = sprite_sheet.width // TILE_SIZE_X_2
    return (py // TILE_SIZE) * tiles_per_row + (px // TILE_SIZE_X_2)


bonus_fruit = displayio.TileGrid(
    sprite_sheet,
    pixel_shader=sprite_palette,
    width=1,
    height=2,
    tile_width=TILE_SIZE_X_2,
    tile_height=TILE_SIZE,
)
bonus_fruit.x = 13 * TILE_SIZE
bonus_fruit.y = 17 * TILE_SIZE - TILE_SIZE__2
bonus_fruit.hidden = True
game_group.append(bonus_fruit)

# Life sprites (on left panel)
life_sprites = []
for i in range(5):
    life_tg = displayio.TileGrid(
        sprite_sheet,
        pixel_shader=sprite_palette,
        width=1,
        height=2,
        tile_width=TILE_SIZE_X_2,
        tile_height=TILE_SIZE,
    )
    if DISPLAY_VERTICAL:
        # Position at bottom left, spaced 16 pixels apart
        life_tg.x = (OFFSET_X + (3 * TILE_SIZE) + (i * TILE_SIZE_X_2)) // SCORE_SCALE
        life_tg.y = (OFFSET_Y + GAME_HEIGHT * GAME_SCALE + TILE_SIZE__2) // SCORE_SCALE  # Below game area
    else:
        life_tg.x = TILE_SIZE_X_2 + 4 + (i * int(0.06 * DISPLAY_WIDTH / SCORE_SCALE))
        life_tg.y = int(0.83 * DISPLAY_HEIGHT / SCORE_SCALE)
    base_tile = get_tile_index(SPRITE_LIFE[0], SPRITE_LIFE[1])
    tiles_per_row = sprite_sheet.width // TILE_SIZE_X_2
    life_tg[0, 0] = base_tile
    life_tg[0, 1] = base_tile + tiles_per_row
    life_tg.hidden = True
    life_sprites.append(life_tg)
    score_group.append(life_tg)

# Add game group to main
main_group.append(game_group)

gc.collect()

# =============================================================================
# UI LABELS
# =============================================================================

score_label = None
high_score_label = None
one_up_label = None
level_label = None
game_over_label = None
ready_label = None

try:
    if bitmap_font and label:
        font = bitmap_font.load_font("fonts/press_start_2p.bdf")

        one_up_label = label.Label(
            font, text="1UP", color=0xFFFFFF,
        )

        score_label = label.Label(
            font, text="0", color=0xFFFFFF,
        )

        hs_title = label.Label(
            font, text="HIGH SCORE", color=0xFFFFFF,
        )
        high_score_label = label.Label(
            font, text="0", color=0xFFFFFF,
        )

        level_label = label.Label(
            font, text="LVL 1", color=0xFFFF00,
        )

        if DISPLAY_VERTICAL:
            one_up_label.x, one_up_label.y = 8, 8  # top left
            score_label.x, score_label.y = 8, 24  # below 1UP
            hs_title.anchor_point = (0.5, 0.0)
            hs_title.anchored_position = (DISPLAY_WIDTH // SCORE_SCALE // 2, 8)  # top center
            high_score_label.anchor_point = (0.5, 0.0)
            high_score_label.anchored_position = (DISPLAY_WIDTH // SCORE_SCALE // 2, 24)  # below title

            if DISPLAY_WIDTH < 240:
                level_label.anchor_point = (0.5, 0.0)
                level_label.anchored_position = (DISPLAY_WIDTH // SCORE_SCALE // 2, 40)  # below high score
            else:
                level_label.anchor_point = (1.0, 0.0)
                level_label.anchored_position = (DISPLAY_WIDTH // SCORE_SCALE - 8, 8)  # top right
            
        else:
            one_up_label.x, one_up_label.y = TILE_SIZE_X_2 + 4, int(0.1 * DISPLAY_HEIGHT / SCORE_SCALE)
            score_label.x, score_label.y = TILE_SIZE_X_2 + 4, int(0.17 * DISPLAY_HEIGHT / SCORE_SCALE)
            high_score_label.x, high_score_label.y = TILE_SIZE_X_2 + 4, int(0.43 * DISPLAY_HEIGHT / SCORE_SCALE)
            level_label.x, level_label.y = TILE_SIZE_X_2 + 4, int(0.58 * DISPLAY_HEIGHT / SCORE_SCALE)

            hs_title.text = "HIGH"
            hs_title.x, hs_title.y = TILE_SIZE_X_2 + 4, int(0.31 * DISPLAY_HEIGHT / SCORE_SCALE)

            hs_title2 = label.Label(
                font, text="SCORE", color=0xFFFFFF,
            )
            hs_title2.x, hs_title2.y = TILE_SIZE_X_2 + 4, int(0.36 * DISPLAY_HEIGHT / SCORE_SCALE)

        game_over_label = label.Label(font, text="GAME OVER", color=0xFF0000)
        game_over_label.anchor_point = (0.5, 0.5)
        game_over_label.anchored_position = (
            OFFSET_X + int(MAZE_COLS * TILE_SIZE * GAME_SCALE / 2),
            OFFSET_Y + int(17.5 * TILE_SIZE * GAME_SCALE)
        )
        game_over_label.hidden = True

        ready_label = label.Label(font, text="READY!", color=0xFFFF00)
        ready_label.anchor_point = (0.5, 0.5)
        ready_label.anchored_position = game_over_label.anchored_position
        ready_label.hidden = True
        
        score_group.append(one_up_label)
        score_group.append(score_label)
        score_group.append(hs_title)
        if not DISPLAY_VERTICAL:
            score_group.append(hs_title2)
        score_group.append(high_score_label)
        score_group.append(level_label)

        main_group.append(game_over_label)
        main_group.append(ready_label)
except Exception as e:
    print(f"Label error: {e}")

# =============================================================================
# INITIALIZE SYSTEMS
# =============================================================================

# create gamepad object
gamepad = relic_usb_host_gamepad.Gamepad(debug=False)
gamepad.joystick_threshold = 0.8

sound = SoundEngine()
high_scores = HighScoreManager()

# Game state
score = 0
lives = 3
level = 1
dots_eaten = 0
game_state = STATE_READY
current_mode = MODE_SCATTER
mode_index = 0
last_mode_time = 0
ghosts_eaten_count = 0
bonus_fruit_active = False
bonus_fruit_timer = 0

# Timers
death_timer = 0
death_frame_idx = 0
eat_timer = 0
eaten_ghost_ref = None
level_complete_timer = 0
blink_timer = 0
blink_state = True
ready_timer = 0


def update_life_display():
    for i, sprite in enumerate(life_sprites):
        sprite.hidden = i >= lives - 1


def update_fruit_sprite():
    fruit_idx = min(level - 1, len(FRUIT_LEVELS) - 1)
    fx, fy = FRUIT_LEVELS[fruit_idx]
    base_tile = get_tile_index(fx, fy)
    tiles_per_row = sprite_sheet.width // TILE_SIZE_X_2
    bonus_fruit[0, 0] = base_tile
    bonus_fruit[0, 1] = base_tile + tiles_per_row


def reset_game():
    global score, lives, level, dots_eaten, game_state, current_mode
    global mode_index, ghosts_eaten_count, bonus_fruit_active

    score = 0
    lives = 3
    level = 1
    dots_eaten = 0
    current_mode = MODE_SCATTER
    game_state = STATE_READY
    mode_index = 0
    ghosts_eaten_count = 0
    bonus_fruit_active = False
    bonus_fruit.hidden = True

    reset_dots()
    pacman.reset()
    pacman.sprite.hidden = False
    for g in ghosts:
        g.reset()
        g.sprite.hidden = False

    update_life_display()
    update_fruit_sprite()

    if game_over_label:
        game_over_label.hidden = True


update_life_display()
update_fruit_sprite()

if high_score_label:
    high_score_label.text = str(high_scores.get_high_score())

print(f"Free memory: {gc.mem_free()}")

# Play startup
sound.play_startup()
game_state = STATE_READY
ready_timer = 0
if ready_label:
    ready_label.hidden = False

# =============================================================================
# MAIN GAME LOOP
# =============================================================================

# Flush stdin input buffer
while supervisor.runtime.serial_bytes_available:
    sys.stdin.read(1)

try:
    while True:
        start_time = time.monotonic()

        # Read keyboard input
        keys = []
        if (available := supervisor.runtime.serial_bytes_available) > 0:
            buffer = sys.stdin.read(available)
            while buffer:
                key = buffer[0]
                buffer = buffer[1:]
                if key == "\x1b" and buffer and buffer[0] == "[" and len(buffer) >= 2:
                    key += buffer[:2]
                    buffer = buffer[2:]
                keys.append(key.upper())

        # Update gamepad state
        gamepad.update()

        # Exit game loop
        if "\x1b" in keys or "Q" in keys or gamepad.buttons.HOME:
            break

        # Toggle sound
        if "\n" in keys or "Z" in keys or gamepad.buttons.SELECT:
            sound.toggle()

        # now = time.monotonic()
        # print(f"controller update took: {now - start_time}")
        # prev_time = now

        if game_state == STATE_READY:
            ready_timer += 1
            if ready_timer >= 120:  # ~2 seconds
                game_state = STATE_PLAY
                if ready_label:
                    ready_label.hidden = True
                last_mode_time = time.monotonic()

        elif game_state == STATE_PLAY:
            # play_state_start = time.monotonic()
            # prev_time = None

            # Mode switching
            if mode_index < len(MODE_TIMES):
                if time.monotonic() - last_mode_time > MODE_TIMES[mode_index]:
                    mode_index += 1
                    last_mode_time = time.monotonic()
                    current_mode = (
                        MODE_CHASE if current_mode == MODE_SCATTER else MODE_SCATTER
                    )
                    for g in ghosts:
                        if g.mode not in (MODE_FRIGHTENED, MODE_EATEN):
                            g.mode = current_mode
                            if not g.in_house:
                                g.reverse_pending = True

            # now = time.monotonic()
            # prev_time = now
            # print(f"mode switching took: {now - play_state_start}")

            # Read input
            # Joystick UP/DOWN reversed because of flight simulator bias on Joysticks
            if "\x1b[A" in keys or "W" in keys or gamepad.buttons.UP or gamepad.buttons.JOYSTICK_DOWN:
                pacman.next_direction = DIR_UP
            elif "\x1b[B" in keys or "S" in keys or gamepad.buttons.DOWN or gamepad.buttons.JOYSTICK_UP:
                pacman.next_direction = DIR_DOWN
            elif "\x1b[D" in keys or "A" in keys or gamepad.buttons.LEFT or gamepad.buttons.JOYSTICK_LEFT:
                pacman.next_direction = DIR_LEFT
            elif "\x1b[C" in keys or "D" in keys or gamepad.buttons.RIGHT or gamepad.buttons.JOYSTICK_RIGHT:
                pacman.next_direction = DIR_RIGHT

            # now = time.monotonic()
            # print(f"read input took: {now - prev_time}")
            # prev_time = now

            pacman.update()

            # now = time.monotonic()
            # print(f"pacman update took: {now - prev_time}")
            # prev_time = now

            # Eat dots
            if pacman.at_tile_center():
                sound.stop()
                tx, ty = int(pacman.tile_x), int(pacman.tile_y)
                if 0 <= tx < MAZE_COLS and 0 <= ty < MAZE_ROWS:
                    item = items_grid[tx, ty]
                    if item == 1:
                        items_grid[tx, ty] = 0
                        score += 10
                        dots_eaten += 1
                        sound.play_waka()

                        if dots_eaten in (70, 170):
                            bonus_fruit_active = True
                            bonus_fruit_timer = 0
                            bonus_fruit.hidden = False
                            update_fruit_sprite()

                    elif item == 2:
                        items_grid[tx, ty] = 0
                        score += 50
                        dots_eaten += 1
                        sound.play_waka()
                        ghosts_eaten_count = 0
                        for g in ghosts:
                            if g.mode != MODE_EATEN:
                                g.mode = MODE_FRIGHTENED
                                g.frightened_timer = 0
                                if not g.in_house:
                                    g.reverse_pending = True

            # now = time.monotonic()
            # print(f"eat dots took: {now - prev_time}")
            # prev_time = now

            # Update ghosts
            for ghost in ghosts:
                if ghost.mode == MODE_FRIGHTENED:
                    ghost.frightened_timer += 1
                    if ghost.frightened_timer > FRIGHTENED_DURATION:
                        ghost.mode = current_mode

                ghost.update(pacman, ghosts, current_mode)

                # Collision
                dx = abs((pacman.x + TILE_SIZE) - (ghost.x + TILE_SIZE))
                dy = abs((pacman.y + TILE_SIZE) - (ghost.y + TILE_SIZE))

                if dx < 6 and dy < 6:
                    if ghost.mode == MODE_FRIGHTENED:
                        sound.play_eat_ghost()
                        points = 200 * (2**ghosts_eaten_count)
                        score += points
                        ghosts_eaten_count += 1

                        game_state = STATE_EATING_GHOST
                        eat_timer = 0
                        eaten_ghost_ref = ghost

                        pacman.sprite.hidden = True
                        ghost.sprite.hidden = True

                        pacman.saved_x = pacman.x
                        pacman.saved_y = pacman.y
                        pacman.x = ghost.x
                        pacman.y = ghost.y
                        pacman.update_sprite_pos()
                        pacman.set_score_frame(min(ghosts_eaten_count - 1, 3))
                        pacman.sprite.hidden = False

                        ghost.mode = MODE_EATEN

                    elif ghost.mode != MODE_EATEN:
                        sound.stop()
                        game_state = STATE_DYING
                        death_timer = 0
                        death_frame_idx = 0
                        for g in ghosts:
                            g.sprite.hidden = True
                        time.sleep(1.0)
                        break

            # now = time.monotonic()
            # print(f"update ghosts took: {now - prev_time}")
            # prev_time = now

            # Bonus fruit
            if bonus_fruit_active:
                bonus_fruit_timer += 1
                if bonus_fruit_timer > 500:
                    bonus_fruit_active = False
                    bonus_fruit.hidden = True
                else:
                    fx, fy = 13 * TILE_SIZE, 17 * TILE_SIZE
                    dx = abs((pacman.x + TILE_SIZE) - (fx + TILE_SIZE))
                    dy = abs((pacman.y + TILE_SIZE) - (fy + TILE_SIZE))
                    if dx < TILE_SIZE and dy < TILE_SIZE:
                        fruit_idx = min(level - 1, len(FRUIT_POINTS) - 1)
                        score += FRUIT_POINTS[fruit_idx]
                        sound.play_eat_ghost()
                        bonus_fruit_active = False
                        bonus_fruit.hidden = True

            # now = time.monotonic()
            # print(f"bonus_fruit took: {now - prev_time}")
            # prev_time = now

            # Level complete
            if dots_eaten >= TOTAL_DOTS:
                sound.stop()
                game_state = STATE_LEVEL_COMPLETE
                level_complete_timer = 0

            # now = time.monotonic()
            # print(f"level complete check took: {now - prev_time}")
            # prev_time = now

        elif game_state == STATE_DYING:
            death_timer += 1
            if death_timer >= 8:
                death_timer = 0
                death_frame_idx += 1

                if death_frame_idx < len(PacMan.DEATH_FRAMES):
                    pacman.set_death_frame(death_frame_idx)
                    sound.play_death_note(death_frame_idx)
                else:
                    sound.stop()
                    time.sleep(1.0)
                    lives -= 1
                    update_life_display()

                    if lives <= 0:
                        if high_scores.is_high_score(score):
                            high_scores.add_score(score, "PAC")
                            if high_score_label:
                                high_score_label.text = str(high_scores.get_high_score())

                        if game_over_label:
                            game_over_label.hidden = False
                        pacman.sprite.hidden = True
                        game_state = STATE_GAME_OVER
                    else:
                        pacman.reset()
                        for g in ghosts:
                            g.reset()
                            g.sprite.hidden = False
                        mode_index = 0
                        current_mode = MODE_SCATTER
                        last_mode_time = time.monotonic()
                        game_state = STATE_PLAY

        elif game_state == STATE_EATING_GHOST:
            eat_timer += 1
            if eat_timer >= 60:
                game_state = STATE_PLAY
                pacman.sprite.hidden = False
                pacman.set_frame(pacman.direction, 0)
                pacman.x = pacman.saved_x
                pacman.y = pacman.saved_y
                pacman.update_sprite_pos()
                if eaten_ghost_ref:
                    eaten_ghost_ref.sprite.hidden = False
                    eaten_ghost_ref.set_frame(eaten_ghost_ref.direction, 0)

        elif game_state == STATE_LEVEL_COMPLETE:
            level_complete_timer += 1
            if level_complete_timer % 15 == 0:
                try:
                    maze_palette[1] = (
                        0xFFFFFF if (level_complete_timer // 15) % 2 else 0x2121DE
                    )
                except:
                    pass

            if level_complete_timer >= 180:
                try:
                    maze_palette[1] = 0x2121DE
                except:
                    pass

                level += 1
                dots_eaten = 0
                reset_dots()
                pacman.reset()
                for g in ghosts:
                    g.reset()
                    g.sprite.hidden = False
                bonus_fruit.hidden = True
                bonus_fruit_active = False
                mode_index = 0
                current_mode = MODE_SCATTER
                last_mode_time = time.monotonic()

                if level_label:
                    level_label.text = f"LVL {level}"
                update_fruit_sprite()

                sound.play_startup()
                game_state = STATE_READY
                ready_timer = 0
                if ready_label:
                    ready_label.hidden = False

        elif game_state == STATE_GAME_OVER:
            if " " in keys or gamepad.buttons.START:
                reset_game()
                level_label.text = f"LVL {level}"
                sound.play_startup()
                game_state = STATE_READY
                ready_timer = 0
                if ready_label:
                    ready_label.hidden = False

        # Blink power pellets
        blink_timer += 1
        if blink_timer >= 15:
            blink_timer = 0
            blink_state = not blink_state
            for cover in pellet_covers:
                cover.hidden = blink_state
            if one_up_label:
                one_up_label.hidden = not blink_state

        # now = time.monotonic()
        # print(f"pellete blink took: {now - prev_time}")
        # prev_time = now

        # Update score display
        if score_label:
            score_label.text = str(score) if score > 0 else "00"

        # now = time.monotonic()
        # print(f"update score took: {now - prev_time}")
        # prev_time = now

        # now = time.monotonic()
        # print(f"total frame took: {now - start_time}")
        # prev_time = now

        # Frame timing
        elapsed = time.monotonic() - start_time
        if elapsed < FRAME_DELAY:
            time.sleep(FRAME_DELAY - elapsed)

except KeyboardInterrupt:  # Ctrl+C was pressed
    pass

finally:
    # Clean up
    if high_scores.is_high_score(score):  # save high score
        high_scores.add_score(score, "PAC")
    sound.deinit()  # stop audio and deinit dac
    gamepad.disconnect()  # release usb gamepad resources
    supervisor.reload()  # reload or return to Fruit Jam OS
