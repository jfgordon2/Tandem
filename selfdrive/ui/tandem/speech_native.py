"""Voice typing with whisper.cpp's CPU runner (2 threads while driving, speech.driving_limits). No audio leaves the worker's pipes.

The source and tiny.en Q8 model are pinned and checked on first use. Only the resulting
executable and model are needed after setup; nothing is installed into AGNOS or openpilot.
"""
from __future__ import annotations

import io
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import wave
from collections.abc import Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
  import numpy as np

REVISION = "d1be6fde11ac6e0407606b4e42fe72d34add8037"  # whisper.cpp v1.9.5 (MIT)
SOURCE_URL = f"https://codeload.github.com/ggml-org/whisper.cpp/tar.gz/{REVISION}"
SOURCE_SHA256 = "645445da884df6dbd52b30f82d7be7c01d1767c938714e477e786b88d529e9f4"
MODEL_NAME = "ggml-tiny.en-q8_0.bin"
MODEL_URL = f"https://huggingface.co/ggerganov/whisper.cpp/resolve/5359861c739e955e79d9a303bcbc70fb988958b1/{MODEL_NAME}"
MODEL_SHA256 = "5bc2b3860aa151a4c6e7bb095e1fcce7cf12c7b020ca08dcec0c6d018bb7dd94"
ADDRESS_PROMPT = "123 First Street, New York, NY 10003. 4500 Main St, Des Moines, IA."
RATE = 16000


def executable(folder: Path) -> Path:
  return folder / f"whisper-{REVISION[:12]}" / "whisper-cli"


def ready(folder: Path) -> bool:
  return os.access(executable(folder), os.X_OK) and (folder / MODEL_NAME).is_file()


def prepare(folder: Path, download: Callable[[str, Path, Callable[[float], None], str | None], None], progress: Callable[[float], None]) -> None:
  """Build once from verified source, without replacing a working executable on failure."""
  folder.mkdir(parents=True, exist_ok=True)
  if not (folder / MODEL_NAME).is_file():
    download(MODEL_URL, folder / MODEL_NAME, lambda p: progress(p * 0.8), MODEL_SHA256)
  binary = executable(folder)
  if os.access(binary, os.X_OK):
    return
  archive = folder / f"whisper-{REVISION[:12]}.tar.gz"
  download(SOURCE_URL, archive, lambda p: progress(0.8 + p * 0.1), SOURCE_SHA256)
  with tarfile.open(archive) as source:
    source.extractall(folder, filter="data")
  build = binary.parent / "build"
  source_dir = folder / f"whisper.cpp-{REVISION}"
  progress(0.9)
  subprocess.run(["cmake", "-S", str(source_dir), "-B", str(build), "-DCMAKE_BUILD_TYPE=Release", "-DBUILD_SHARED_LIBS=OFF",
                  "-DWHISPER_BUILD_TESTS=OFF", "-DWHISPER_BUILD_SERVER=OFF", "-DGGML_OPENMP=OFF"],
                 stdout=sys.stderr, stderr=sys.stderr, check=True)
  subprocess.run(["cmake", "--build", str(build), "--target", "whisper-cli", "-j4"],
                 stdout=sys.stderr, stderr=sys.stderr, check=True)
  part = binary.with_suffix(f".{os.getpid()}.part")
  try:
    shutil.copy2(build / "bin" / "whisper-cli", part)
    part.replace(binary)
  finally:
    part.unlink(missing_ok=True)
  progress(1.0)


class NativeWhisper:
  """Whisper through the native whisper.cpp runner (the comma's CPU), started fresh for each transcription."""

  def __init__(self, folder: Path):
    self.folder = folder

  def transcribe(self, samples: np.ndarray, style: str) -> str:
    """Transcribes the samples with the native runner.

    Args:
      samples: 16 kHz mono audio, -1 to 1.
      style: "address" primes the model to write an address; anything else writes plain text.

    Returns:
      The words heard, or "" when none were.
    """
    import numpy as np
    # The recorder allows 15 s. Keep that entire window (plus rounding), rather than encoding 30 s of mostly silence.
    # Longer --file diagnostics retain their full context as well.
    context = min(1500, max(768, math.ceil(len(samples) / RATE * 50 / 128) * 128))
    audio = io.BytesIO()
    with wave.open(audio, "wb") as wav:
      wav.setnchannels(1)
      wav.setsampwidth(2)
      wav.setframerate(RATE)
      wav.writeframes((np.clip(samples, -1, 1) * 32767).astype("<i2").tobytes())
    command = [sys.executable, str(Path(__file__)), "--exec", str(os.getpid()), str(executable(self.folder)),
               "-m", str(self.folder / MODEL_NAME), "-f", "-", "-otxt", "-of", "-", "-ng", "-nt", "-np", "-nf", "-bs", "1", "-bo", "1",
               "-t", os.environ.get("TANDEM_SPEECH_THREADS") or str(min(4, os.cpu_count() or 1)), "-l", "en", "-ac", str(context)]
    if style == "address":
      command.extend(["--prompt", ADDRESS_PROMPT])
    result = subprocess.run(command, input=audio.getvalue(), stdout=subprocess.PIPE, stderr=sys.stderr, check=True, timeout=30)
    return result.stdout.decode("utf-8", errors="replace").strip()


def exec_runner(parent: int, command: list[str]) -> None:
  """Keep cancellation effective: killing the Python speech worker also kills its native runner.

  Use a fresh helper process before exec, rather than running Python in preexec_fn after a threaded fork.
  """
  if sys.platform.startswith("linux"):
    import ctypes
    import signal
    if ctypes.CDLL(None, use_errno=True).prctl(1, signal.SIGKILL, 0, 0, 0) != 0:
      raise OSError(ctypes.get_errno(), "Could not bind speech runner to its worker")
    if os.getppid() != parent:                  # the worker may have ended before prctl
      raise SystemExit(1)
  os.execv(command[0], command)


if __name__ == "__main__" and sys.argv[1:2] == ["--exec"]:
  exec_runner(int(sys.argv[2]), sys.argv[3:])
