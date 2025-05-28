# 🎞️ Baselight & Xytech Shot Processor

This tool processes Baselight export files and Xytech path mappings to identify used frame ranges in a video, extract shots and thumbnails, and optionally upload clips to Vimeo. It also exports detailed reports including used/unmatched frame ranges and unused frames, and integrates with MongoDB for data persistence.

---

## Features

-  Parses Baselight frame lists and optional Xytech path mapping.
-  Extracts and encodes shots from a video using frame ranges.
-  Generates thumbnails for shot midpoints.
-  Exports CSV and XLSX reports with thumbnails, timecodes, and metadata.
-  Optionally uploads extracted shots to Vimeo.
-  Supports MongoDB for persistent frame and video data.
-  Identifies and exports unused frames.
-  Supports test mode to extract a single frame by number and convert to timecode.

---

## 🧰 Requirements

- Python 3
- FFmpeg & FFprobe (`ffmpeg` and `ffprobe` must be in PATH)
- MongoDB (local instance, optional)
- Python packages (install via pip):

```bash
pip install pymongo xlsxwriter vimeo
```

---

## 🚀 Usage

```bash
python shot_proccessor.py [options]
```

### 🔧 Common Options

| Option | Description |
|--------|-------------|
| `--baselight` | Path to Baselight export file (default: `Baselight_export_spring2025.txt`) |
| `--xytech` | CSV file mapping relative → full paths |
| `--process` | Video file to process |
| `--fps` | Frames per second (default: `24.0`) |
| `--output` | Export XLSX summary report |
| `--vimeo-upload` | Upload extracted shots to Vimeo |
| `--unused-frames` | Export CSV/XLSX of unused frames |
| `--no-db` | Skip MongoDB operations |
| `--get-timecode` | Convert frame number to timecode (exits after printing) |

---

## 📂 Output Structure

When `--process` is used, the following structure is created:

```
<video_name>_processed/
├── thumbnails/          # JPG thumbnails of mid-frames
├── shots/               # Encoded MP4 shots by frame range
├── unused_frames.csv    # CSV of frames not used in any range
├── not_uploaded.csv     # Ranges that failed or were invalid
├── vimeo_links.csv      # URLs of uploaded Vimeo clips
├── <video_name>_ranges.xlsx     # XLSX report with thumbnails and Vimeo URLs
├── <video_name>_matching_ranges.csv # CSV report of successful extractions
```

---

## 🌐 Vimeo Integration

To enable video uploads, provide Vimeo credentials inside the script:

```python
CLIENT_ID = 'your_client_id'
CLIENT_SECRET = 'your_client_secret'
ACCESS_TOKEN = 'your_access_token'
```

Enable upload via:
```bash
--vimeo-upload
```

---

## 🧪 Timecode Testing

Convert a frame number to SMPTE timecode and extract a frame from the video:

```bash
python shot_proccessor.py --get-timecode 1543 --process video.mp4
```

---

## 🛢️ MongoDB Integration

By default, the tool uses a local MongoDB instance to store:
- Processed video metadata
- Baselight ranges
- Xytech mappings

To skip database usage, pass:
```bash
--no-db
```

---

## 🧾 Example

```bash
python shot_processor.py \
  --baselight Baselight_export_spring2025.txt \
  --xytech xytech_paths.csv \
  --process sample_video.mov \
  --fps 23.976 \
  --output \
  --vimeo-upload \
  --unused-frames
```

---

## 📖 Baselight File Format

Expected format: Frame ranges per shot with relative paths.

Example:
```
reel1/partA/1920x1080 frame: 105-130
reel1/partA/1920x1080 frame: 145-160
```

## 📖 Xytech Mapping Format

CSV file:
```
relative_path,full_path,workorder
reel1/partA/1920x1080,/mnt/proj/reel1/partA/1920x1080,WorkOrder123
```

