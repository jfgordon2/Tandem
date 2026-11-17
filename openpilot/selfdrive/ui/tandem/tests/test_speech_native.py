"""Native voice typing: real pipe/audio handoff, setup failure recovery, and worker cancellation."""
import json
from pathlib import Path
import subprocess
import sys
import time

import numpy as np
import pytest

from openpilot.selfdrive.ui.tandem import speech, speech_native as native


@pytest.mark.parametrize("style,expected", [("address", "123 1st Street"), ("text", "1 2 3 First Street")])
@pytest.mark.parametrize("duration,context", [(2.5, 768), (15, 768), (20, 1024), (35, 1500)])
def test_native_worker_receives_audio_and_returns_clean_text(tmp_path, monkeypatch, style, expected, duration, context):
  # A tiny executable at the runner boundary reads the actual WAV pipe and reports its arguments.
  binary = native.executable(tmp_path)
  binary.parent.mkdir()
  binary.write_text(f"#!{sys.executable}\n" + '''import io,json,sys,wave
from pathlib import Path
audio=wave.open(io.BytesIO(sys.stdin.buffer.read()), 'rb')
Path(sys.argv[sys.argv.index('-m')+1]).write_text(json.dumps({
  'args':sys.argv[1:], 'rate':audio.getframerate(), 'channels':audio.getnchannels(),
  'width':audio.getsampwidth(), 'frames':audio.getnframes()}))
print(' 1 2 3 First Street. ')
''')
  binary.chmod(0o755)
  monkeypatch.setenv("TANDEM_SPEECH_BACKEND", "native")
  model, vocab = speech.load(tmp_path)
  samples = np.full(int(duration * 16000), 0.1, dtype=np.float32)
  assert speech.transcribe(model, vocab, samples, style=style) == expected
  info = json.loads((tmp_path / native.MODEL_NAME).read_text())
  assert (info['rate'], info['channels'], info['width'], info['frames']) == (16000, 1, 2, len(samples))
  assert info['args'][info['args'].index('-ac') + 1] == str(context)
  assert ('--prompt' in info['args']) == (style == 'address')
  assert '-ng' in info['args'] and '-nf' in info['args']
  assert '-otxt' in info['args'] and info['args'][info['args'].index('-of') + 1] == '-'
  assert not list(tmp_path.glob('*.wav'))


def test_native_readiness_requires_both_executable_and_model(tmp_path, monkeypatch):
  monkeypatch.setenv("TANDEM_SPEECH_BACKEND", "native")
  (tmp_path / native.MODEL_NAME).touch()
  assert not speech.model_ready(tmp_path)
  binary = native.executable(tmp_path)
  binary.parent.mkdir()
  binary.touch()
  assert not speech.model_ready(tmp_path)
  binary.chmod(0o755)
  assert speech.model_ready(tmp_path)


def test_failed_native_build_is_not_marked_ready_and_can_be_retried(tmp_path, monkeypatch):
  import tarfile
  downloads = []

  def download(url, dest, progress, digest):
    downloads.append((url, digest))
    if dest.suffix == '.gz':
      with tarfile.open(dest, 'w:gz'):
        pass
    else:
      dest.write_bytes(b'model')

  def fail(*args, **kwargs):
    raise subprocess.CalledProcessError(1, args[0])

  monkeypatch.setattr(native.subprocess, 'run', fail)
  with pytest.raises(subprocess.CalledProcessError):
    native.prepare(tmp_path, download, lambda p: None)
  assert not native.ready(tmp_path)
  assert downloads == [(native.MODEL_URL, native.MODEL_SHA256), (native.SOURCE_URL, native.SOURCE_SHA256)]

  def build(command, **kwargs):
    if '--build' in command:
      binary = Path(command[command.index('--build') + 1]) / 'bin' / 'whisper-cli'
      binary.parent.mkdir(parents=True)
      binary.write_bytes(b'runner')
      binary.chmod(0o755)

  monkeypatch.setattr(native.subprocess, 'run', build)
  native.prepare(tmp_path, download, lambda p: None)
  assert native.ready(tmp_path)
  assert not list(native.executable(tmp_path).parent.glob('*.part'))


@pytest.mark.skipif(not sys.platform.startswith('linux'), reason='Linux parent-death signal')
def test_native_runner_ends_if_its_worker_is_killed(tmp_path):
  child_pid = tmp_path / 'child.pid'
  child = f'import os,time; open({str(child_pid)!r}, "w").write(str(os.getpid())); time.sleep(30)'
  worker = ('import subprocess,sys,os,time; ' +
            f'subprocess.Popen([sys.executable,{str(Path(native.__file__))!r},"--exec",str(os.getpid()),' +
            f'sys.executable,"-c",{child!r}]); time.sleep(30)')
  process = subprocess.Popen([sys.executable, '-c', worker])
  try:
    end = time.monotonic() + 5
    while not child_pid.exists() and time.monotonic() < end:
      time.sleep(0.02)
    assert child_pid.exists()
    pid = int(child_pid.read_text())
    process.kill()
    process.wait(timeout=5)
    end = time.monotonic() + 5
    while time.monotonic() < end:
      stat = Path(f'/proc/{pid}/stat')
      if not stat.exists() or stat.read_text().split()[2] == 'Z':
        break
      time.sleep(0.02)
    else:
      pytest.fail('native runner survived its worker')
  finally:
    if process.poll() is None:
      process.kill()
    process.wait(timeout=5)
