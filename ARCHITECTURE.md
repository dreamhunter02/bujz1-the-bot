# bujz1-the-bot

Turning an Espressif ESP-VoCat into an expressive voice agent with a self-hosted
backend and a bridge to Claude Code.

Last updated: 2026-09-10

## Goals

1. Connect the device to a voice agent I control, either hosted or local.
2. Let me issue spoken commands that Claude Code acts on, remotely.
3. Drive the eyes and expressions properly. Today the face stays asleep even
   while the device is talking.

These look like three projects but they are one. All three are downstream of a
single decision: own the backend.

## Hardware

ESP-VoCat v1.2. Verified against the device, not just the datasheet.

| | |
|---|---|
| Module | ESP32-S3-WROOM-1-N16R16VA |
| Flash | 16 MB (GigaDevice, `c8`/`6018`), quad I/O, 1.8 V |
| PSRAM | 16 MB |
| Display | 1.85" round QSPI LCD, 360x360, ST77916 |
| Audio in | Dual mic array, ES7210 4-ch ADC |
| Audio out | ES8311 codec, NS4150B 3 W class-D |
| Motion | BMI270 6-axis IMU |
| Touch | 2 native touch pads (GPIO6, GPIO7) |
| Power | BQ27220 fuel gauge, TP4057 charger |
| Storage | microSD slot, FAT32 only (see below) |
| USB | Native USB (`0x303A`), enumerates as `USB JTAG_serial debug unit` |

