#!/usr/bin/env python3
import subprocess
import argparse

def get_duration(path):
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", path],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )
    output = result.stdout.strip()
    if not output:
        raise RuntimeError(f"ffprobe error for {path}: {result.stderr.strip()}")
    try:
        return float(output)
    except ValueError:
        raise ValueError(f"Invalid duration value: {output}")

def calculate_bitrates(duration, target_size, audio_kbps):
    audio_bytes = audio_kbps * 1024 * duration / 8
    video_bytes = max(0, target_size - audio_bytes)
    video_kbps = int(video_bytes * 8 / duration / 1000)
    return video_kbps

def compress(input_path, output_path, target_mb, audio_kbps):
    duration = get_duration(input_path)
    target_bytes = target_mb * 1024 * 1024
    video_kbps = calculate_bitrates(duration, target_bytes, audio_kbps)
    subprocess.run([
        "ffmpeg", "-i", input_path,
        "-c:v", "libx264", "-b:v", f"{video_kbps}k",
        "-c:a", "aac",    "-b:a", f"{audio_kbps}k",
        output_path
    ], check=True)

def main():
    parser = argparse.ArgumentParser(description="Compress video to a size target")
    parser.add_argument("input",  help="Input video file")
    parser.add_argument("output", help="Output video file")
    parser.add_argument("--target", type=int, default=100,
                        help="Target size in MB (default: 100)")
    parser.add_argument("--audio",  type=int, default=128,
                        help="Audio bitrate in kbps (default: 128)")
    args = parser.parse_args()
    compress(args.input, args.output, args.target, args.audio)

if __name__ == "__main__":
    main()