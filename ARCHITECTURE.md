# bujz1-the-bot

Turning an Espressif ESP-VoCat into Bujji (BU-JZ1) from Kalki 2898 AD: an
expressive voice companion with a backend I control.

Last updated: 2026-09-15

## Goals

1. Connect the device to a voice agent I control, hosted or local.
2. Issue spoken commands that Claude Code acts on, remotely.
3. Drive the eyes and expressions properly, in Bujji's red visor style.

These look like three projects but they are one. All three are downstream of a
single decision: own the backend.

## Hardware

ESP-VoCat v1.2, verified against the device rather than the datasheet.

| | |
|---|---|
| Module | ESP32-S3-WROOM-1-N16R16VA |
| Flash | 16 MB (GigaDevice `c8`/`6018`), quad I/O, 1.8 V |
| PSRAM | 16 MB, **Octal mode, 80 MHz, XIP from PSRAM** |
| Display | 1.85" round QSPI LCD, 360x360, ST77916 |
| Audio | ES7210 4-ch ADC in, ES8311 + NS4150B out |
| Motion | BMI270 IMU · Touch: 2 pads (GPIO6/7) |
| USB | Native (`0x303A`), `USB JTAG_serial debug unit` |
| MAC | b4:3a:45:16:2d:38 |

## Use release/v0.7, not v0.6

The single most costly mistake of the first session. The factory firmware's own
app descriptor, read out of the flash dump:

```
version      : 0.12.6-fac
project_name : brookesia_speaker
compile date : Feb  5 2026
idf_ver      : v5.5.2-dirty
```

Official compatibility:

| esp-brookesia | ESP-IDF | status |
|---|---|---|
| master (v0.8) | 6.0–6.2 | active development |
| **release/v0.7** | **>= 5.5, <= 6.0** | **stable — use this** |
| release/v0.6 | >= 5.3, <= 5.5 | end of maintenance |

v0.6 is EOL and structured completely differently (`products/speaker`, SPIFFS,
Coze-only). v0.7 restructured into `examples/` + `hal/` + `agent/`, with a real
HAL board definition for this board. The app we want is
`examples/agent/chatbot`.

**Building v0.6 produced a 10-second crash loop**: `assert failed:
heap_caps_free ... target pointer is outside heap areas`, panic, reboot, repeat.
It surfaced in unrelated threads (main task teardown, Wi-Fi scan), which is the
signature of an environment problem rather than a code bug. Root cause was
almost certainly the missing board configuration — v0.6 has no board manager, so
the build ran generic PSRAM settings on a board that needs Octal mode with XIP.

## Build procedure

ESP-IDF on `release/v5.5` **branch** (not the `v5.5` tag — the tag is frozen at
July 2025 and lacks fourteen months of fixes).

Python 3.14 cannot create IDF's virtualenv. Use 3.11. `idfenv.sh`:

```bash
export PATH="/opt/homebrew/opt/python@3.11/libexec/bin:$PATH"
source ~/esp/esp-idf/export.sh >/dev/null 2>&1
```

IDF's installer does not pull `cmake`/`ninja`. Without them `idf.py` **exits 0
while doing nothing**, which is a confusing failure:

```bash
python "$IDF_PATH/tools/idf_tools.py" install cmake ninja
```

Then, and this step is mandatory:

```bash
cd examples/agent/chatbot
idf.py gen-bmgr-config -b esp_vocat_board_v1_2   # wires in the HAL board
idf.py build
idf.py -p <PORT> flash
```

`gen-bmgr-config` pulls in the board's own defaults, including the PSRAM
settings that matter:

```
CONFIG_SPIRAM_MODE_OCT=y
CONFIG_SPIRAM_XIP_FROM_PSRAM=y
CONFIG_SPIRAM_SPEED_80M=y
```

Note `idf_ext.py` **fails the build if user sdkconfig defaults load after
`board_manager.defaults`**, so you cannot append an override file. To change a
setting, edit what the board defaults already reference.

## The partition table will destroy your credentials

`fctry` at 0x10000 holds per-device RainMaker credentials burned in at
manufacture. They are unique and cannot be reissued. **Both** v0.6's and v0.7's
stock partition tables place a 600K `model` partition at exactly 0x10000.

Flashing either one unmodified overwrites them permanently.

`examples/agent/chatbot/partitions_16m.csv` is therefore replaced with a table
whose first five entries are byte-identical to the factory layout (verified
programmatically against the flash dump), keeping v0.7's LittleFS/FAT types for
everything below:

```
# Name,          Type, SubType,   Offset,    Size,   Flags
nvs_key,         data, nvs_keys,  0xf000,    0x1000,
fctry,           data, nvs,       0x10000,   0x6000,
nvs,             data, nvs,       0x16000,   0x6000,
otadata,         data, ota,       0x1c000,   0x2000,
phy_init,        data, phy,       0x1e000,   0x1000,
model,           data, littlefs,  0x1f000,   600K,
factory,         app,  factory,   0xc0000,   7M,
storage,         data, fat,       0x7c0000,  500K,
littlefs_data,   data, littlefs,  0x83d000,  500K,
anim_icon,       data, littlefs,  0x8ba000,  3000K,
```

Stock kept alongside as `partitions_16m.csv.stock`. Rules: never
`erase_flash`, and verify the flash plan's offsets against 0xf000–0x1c000
before every write.

