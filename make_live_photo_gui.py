#!/usr/bin/env python3
import struct
import sys
import os
import io
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from PIL import Image
from threading import Thread

XMP_IDENTIFIER = b'http://ns.adobe.com/xap/1.0/\x00'


def find_jpeg_end(data: bytes) -> int:
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
    if jpeg_data[:2] != b'\xff\xd8':
        raise ValueError("Not a JPEG file")

    result = bytearray(jpeg_data[:2])
    pos = 2
    while pos < len(jpeg_data):
        if jpeg_data[pos] != 0xFF:
            result += jpeg_data[pos:]
            break
        marker = jpeg_data[pos:pos + 2]
        if len(marker) < 2:
            result += jpeg_data[pos:]
            break
        marker_code = struct.unpack('>H', marker)[0]
        if marker_code in (0xFFD8, 0xFFD9):
            result += marker
            pos += 2
            continue
        if marker_code == 0xFFDA:
            result += jpeg_data[pos:]
            break
        seg_len = struct.unpack('>H', jpeg_data[pos + 2:pos + 4])[0]
        seg_data = jpeg_data[pos + 4:pos + 2 + seg_len]
        if marker_code == 0xFFE1 and seg_data.startswith(XMP_IDENTIFIER):
            pos += 2 + seg_len
            continue
        result += marker + jpeg_data[pos + 2:pos + 2 + seg_len]
        pos += 2 + seg_len

    return bytes(result)


