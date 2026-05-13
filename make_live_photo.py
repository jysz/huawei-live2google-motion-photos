#!/usr/bin/env python3
"""
Combine separate JPG + MP4 into a Google Photos-recognizable Live Photo (Motion Photo).

Based on the Android Motion Photo format 1.0 specification:
https://developer.android.com/media/platform/motion-photo-format

The format is: [JPEG with XMP metadata] [MP4 video appended after JPEG EOI]

Key insight: Item:Length is the byte offset of the video from the END of the file,
equivalent to the video file size. Google Photos computes video_start = file_size - Item:Length.

Usage:
    python3 make_live_photo.py <input.jpg> <input.mp4> <output.jpg>
"""

import struct
import sys
import os
from PIL import Image
import io

XMP_IDENTIFIER = b'http://ns.adobe.com/xap/1.0/\x00'


def find_jpeg_end(data: bytes) -> int:
    """Find the end of the actual JPEG image data (after the last valid EOI).

    Some phones (Huawei, etc.) append proprietary data after the JPEG EOI.
    We strip that and only keep the valid JPEG.
    """
    if data[:2] != b'\xff\xd8':
        raise ValueError("Not a JPEG file")

    eoi_positions = []
    pos = 0
    while True:
        pos = data.find(b'\xff\xd9', pos)
        if pos == -1:
            break
        eoi_positions.append(pos)
        pos += 2

    if not eoi_positions:
        raise ValueError("No JPEG EOI marker found")

    for eoi in reversed(eoi_positions):
        try:
            img = Image.open(io.BytesIO(data[:eoi + 2]))
            img.verify()
            return eoi + 2
        except Exception:
            continue

    return eoi_positions[-1] + 2


def strip_existing_xmp(jpeg_data: bytes) -> bytes:
    """Remove any existing XMP APP1 segments to avoid duplicate XMP conflicts."""
    if jpeg_data[:2] != b'\xff\xd8':
        raise ValueError("Not a JPEG file")

    result = bytearray(jpeg_data[:2])  # keep SOI
    pos = 2
    while pos < len(jpeg_data):
        if jpeg_data[pos] != 0xFF:
            # Not a marker, copy rest as-is (entropy-coded data)
            result += jpeg_data[pos:]
            break
        marker = jpeg_data[pos:pos + 2]
        if len(marker) < 2:
            result += jpeg_data[pos:]
            break
        marker_code = struct.unpack('>H', marker)[0]
        # Standalone markers (no length field)
        if marker_code in (0xFFD8, 0xFFD9):
            result += marker
            pos += 2
            continue
        if marker_code == 0xFFDA:  # SOS - copy to end
            result += jpeg_data[pos:]
            break
        # Read segment length
        seg_len = struct.unpack('>H', jpeg_data[pos + 2:pos + 4])[0]
        seg_data = jpeg_data[pos + 4:pos + 2 + seg_len]
        # Skip XMP APP1 segments
        if marker_code == 0xFFE1 and seg_data.startswith(XMP_IDENTIFIER):
            pos += 2 + seg_len
            continue
        result += marker + jpeg_data[pos + 2:pos + 2 + seg_len]
        pos += 2 + seg_len

    return bytes(result)