**Migrating firmware requires erasing `nvs`.** Preserving the old build's NVS
made v0.7's Wi-Fi provisioning silently fail to persist — it reprovisioned on
every boot. Fix, which does not touch `fctry`:

```bash
esptool --chip esp32s3 -p <PORT> erase_region 0x16000 0x6000
```

## Target architecture

```
ESP-VoCat ──XiaoZhi protocol──> our server
                                  ├─ STT
                                  ├─ Hermes (persona) / Claude (work commands)
                                  ├─ Bodhan TTS  (Sravani)
                                  └─ emotion tag ──> eye animation
```

**v0.7 ships XiaoZhi as the default agent**, alongside Coze and OpenAI, with
runtime switching. XiaoZhi is an open, self-hostable protocol, so the plan is no
longer "write a WebSocket client and replace the Coze layer" — it is "stand up a
XiaoZhi-compatible server and repoint the device." Substantially less firmware
work than the v0.6 plan assumed.

Default endpoint is `api.xiaozhi.me`; first boot shows an activation code to
claim the device against a XiaoZhi account.

## Voice: Bodhan indic-speak

Hosted API, OpenAI-compatible shapes. `voice/bodhan.py`.

- Base `https://api.bodhan.ai/v1`, `POST /audio/speech`, bearer auth
- **4 requests/minute**, ₹6 per 10K characters, keys are per model
- Response is `audio/wav`, PCM16, 24 kHz, mono

The request shape is easy to get wrong. There is no `language_code` field;
language and style go in `instructions` as a **JSON string**:

```json
{"model":"indic-speak","input":"...","voice":"Sravani",
 "instructions":"{\"lang\": \"en\", \"style\": \"happy\"}"}
```

**Voice: `Sravani`** — the Telugu-recorded female. Any voice can read any
language, so she gives Telugu-accented Indian English (the Hyderabad texture)
and carries over unchanged when Telugu is added.

Six of the fourteen styles are emotions, which the emotion tag maps onto:

```
annoyed→anger  worried→fear  excited/happy→happy  sad→sad  surprised→surprise
neutral/thinking→(omit)
```

## Character

Bujji (BU-JZ1): Bhairava's companion AI, formerly a cargo ship pilot AI. Voiced
by Keerthy Suresh. Anxious, eager, fusses, tells you when you're being an idiot,
unreservedly loyal. Not a servant.

Eventually code-switches: Telugu **in Telugu script** for feeling, English for
technical. Romanised Telugu will be read as English and produce garbage.

## Eyes

Angular red visor slits, generated rather than drawn, so they are editable as
code. `eyes/make_eyes.py` renders 284x126 GIFs for eleven emotions. Resting
face slants inward: focused, faintly unimpressed.

Converted with the in-repo tool (`--depth 8` is real colour via a median-cut
256-colour BGRA palette; `--depth 4` is grayscale):

```bash
python gif_to_aaf.py eyes/gif eyes/aaf --split 16 --depth 8 --enable-huffman
```

Geometric shapes compress far better than the stock organic art: 1,397,128
bytes against 1,933,483 stock.

**Needs rework for v0.7.** Built and flashed successfully on v0.6, which used
SPIFFS and a dedicated `anim_emotion` partition. v0.7 uses LittleFS, has no
`anim_emotion` (animations live in `anim_icon`), and drives expressions through
a different `EmoteHelper` path. The generator and the designs carry over; the
packaging does not.

## Recovery

Full 16 MB factory dump including `fctry`, sha256
`8910dfbd...e8e5e39d`. Restores byte-perfect and has been exercised for real:

```bash
esptool -p <PORT> write_flash 0x0 backup/esp-vocat-factory-16MB.bin
```

## SD card

Optional. Without one the firmware shows a warning and stalls 10 seconds before
continuing. 32 GB maximum and FAT32 only — ESP-IDF hardcodes `FF_FS_EXFAT 0`, so
SDXC cards ship unmountable.

## Status

Working:

- v0.7 chatbot, stock, boots clean — 0 reboots, 0 asserts over 45s
- Wi-Fi provisioning via SoftAP portal at `192.168.4.1`, persists after the
  `nvs` erase
- XiaoZhi agent activated and holding a conversation
- Bodhan TTS client, Bujji voice samples across six emotions
- Eye generator and conversion pipeline

Next:

1. Repackage the eyes for v0.7 (LittleFS, `anim_icon`, `EmoteHelper`)
2. Stand up a self-hosted XiaoZhi server and repoint the device
3. Wire Hermes for persona, Bodhan for voice, emotion tags to the eyes
4. Add the Claude Agent SDK path for work commands

## Debugging notes

Worth remembering, because each cost real time:

- `heap_caps_free ... outside heap areas` recurring across **unrelated** threads
  means the environment is wrong, not the code. Chasing individual call sites
  produced three wrong fixes in a row.
- Read the app descriptor at app-partition + 0x20 to fingerprint a factory
  firmware. Version, project name, build date and IDF version. Doing this first
  would have saved the entire v0.6 detour.
- `idf.py` exiting 0 having done nothing means `cmake` is missing.
- Opening the serial port toggles DTR/RTS and can reset an ESP32-S3 over native
  USB, so monitoring perturbs what it measures.