def build_xmp_app1(mp4_size: int) -> bytes:
    xmp_content = (
        '<x:xmpmeta xmlns:x="adobe:ns:meta/" x:xmptk="Adobe XMP Core 5.1.0-jc003">\n'
        '  <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">\n'
        '    <rdf:Description rdf:about="\n'
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
    with open(jpg_path, 'rb') as f:
        jpg_data = f.read()
    with open(mp4_path, 'rb') as f:
        mp4_data = f.read()

    jpeg_end = find_jpeg_end(jpg_data)
    clean_jpeg = jpg_data[:jpeg_end]
    stripped_jpeg = strip_existing_xmp(clean_jpeg)
    mp4_size = len(mp4_data)
    xmp_segment = build_xmp_app1(mp4_size)

    result = bytearray()
    result += stripped_jpeg[:2]
    result += xmp_segment
    result += stripped_jpeg[2:]
    result += mp4_data

    with open(output_path, 'wb') as f:
        f.write(bytes(result))

    return os.path.getsize(output_path)


class LivePhotoGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Make Live Photo - Google Motion Photo")
        self.root.geometry("700x550")
        self.root.resizable(True, True)

        self.file_pairs = []
        self.output_dir = tk.StringVar()

        self.create_widgets()

    def create_widgets(self):
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        title_label = ttk.Label(main_frame, text="Make Live Photo (Motion Photo)", font=("Arial", 14, "bold"))
        title_label.pack(pady=(0, 10))

        output_frame = ttk.LabelFrame(main_frame, text="Output Directory", padding="5")
        output_frame.pack(fill=tk.X, pady=(0, 10))

        ttk.Entry(output_frame, textvariable=self.output_dir, width=60).pack(side=tk.LEFT, padx=5)
        ttk.Button(output_frame, text="Browse", command=self.browse_output_dir).pack(side=tk.LEFT)

        list_frame = ttk.LabelFrame(main_frame, text="JPG + MP4 File Pairs", padding="5")
        list_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        scrollbar = ttk.Scrollbar(list_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.file_listbox = tk.Listbox(list_frame, height=12, yscrollcommand=scrollbar.set)
        self.file_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.file_listbox.yview)

        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=(0, 10))

        ttk.Button(btn_frame, text="Add JPG + MP4 Files", command=self.add_pairs).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Remove Selected", command=self.remove_pair).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Clear All", command=self.clear_all).pack(side=tk.LEFT, padx=5)

        self.progress = ttk.Progressbar(main_frame, mode='determinate')
        self.progress.pack(fill=tk.X, pady=(0, 5))

        self.status_label = ttk.Label(main_frame, text="Ready")
        self.status_label.pack(pady=(0, 5))

        ttk.Button(main_frame, text="Start Processing", command=self.start_processing).pack(pady=(0, 5))

    def browse_output_dir(self):
        dir_path = filedialog.askdirectory()
        if dir_path:
            self.output_dir.set(dir_path)

    def add_pairs(self):
        files = filedialog.askopenfilenames(
            title="Select JPG and MP4 Files",
            filetypes=[("Image/Video files", "*.jpg *.jpeg *.mp4"), ("All files", "*.*")]
        )
        if not files:
            return

        jpg_files = {}
        mp4_files = {}

        for f in files:
            basename = os.path.basename(f)
            name, ext = os.path.splitext(basename)
            ext_lower = ext.lower()
            if ext_lower in ('.jpg', '.jpeg'):
                jpg_files[name] = f
            elif ext_lower == '.mp4':
                mp4_files[name] = f

        matched_pairs = []
        unmatched = []

        for name in sorted(set(jpg_files.keys()) | set(mp4_files.keys())):
            if name in jpg_files and name in mp4_files:
                matched_pairs.append((name, jpg_files[name], mp4_files[name]))
            else:
                unmatched.append(name)

        for name, jpg_path, mp4_path in matched_pairs:
            self.file_pairs.append((jpg_path, mp4_path))
            self.file_listbox.insert(tk.END, f"{name}.jpg + {name}.mp4")

        if unmatched:
            msg = "以下文件未找到匹配项，已舍弃：\n" + "\n".join(
                f"{name}.jpg" if name in jpg_files else f"{name}.mp4" for name in unmatched
            )
            messagebox.showinfo("匹配结果", msg)

    def remove_pair(self):
        selection = self.file_listbox.curselection()
        if selection:
            idx = selection[0]
            self.file_listbox.delete(idx)
            self.file_pairs.pop(idx)

    def clear_all(self):
        self.file_listbox.delete(0, tk.END)
        self.file_pairs.clear()

    def start_processing(self):
        if not self.file_pairs:
            messagebox.showwarning("Warning", "Please add at least one JPG + MP4 pair")
            return

        output_dir = self.output_dir.get()
        if not output_dir:
            messagebox.showwarning("Warning", "Please select an output directory")
            return

        self.progress['maximum'] = len(self.file_pairs)
        self.progress['value'] = 0
        self.status_label.config(text="Processing...")

        Thread(target=self.process_files, args=(output_dir,), daemon=True).start()

    def process_files(self, output_dir):
        success_count = 0
        fail_count = 0

        for i, (jpg_path, mp4_path) in enumerate(self.file_pairs):
            try:
                jpg_basename = os.path.splitext(os.path.basename(jpg_path))[0]
                output_path = os.path.join(output_dir, f"{jpg_basename}_live.jpg")

                make_live_photo(jpg_path, mp4_path, output_path)

                success_count += 1
                self.root.after(0, self.update_progress, i + 1, f"Processed: {jpg_basename}_live.jpg")
            except Exception as e:
                fail_count += 1
                self.root.after(0, self.update_status, f"Error processing {os.path.basename(jpg_path)}: {str(e)}")

        self.root.after(0, self.update_status, f"Done! Success: {success_count}, Failed: {fail_count}")
        self.root.after(0, lambda: messagebox.showinfo("Complete", f"Processing complete!\nSuccess: {success_count}\nFailed: {fail_count}"))

    def update_progress(self, value, status_text):
        self.progress['value'] = value
        self.status_label.config(text=status_text)

    def update_status(self, text):
        self.status_label.config(text=text)


def main():
    root = tk.Tk()
    app = LivePhotoGUI(root)
    root.mainloop()


if __name__ == '__main__':
    main()
