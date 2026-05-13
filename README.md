# 📸 Huawei Live Photo → Google Photos Converter
Convert Huawei Live Photos to Google Photos compatible Motion Photos.

Combine separate JPG + MP4 files from Huawei Live Photos into Google Photos-compatible Motion Photos.

## What Works

* **Full Compatibility**: Motion is playable on both Google Photos App and Web.
* **Ultra HDR**: Preserves Ultra HDR information.
* **EXIF Metadata**: Retains camera model and shutter speed.
* **GPS Location**: Preserves original location data.

## How It Works

A Google Photos Motion Photo is a single file containing two parts:

```
[JPEG image + XMP metadata] [MP4 video]
```

The XMP metadata field `Item:Length` tells Google Photos where the video starts — its value equals the MP4 size in bytes, and Google Photos locates the video at `file_size - Item:Length`.

## Usage
### GUI
just run the exe and enjoy 😀
![image](https://github.com/user-attachments/assets/47240a0e-993e-4ea9-a58f-0bfeac30823b)
### Python Script (CLI)
```bash
python3 make_live_photo.py <input.jpg> <input.mp4> <output.jpg>
```

Example:

```bash
python3 make_live_photo.py IMG_20250621_173410.jpg IMG_20250621_173410.mp4 IMG_20250621_173410_live.jpg
```

Upload the resulting `IMG_20250621_173410_live.jpg` to Google Photos — it will be recognized as a Motion Photo.

## Dependencies

- Python 3.10+
- Pillow

```bash
pip install Pillow
```

## Processing Steps

1. **Strip vendor trailing data** — Phones like Huawei append proprietary data (depth maps, etc.) after the JPEG EOI marker. The program validates EOI positions and truncates at the correct boundary.
2. **Deduplicate XMP** — If the source JPG already contains an XMP APP1 segment, it is removed first to avoid duplicate conflicts.
3. **Insert Motion Photo XMP** — A new XMP APP1 segment is inserted after the JPEG SOI, declaring Motion Photo attributes and the video offset.
4. **Concatenate** — The clean JPEG and raw MP4 are written sequentially.

## Compatibility

Verified with:

- Source: HUAWEI nova 14 Ultra JPG + MP4
- Target: Google Photos— recognized as Motion Photo with playback

## References

- [Android Motion Photo format 1.0](https://developer.android.com/media/platform/motion-photo-format)
- [joelkitching.com - Create Google Photos Motion Photo](https://joelkitching.com/writing/create-google-photos-motion-photo/)

## Built With
  **AI Assistance:** DeepSeek V4 Pro, GLM 5.1
