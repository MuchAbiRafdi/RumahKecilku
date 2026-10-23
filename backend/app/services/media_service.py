from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path


class MediaProcessingError(RuntimeError):
    pass


def _ffmpeg_path() -> str | None:
    executable = shutil.which("ffmpeg")
    if executable:
        return executable
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except (ImportError, RuntimeError, OSError):
        return None


def normalize_video(data: bytes, content_type: str) -> tuple[bytes, str]:
    """Convert any FFmpeg-readable video into browser-friendly MP4/H.264/AAC."""
    executable = _ffmpeg_path()
    if not executable:
        raise MediaProcessingError("Pemroses video belum tersedia. Instal dependensi backend imageio-ffmpeg.")

    with tempfile.TemporaryDirectory(prefix="rumah-media-") as temp_dir:
        source = Path(temp_dir) / "source.bin"
        target = Path(temp_dir) / "normalized.mp4"
        source.write_bytes(data)
        command = [
            executable, "-hide_banner", "-loglevel", "error", "-y",
            "-i", str(source),
            "-map", "0:v:0", "-map", "0:a?",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k",
            "-movflags", "+faststart", str(target),
        ]
        try:
            completed = subprocess.run(command, capture_output=True, timeout=300, check=False)
        except subprocess.TimeoutExpired as exc:
            raise MediaProcessingError("Konversi video melewati batas waktu 5 menit.") from exc
        if completed.returncode != 0 or not target.exists():
            detail = completed.stderr.decode("utf-8", errors="ignore")[-400:]
            raise MediaProcessingError(f"Video tidak dapat dikonversi ke format pemutaran browser. {detail}".strip())
        return target.read_bytes(), "video/mp4"