Stock firmware is [esp-brookesia](https://github.com/espressif/esp-brookesia)
`release/v0.6`, the `speaker` product, talking to a Coze agent.

## Findings from the factory image

A full 16 MB dump was taken before any modification. Three things came out of it
that shape the whole build.

### 1. The factory partition layout differs from the repo, destructively

The device's table is not the one in `products/speaker/partitions.csv`:

| | device | repo default |
|---|---|---|
| `nvs_key` | 0xf000, 4K | absent |
| `fctry` | **0x10000, 24K** | absent |
| `nvs` | 0x16000, 24K | 0x9000, 16K |
| `model` | 0x1f000, 600K | **0x10000, 600K** |
| `board_test` | 0x890000, 1600K | absent |
| `anim_emotion` | **absent** | 1900K |

The repo's auto-assigned offsets place `model` at 0x10000, exactly where `fctry`
lives. Building the example unmodified and flashing it writes a SPIFFS image over
the factory partition.

`fctry` holds per-device RainMaker credentials, a certificate and private key
burned in at manufacture. They are unique to this unit and cannot be reissued.
Overwriting them permanently removes the device's ability to rejoin RainMaker.

**Rule: never `erase-flash`, never flash a partition table that does not preserve
`fctry` at 0x10000.**

### 2. The device has no emotion animation storage

The factory image has no `anim_emotion` partition. The repo allocates 1900K to
one. This is the most likely explanation for the permanently sleeping face.

### 3. Agent config is loaded from SD at runtime, not compiled in

```c
// products/speaker/main/modules/coze_agent_config.c
#define BASE_PATH         BSP_SD_MOUNT_POINT      // "/sdcard"
#define PRIVATE_KEY_PATH  BASE_PATH "/private_key.pem"
#define BOT_SETTING_PATH  BASE_PATH "/bot_setting.json"
```

`EXAMPLE_COZE_AGENT_ENABLE_DEFAULT_CONFIG` defaults to `n`, so menuconfig is the
fallback and the SD card is the primary configuration path.

Developer Mode (Settings > Developer Mode) sets a magic key in RTC memory,
reboots, and brings the device up as a USB mass-storage drive. Config files are
editable in Finder, then "Exit and reboot". No reflash.

**This pattern should be extended rather than replaced.** Our own backend config
(server URL, auth token, persona, emotion map) belongs in the same file, so
day-to-day tuning is a text edit instead of a build cycle.

## Target architecture

```
ESP-VoCat ──WebSocket (Opus audio)──> our server
                                        │
                                        ├─ STT      (local Whisper, or Deepgram)
                                        │
                                        ├─ router ──┬─ chat ──────> LLM
                                        │           └─ "computer…" > Claude Agent SDK
                                        │                            (headless Claude Code,
                                        │                             scoped to a repo)
                                        ├─ TTS      (local Piper, or ElevenLabs/Cartesia)
                                        │
                                        └─ emotion tag ─────────────> eye animation
```

One server, one WebSocket, all three goals. The device becomes an audio and
display endpoint; every decision worth controlling lives on hardware we own.

## Design decisions

### Keep esp-brookesia, replace the agent layer

Fork `products/speaker` and swap the Coze client for a WebSocket client to our
server. Everything difficult is retained: mic array and sound-source
localization, ES8311/ES7210 audio path, Opus encoding, local wake word, the round
display stack, the animation system.

**Rejected: flashing xiaozhi-esp32.** Its self-hosted server story is more mature
and its server URL is runtime-configurable, but it has no board definition for
VoCat's ST77916 round QSPI panel and dual-codec audio. That trades a contained
backend swap for an open-ended display and audio port on a board that already has
an official, working BSP.

### Goal 1: our own voice agent

The transport is compiled in, so pointing at our own server is a one-time code
change plus reflash. After that, the server URL and credentials move into the
SD config file and never require a rebuild again.

### Goal 2: the Claude bridge

Mechanism is the Claude Agent SDK, running Claude Code headlessly. The server
takes the transcript, opens a session scoped to a working directory, and speaks
the result back.

Design this in from the start, not later. Voice transcription is lossy, and an
agent with shell and filesystem access acting on a misheard sentence is a real
failure mode:

- Scope sessions to specific directories, never the home directory.
- Allowlist the tools that may run without confirmation.
- Require spoken confirmation for anything destructive.
- Log every command and its transcript so mistakes are traceable.

### Goal 3: expressions

No custom animation work needed. `core/brookesia_core/ai_framework/expression`
already provides:

```cpp
bool setEmoji(const std::string &emoji);
bool insertEmojiTemporary(const std::string &emoji, uint32_t duration_ms = 1000);
bool setEmotion(EmotionType type, gui::AnimPlayer::Operation operation, bool immediate);
bool setSystemIcon(const std::string &icon);
```

with an `EmojiMap` of `string -> (EmotionType, IconType)`.

The integration is: server tags each reply with an emotion string, firmware calls
`setEmoji("happy")`. `insertEmojiTemporary` covers momentary reactions such as a
blink or a nod without disturbing the base state.

Goal 3 therefore needs three things, none of them novel: the `anim_emotion`
partition, the assets, and a backend that emits an emotion field.

## Build environment

macOS on Apple Silicon.

ESP-IDF v5.5 cannot build its virtualenv under Python 3.14. Python 3.11 is
required. `idfenv.sh`:

```bash
export PATH="/opt/homebrew/opt/python@3.11/libexec/bin:$PATH"
source ~/esp/esp-idf/export.sh >/dev/null 2>&1
```

IDF's installer did not pull `cmake` or `ninja`. Without them `idf.py` exits 0
while doing nothing, which is a confusing failure:

```bash
python "$IDF_PATH/tools/idf_tools.py" install cmake ninja
```

Build:

```bash
source idfenv.sh
cd esp-brookesia/products/speaker
D="sdkconfig.defaults;sdkconfig.ci.board.esp_vocat_1_2;sdkconfig.vocat"
idf.py -DSDKCONFIG_DEFAULTS="$D" set-target esp32s3
idf.py -DSDKCONFIG_DEFAULTS="$D" build
```

`sdkconfig.vocat` selects the custom partition table:

```
CONFIG_PARTITION_TABLE_CUSTOM=y
CONFIG_PARTITION_TABLE_CUSTOM_FILENAME="partitions_vocat.csv"
CONFIG_ESPTOOLPY_FLASHSIZE_16MB=y
```

## Custom partition table

Reproduces the factory layout byte-for-byte and appends `anim_emotion` in the
free space after `anim_boot`. Verified: the first 11 entries are byte-identical
to the factory table.

```
# Name,        Type, SubType,  Offset,    Size,      Flags
nvs_key,       data, nvs_keys, 0xf000,    0x1000,
fctry,         data, nvs,      0x10000,   0x6000,
nvs,           data, nvs,      0x16000,   0x6000,
otadata,       data, ota,      0x1c000,   0x2000,
phy_init,      data, phy,      0x1e000,   0x1000,
model,         data, spiffs,   0x1f000,   0x96000,
factory,       app,  factory,  0xc0000,   0x7d0000,
board_test,    app,  ota_0,    0x890000,  0x190000,
spiffs_data,   data, spiffs,   0xa20000,  0xc8000,
anim_icon,     data, spiffs,   0xae8000,  0x271000,
anim_boot,     data, spiffs,   0xd59000,  0xb9000,
anim_emotion,  data, spiffs,   0xe12000,  0x1db000,
```

Flash plan verification (baseline build):

| offset | partition | image | capacity | used |
|---|---|---|---|---|
| 0x0 | bootloader | 22,432 | 32,768 | 68% |
| 0x8000 | partition table | 3,072 | 4,096 | 75% |
| 0x1c000 | otadata | 8,192 | 8,192 | 100% |
| 0x1f000 | model | 582,214 | 614,400 | 94% |
| 0xc0000 | factory app | 7,933,600 | 8,192,000 | 96% |
| 0xa20000 | spiffs_data | 819,200 | 819,200 | 100% |
| 0xae8000 | anim_icon | 1,326,723 | 2,560,000 | 51% |
| 0xd59000 | anim_boot | 648,188 | 757,760 | 85% |
| 0xe12000 | anim_emotion | 1,933,483 | 1,945,600 | 99% |

`nvs_key`, `fctry` and `nvs` are never written. RainMaker credentials survive,
and so does the provisioned Wi-Fi configuration.

**Headroom warning.** The app sits at 96% of its partition, 258 KB spare. Adding
a WebSocket client and our own logic may overflow it. `board_test` sits directly
between `factory` and `spiffs_data`, so `factory` can absorb it and grow from
8000K to 9600K, ending exactly where `spiffs_data` starts. No other offsets move.

## Recovery

A full 16 MB dump of the factory image exists, including `fctry`. Full restore:

```bash
esptool -p /dev/cu.usbmodem1101 write-flash 0x0 esp-vocat-factory-16MB.bin
```

Keep this backup. It is the only copy of the factory credentials.

## SD card

Required for the config workflow above, though the firmware boots without one
after a 10 second warning screen. `SD_CARD_NOT_FOUND_RETRY_MAX_COUNT` can be set
to 0 to remove that delay in our own builds.

**32 GB maximum.** The constraint is the filesystem, not capacity: ESP-IDF
hardcodes `FF_FS_EXFAT 0` with no Kconfig option, so only FAT16 and FAT32 mount.
SDXC cards (64 GB+) ship as exFAT and will not mount as sold.

## Status

Done:

- Factory flash dumped and verified
- ESP-IDF v5.5 toolchain working
- esp-brookesia `release/v0.6` cloned
- Custom partition table written and validated
- Baseline build compiles clean (2207/2207)

Next:

1. Flash the baseline and confirm display, touch and Wi-Fi on our own build
2. Stand up the server with a trivial echo agent
3. Replace the Coze client with a WebSocket client to it
4. Fill in STT, TTS, the Claude bridge and emotion tags, one at a time

Open decisions:

- Server on the Mac (simple, LAN only, dies when the Mac sleeps) or reachable
  from anywhere? Affects transport and auth.
- Local or hosted STT and TTS.