def build_xmp_app1(mp4_size: int) -> bytes:
    """Build an XMP APP1 segment for Motion Photo metadata.

    Item:Length = MP4 file size (offset from end of file to start of video).
    Item:Padding = 0 for both items.
    Per Android Motion Photo format 1.0 spec.
    """
    xmp_content = (
        '<x:xmpmeta xmlns:x="adobe:ns:meta/" x:xmptk="Adobe XMP Core 5.1.0-jc003">\n'
        '  <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">\n'
        '    <rdf:Description rdf:about=""\n'
        '        xmlns:GCamera="http://ns.google.com/photos/1.0/camera/"\n'
        '        xmlns:Container="http://ns.google.com/photos/1.0/container/"\n'
        '        xmlns:Item="http://ns.google.com/photos/1.0/container/item/"\n'
        '      GCamera:MotionPhoto="1"\n'
        '      GCamera:MotionPhotoVersion="1"\n'
        '      GCamera:MotionPhotoPresentationTimestampUs="-1">\n'
        '      <Container:Directory>\n'
        '        <rdf:Seq>\n'
        '          <rdf:li rdf:parseType="Resource">\n'
        '            <Container:Item\n'
        '              Item:Mime="image/jpeg"\n'
        '              Item:Semantic="Primary"\n'
        '              Item:Length="0"\n'
        '              Item:Padding="0"/>\n'
        '          </rdf:li>\n'
        '          <rdf:li rdf:parseType="Resource">\n'
        '            <Container:Item\n'
        '              Item:Mime="video/mp4"\n'
        '              Item:Semantic="MotionPhoto"\n'
        f'              Item:Length="{mp4_size}"\n'
        '              Item:Padding="0"/>\n'
        '          </rdf:li>\n'
        '        </rdf:Seq>\n'
        '      </Container:Directory>\n'
        '    </rdf:Description>\n'
        '  </rdf:RDF>\n'
        '</x:xmpmeta>'
    )

    payload = XMP_IDENTIFIER + xmp_content.encode('utf-8')
    length = len(payload) + 2
    return b'\xff\xe1' + struct.pack('>H', length) + payload


def make_live_photo(jpg_path: str, mp4_path: str, output_path: str):
    """Combine JPG + MP4 into a Motion Photo."""
    with open(jpg_path, 'rb') as f:
        jpg_data = f.read()
    with open(mp4_path, 'rb') as f:
        mp4_data = f.read()

    # Strip any trailing proprietary data after JPEG EOI
    jpeg_end = find_jpeg_end(jpg_data)
    clean_jpeg = jpg_data[:jpeg_end]

    if len(clean_jpeg) < len(jpg_data):
        print(f"  Stripped {len(jpg_data) - len(clean_jpeg):,} bytes of trailing data")

    # Remove existing XMP APP1 to avoid duplicates
    stripped_jpeg = strip_existing_xmp(clean_jpeg)
    if len(stripped_jpeg) < len(clean_jpeg):
        print(f"  Removed existing XMP ({len(clean_jpeg) - len(stripped_jpeg):,} bytes)")

    mp4_size = len(mp4_data)
    xmp_segment = build_xmp_app1(mp4_size)

    # Build output: SOI + XMP APP1 + rest of JPEG (after SOI) + MP4
    result = bytearray()
    result += stripped_jpeg[:2]   # SOI
    result += xmp_segment          # XMP APP1 (inserted right after SOI)
    result += stripped_jpeg[2:]   # Rest of JPEG (all original segments + image data)
    result += mp4_data            # MP4 appended directly after JPEG EOI

    with open(output_path, 'wb') as f:
        f.write(bytes(result))

    out_size = os.path.getsize(output_path)
    jpeg_part_size = len(stripped_jpeg) + len(xmp_segment)
    print(f"  Output: {output_path} ({out_size:,} bytes)")
    print(f"    JPEG part: {jpeg_part_size:,} bytes")
    print(f"    MP4 part:  {mp4_size:,} bytes")
    print(f"    Item:Length = {mp4_size} (offset from EOF = video size)")
    print(f"    Video starts at byte {out_size - mp4_size} (file_size - Item:Length)")


def main():
    if len(sys.argv) != 4:
        print(f"Usage: {sys.argv[0]} <input.jpg> <input.mp4> <output.jpg>")
        sys.exit(1)

    jpg_path, mp4_path, output_path = sys.argv[1], sys.argv[2], sys.argv[3]

    for p in [jpg_path, mp4_path]:
        if not os.path.exists(p):
            print(f"Error: {p} not found")
            sys.exit(1)

    print(f"Combining {jpg_path} + {mp4_path} -> {output_path}")
    make_live_photo(jpg_path, mp4_path, output_path)
    print("Done!")


if __name__ == '__main__':
    main()
