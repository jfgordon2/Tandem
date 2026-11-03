"""On-device speech to text for the keyboard's mic key: Whisper tiny.en.

It runs as its own process (python3 speech.py, by path: the package would load raylib), so the UI never loads tinygrad or opens the
microphone itself, and the UI keeps drawing while it works. voice.py starts it and reads what it prints, one JSON object a
line:

  {"state": "download", "progress": 0.42}   first use only: fetching the model (75 MB) and its word list
  {"state": "listening"}                     the microphone is open
  {"level": 0.31}                            how loud it is, about 20 times a second
  {"state": "transcribing"}                  done listening; the model is working
  {"text": "hardware store"}                 the words, then it exits
  {"error": "no_speech" | "no_mic" | "download" | "failed"}

"--style address" (the destination field) primes Whisper with an example address and tidies house numbers and
street ordinals (address_text). A line "stop" on its stdin ends listening early. Listening also ends after a pause once someone has spoken, after
NO_SPEECH_S of quiet, or at MAX_S. The model loads while the person speaks.

The comma uses whisper.cpp's native CPU runner (speech_native.py); tinygrad remains available with
TANDEM_SPEECH_BACKEND=tinygrad. The fallback model is from tinygrad's examples/whisper.py (MIT, after openai/whisper), kept here because release
builds don't ship tinygrad's examples. The spectrogram and the word list need neither librosa nor tiktoken.
"""
from __future__ import annotations

import base64
import collections
import hashlib
import json
import os
import queue
import re
import sys
import threading
import time
import traceback
import urllib.request
from pathlib import Path



def relax_priority() -> None:
  """Run as an ordinary background job. Started from the UI, this process inherits the UI's real-time priority and its
  one CPU core, and loading the model would then stop the UI drawing until it finished."""
  if not sys.platform.startswith("linux"):
    return
  try:
    os.sched_setscheduler(0, os.SCHED_OTHER, os.sched_param(0))
  except (OSError, AttributeError):
    pass
  try:
    os.sched_setaffinity(0, range(os.cpu_count() or 1))
  except (OSError, AttributeError):
    pass
  try:
    os.setpriority(os.PRIO_PROCESS, 0, 10)
  except (OSError, AttributeError):
    pass


DRIVING = os.environ.get("TANDEM_SPEECH_DRIVING") == "1"   # voice.py sets it when the car is on
DRIVING_CORES = {0, 1, 2, 3}             # away from controlsd and card (4), plannerd, radard and selfdrived (5) and modeld (7)
DRIVING_THREADS = 2


def driving_limits() -> None:
  """While driving: fewer threads, on the cores openpilot's control loop and driving model don't use. They run at real-time
  priority and would win anyway; this keeps memory traffic and heat down too."""
  os.environ.setdefault("TANDEM_SPEECH_THREADS", str(DRIVING_THREADS))
  if sys.platform.startswith("linux"):
    try:
      cores = DRIVING_CORES & set(os.sched_getaffinity(0))
      if cores:
        os.sched_setaffinity(0, cores)
    except (OSError, AttributeError):
      pass


if __name__ == "__main__":
  relax_priority()                        # before numpy and tinygrad load
  if sys.argv[1:2] == ["--exec"]:
    # The UI starts this fresh process instead of running Python callbacks between fork and exec.
    os.execv(sys.argv[2], sys.argv[2:])
  if DRIVING:
    driving_limits()

import numpy as np

RATE = 16000
N_FFT, HOP, N_MELS = 400, 160, 80
SEGMENT = RATE * 30                       # the model always hears 30 seconds; shorter speech is padded with silence
BLOCK = 800                               # 50 ms of audio per level reading

SILENCE_AFTER_S = 1.5                     # stop this long after the person stops talking
NO_SPEECH_S = 6.0                         # stop if nobody has said anything by now
FIRST_AUDIO_S = 2.0                       # no audio at all by then: the microphone isn't reaching us
MAX_S = 15.0
SPEECH_LEVEL = 0.06                       # a level (0..1, see level()) that counts as talking

MODEL_SHA256 = "d3dd57d32accea0b295c96e26691aa14d8822fac7d9d27d5dc00b4ca2826dd03"
MODEL_URL = f"https://openaipublic.azureedge.net/main/whisper/models/{MODEL_SHA256}/tiny.en.pt"
VOCAB_URL = "https://raw.githubusercontent.com/openai/whisper/main/whisper/assets/gpt2.tiktoken"
N_LANGUAGES = 99                          # the language tokens between <|startoftranscript|> and <|translate|>


def model_dir() -> Path:
  if os.environ.get("TANDEM_SPEECH_DIR"):
    return Path(os.environ["TANDEM_SPEECH_DIR"])
  return Path("/data/tandem/speech") if Path("/data").is_dir() and os.access("/data", os.W_OK) else Path.home() / ".comma/tandem/speech"


def native_backend():
  """The native CPU runner on the comma; keep tinygrad available for diagnostics and PC previews."""
  if os.environ.get("TANDEM_SPEECH_BACKEND", "native" if Path("/TICI").is_file() else "tinygrad") != "native":
    return None
  if __package__:
    from openpilot.selfdrive.ui.tandem import speech_native
  else:
    import speech_native
  return speech_native


def model_ready(folder: Path | None = None) -> bool:
  folder = folder or model_dir()
  if native := native_backend():
    return native.ready(folder)
  return (folder / "tiny.en.pt").is_file() and (folder / "gpt2.tiktoken").is_file()


def say(**message) -> None:
  print(json.dumps(message), flush=True)


def report_error(kind: str, error: Exception) -> None:
  """Keep the traceback in worker.log as well as the short protocol error the keyboard follows."""
  traceback.print_exception(error, file=sys.stderr)
  say(error=kind, detail=str(error)[:200])


# ---- audio ----

def level(block: np.ndarray) -> float:
  """How loud a block of samples (-1..1) is, 0..1: RMS in dB, mapped from -60 dB (quiet room) to -10 dB (speaking up close)."""
  rms = float(np.sqrt(np.mean(np.square(block, dtype=np.float64)))) if block.size else 0.0
  db = 20 * np.log10(max(rms, 1e-9))
  return float(np.clip((db + 60) / 50, 0.0, 1.0))


class Endpointer:
  """Decides when listening is over from the levels so far: a pause after speech, nothing said at all, or too long."""

  def __init__(self, block_s: float = BLOCK / RATE):
    self.block_s = block_s
    self.elapsed = 0.0
    self.heard = False
    self.quiet = 0.0

  def add(self, value: float) -> str | None:
    """Feed one block's level; returns why to stop ("pause", "no_speech", "max"), or None to keep listening."""
    self.elapsed += self.block_s
    if value >= SPEECH_LEVEL:
      self.heard, self.quiet = True, 0.0
    else:
      self.quiet += self.block_s
    if self.heard and self.quiet >= SILENCE_AFTER_S:
      return "pause"
    if not self.heard and self.elapsed >= NO_SPEECH_S:
      return "no_speech"
    return "max" if self.elapsed >= MAX_S else None


def mel_filters(sr: int = RATE, n_fft: int = N_FFT, n_mels: int = N_MELS) -> np.ndarray:
  """librosa's Slaney mel filterbank (what Whisper was trained on), (n_mels, n_fft // 2 + 1)."""
  def hz_to_mel(f):
    f = np.asarray(f, dtype=np.float64)
    lin = f / (200.0 / 3)
    return np.where(f >= 1000.0, 15.0 + np.log(np.maximum(f, 1e-10) / 1000.0) / (np.log(6.4) / 27.0), lin)

  def mel_to_hz(m):
    m = np.asarray(m, dtype=np.float64)
    lin = m * (200.0 / 3)
    return np.where(m >= 15.0, 1000.0 * np.exp((np.log(6.4) / 27.0) * (m - 15.0)), lin)

  fft_f = np.linspace(0, sr / 2, n_fft // 2 + 1)
  mel_f = mel_to_hz(np.linspace(hz_to_mel(0.0), hz_to_mel(sr / 2), n_mels + 2))
  fdiff = np.diff(mel_f)
  ramps = mel_f[:, None] - fft_f[None, :]
  lower = -ramps[:-2] / fdiff[:-1, None]
  upper = ramps[2:] / fdiff[1:, None]
  weights = np.maximum(0, np.minimum(lower, upper))
  weights *= (2.0 / (mel_f[2:n_mels + 2] - mel_f[:n_mels]))[:, None]
  return weights.astype(np.float32)


def log_mel(samples: np.ndarray) -> np.ndarray:
  """Whisper's input: 30 s of 16 kHz audio as an (1, 80, 3000) log-mel spectrogram, as librosa.stft would make it."""
  audio = np.zeros(SEGMENT, dtype=np.float32)
  audio[:min(len(samples), SEGMENT)] = samples[:SEGMENT]
  padded = np.pad(audio, N_FFT // 2, mode="reflect")
  window = (0.5 - 0.5 * np.cos(2 * np.pi * np.arange(N_FFT) / N_FFT)).astype(np.float32)   # periodic Hann
  frames = np.lib.stride_tricks.sliding_window_view(padded, N_FFT)[::HOP]
  power = np.abs(np.fft.rfft(frames * window, axis=-1)) ** 2          # (3001, 201)
  spec = mel_filters() @ power[:-1].T                                  # (80, 3000)
  logs = np.log10(np.maximum(spec, 1e-10))
  logs = np.maximum(logs, logs.max() - 8.0)
  return ((logs + 4.0) / 4.0)[None].astype(np.float32)


# ---- words ----

class Vocab:
  """GPT-2's byte-pair ranks (gpt2.tiktoken) turned back into text. Decoding is a lookup, so tiktoken isn't needed."""

  def __init__(self, path: Path):
    self.pieces: dict[int, bytes] = {}
    for line in path.read_text().splitlines():
      if line.strip():
        token, rank = line.split()
        self.pieces[int(rank)] = base64.b64decode(token)
    self.eot = len(self.pieces)                    # <|endoftext|>, the first special token
    self.sot = self.eot + 1
    # after the languages: translate, transcribe, startoflm, startofprev, nospeech, then notimestamps (50362 for English)
    self.no_timestamps = self.sot + 1 + N_LANGUAGES + 5
    self.start_of_prev = self.sot + 1 + N_LANGUAGES + 3     # the text before, to prime the words (50360 for English)

  def decode(self, tokens) -> str:
    return b"".join(self.pieces.get(int(t), b"") for t in tokens if int(t) < self.eot).decode("utf-8", errors="replace").strip()


def clean(text: str) -> str:
  """Whisper's habits that don't belong in a text field: a closing period on a short phrase, and its silence fillers."""
  text = " ".join(text.split())
  if text.lower().strip(" .!") in {"", "you", "thank you", "thanks for watching", "[blank_audio]", "[silence]"}:
    return ""
  if text.endswith(".") and not text.endswith("..") and text.count(".") == 1:
    text = text[:-1]
  return text


# Addresses (the destination field). Whisper already writes "one twenty three" as 123; these fix what it leaves.
# ADDRESS_PROMPT is GPT-2's tokens for " 123 First Street, New York, NY 10003. 4500 Main St, Des Moines, IA.", made
# once with tiktoken: given as the text before, it nudges Whisper toward digits, commas and state codes.
ADDRESS_PROMPT = [17031, 3274, 3530, 11, 968, 1971, 11, 6645, 8576, 18, 13, 604, 4059, 8774, 520, 11, 2935, 36576, 11, 35229, 13]
DIGITS = {"zero": "0", "one": "1", "two": "2", "three": "3", "four": "4", "five": "5", "six": "6", "seven": "7", "eight": "8",
          "nine": "9"}
ORDINALS = ["first", "second", "third", "fourth", "fifth", "sixth", "seventh", "eighth", "ninth", "tenth", "eleventh", "twelfth",
            "thirteenth", "fourteenth", "fifteenth", "sixteenth", "seventeenth", "eighteenth", "nineteenth", "twentieth"]
STREET_TYPES = {"street", "st", "avenue", "ave", "road", "rd", "boulevard", "blvd", "drive", "dr", "lane", "ln", "place", "pl", "court",
                "ct", "way", "terrace", "parkway", "pkwy"}


def _ordinal(n: int) -> str:
  return f"{n}{'th' if 11 <= n % 100 <= 13 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def address_text(text: str) -> str:
  """A spoken address as people type it: a house number said digit by digit ("1, 2, 3" or "one two three", with "oh"
  for zero after the first digit) becomes 123, and "First Street" becomes "1st Street"."""
  words = [part for word in text.split()             # "1-2-3" is three digits
           for part in (word.strip(",.").split("-") if re.fullmatch(r"\d(-\d)+[,.]?", word) else [word])]
  digits, used = "", 0
  for word in words:
    bare = word.strip(",.-").lower()
    digit = bare if len(bare) == 1 and bare.isdigit() else DIGITS.get(bare, "0" if bare == "oh" and digits else None)
    if digit is None:
      break
    digits += digit
    used += 1
  if used >= 2:                                    # the commas or hyphens between the digits go too
    words = [digits, *words[used:]]
  for i in range(len(words) - 1):
    bare = words[i].strip(",.").lower()
    if bare in ORDINALS and words[i + 1].strip(",.").lower() in STREET_TYPES:
      words[i] = _ordinal(ORDINALS.index(bare) + 1) + words[i][len(words[i].rstrip(",.")):]
  return " ".join(words)


# ---- model (tinygrad examples/whisper.py) ----

def build_model(state):
  from tinygrad import Tensor, TinyJit, Variable, nn

  class Attention:
    def __init__(self, n_state, n_head, cache=None, max_len=None):
      self.n_head, self.cache, self.max_len = n_head, cache, max_len
      self.query, self.key, self.value, self.out = nn.Linear(n_state, n_state), nn.Linear(n_state, n_state, bias=False), \
        nn.Linear(n_state, n_state), nn.Linear(n_state, n_state)

    def __call__(self, x, xa=None, mask=None, pos=None):
      if self.cache == "cross":
        if xa is not None:
          k, v = self.key(xa), self.value(xa)
          if not hasattr(self, "cache_k"):
            self.cache_k, self.cache_v = k, v
          else:
            self.cache_k.assign(k).realize()
            self.cache_v.assign(v).realize()
        else:
          k, v = self.cache_k, self.cache_v
      else:
        k, v = self.key(x), self.value(x)
        if self.cache == "self":
          if not hasattr(self, "cache_k"):
            self.cache_k = Tensor.zeros(x.shape[0], self.max_len, x.shape[2])
            self.cache_v = Tensor.zeros(x.shape[0], self.max_len, x.shape[2])
          k = self.cache_k.shrink((None, (0, pos), None)).cat(k, dim=1)
          v = self.cache_v.shrink((None, (0, pos), None)).cat(v, dim=1)
          padding = self.max_len - pos - x.shape[1]
          self.cache_k.assign(k.pad((None, (0, padding), None)).contiguous()).realize()
          self.cache_v.assign(v.pad((None, (0, padding), None)).contiguous()).realize()
      q = self.query(x)
      n_ctx, head = q.shape[1], q.shape[-1] // self.n_head
      q, k, v = (t.reshape(*t.shape[:2], self.n_head, head).permute(0, 2, 1, 3) for t in (q, k, v))
      attn = Tensor.scaled_dot_product_attention(q, k, v, mask[:n_ctx, :n_ctx] if mask is not None else None)
      return self.out(attn.permute(0, 2, 1, 3).flatten(start_dim=2))

  class Block:
    def __init__(self, n_state, n_head, decoder=False, max_len=None):
      self.attn = Attention(n_state, n_head, "self" if decoder else None, max_len)
      self.attn_ln = nn.LayerNorm(n_state)
      self.cross_attn = Attention(n_state, n_head, "cross") if decoder else None
      self.cross_attn_ln = nn.LayerNorm(n_state) if decoder else None
      self.mlp = [nn.Linear(n_state, n_state * 4), Tensor.gelu, nn.Linear(n_state * 4, n_state)]
      self.mlp_ln = nn.LayerNorm(n_state)

    def __call__(self, x, xa=None, mask=None, pos=None):
      x = x + self.attn(self.attn_ln(x), mask=mask, pos=pos)
      if self.cross_attn:
        x = x + self.cross_attn(self.cross_attn_ln(x), xa)
      return (x + self.mlp_ln(x).sequential(self.mlp)).realize()

  class Encoder:
    def __init__(self, n_mels, n_audio_ctx, n_audio_state, n_audio_head, n_audio_layer, **_):
      self.conv1 = nn.Conv1d(n_mels, n_audio_state, kernel_size=3, padding=1)
      self.conv2 = nn.Conv1d(n_audio_state, n_audio_state, kernel_size=3, stride=2, padding=1)
      self.blocks = [Block(n_audio_state, n_audio_head) for _ in range(n_audio_layer)]
      self.ln_post = nn.LayerNorm(n_audio_state)
      self.positional_embedding = Tensor.empty(n_audio_ctx, n_audio_state)

    def __call__(self, x):
      x = self.conv2(self.conv1(x).gelu()).gelu().permute(0, 2, 1)
      x = (x + self.positional_embedding[:x.shape[1]]).sequential(self.blocks)
      return self.ln_post(x).realize()

  class Decoder:
    def __init__(self, n_vocab, n_text_ctx, n_text_state, n_text_head, n_text_layer, **_):
      self.max_len = n_text_ctx
      self.token_embedding = nn.Embedding(n_vocab, n_text_state)
      self.positional_embedding = Tensor.empty(n_text_ctx, n_text_state)
      self.blocks = [Block(n_text_state, n_text_head, decoder=True, max_len=n_text_ctx) for _ in range(n_text_layer)]
      self.ln = nn.LayerNorm(n_text_state)
      self.mask = Tensor.full((n_text_ctx, n_text_ctx), -np.inf).triu(1).realize()
      self.jits = collections.defaultdict(lambda: TinyJit(self.forward))

    def __call__(self, x, pos, audio):
      bound = Variable("self_attn_cache_len", 1, self.max_len - 1).bind(pos) if pos else 0
      return self.jits[x.shape](x, bound, audio)

    def forward(self, x, pos, audio):
      # Keep decoder activations in float32 like the encoder's; half-precision reductions fail QCOM kernel verification.
      x = self.token_embedding(x).float() + self.positional_embedding.shrink(((pos, pos + x.shape[-1]), None))
      for block in self.blocks:
        x = block(x, xa=audio, mask=self.mask, pos=pos)
      return (self.ln(x) @ self.token_embedding.weight.T).realize()

  class Whisper:
    def __init__(self, dims):
      self.encoder, self.decoder = Encoder(**dims), Decoder(**dims)

  from tinygrad.nn.state import load_state_dict
  model = Whisper(state["dims"])
  load_state_dict(model, state["model_state_dict"], strict=False, verbose=False)
  return model


def load(folder: Path):
  if native := native_backend():
    return native.NativeWhisper(folder), None
  from tinygrad.nn.state import torch_load
  return build_model(torch_load(str(folder / "tiny.en.pt"))), Vocab(folder / "gpt2.tiktoken")


def transcribe(model, vocab: Vocab, samples: np.ndarray, max_tokens: int = 64, style: str = "text") -> str:
  """style "address" primes Whisper with ADDRESS_PROMPT and tidies the result with address_text()."""
  if native_backend() is not None:
    text = clean(model.transcribe(samples, style))
    return address_text(text) if style == "address" else text
  from tinygrad import Tensor, dtypes
  audio = model.encoder(Tensor(log_mel(samples)))
  prompt = [vocab.start_of_prev, *ADDRESS_PROMPT] if style == "address" else []
  tokens = [*prompt, vocab.sot, vocab.no_timestamps]
  start = len(tokens)
  ctx, pos = np.array([tokens], dtype=np.int32), 0
  for _ in range(max_tokens):
    logits = model.decoder(Tensor(ctx[:, pos:], dtype=dtypes.int32), pos, audio)[0, -1].numpy()
    nxt = int(np.argmax(logits[:vocab.eot + 1]))          # words or the end; never a timestamp or another special token
    if nxt == vocab.eot:
      break
    tokens.append(nxt)
    pos = ctx.shape[1]
    ctx = np.array([tokens], dtype=np.int32)
  text = clean(vocab.decode(tokens[start:]))
  return address_text(text) if style == "address" else text


# ---- first use ----

def download(url: str, dest: Path, on_progress, sha256: str | None = None) -> None:
  """Fetch url to dest through a .part file, so a cut-off download never looks finished."""
  dest.parent.mkdir(parents=True, exist_ok=True)
  part = dest.with_suffix(dest.suffix + ".part")
  digest = hashlib.sha256()
  with urllib.request.urlopen(url, timeout=30) as response, open(part, "wb") as out:
    total, done = int(response.headers.get("Content-Length") or 0), 0
    while chunk := response.read(1 << 16):
      out.write(chunk)
      digest.update(chunk)
      done += len(chunk)
      if total:
        on_progress(done / total)
  if sha256 and digest.hexdigest() != sha256:
    part.unlink(missing_ok=True)
    raise ValueError(f"{dest.name}: checksum mismatch")
  part.replace(dest)


def fetch_model(folder: Path) -> None:
  last = [-1.0]

  def report(share):
    if share - last[0] >= 0.01:
      last[0] = share
      say(state="download", progress=round(share, 3))

  say(state="download", progress=0.0)
  if native := native_backend():
    native.prepare(folder, download, report)
    return
  if not (folder / "gpt2.tiktoken").is_file():
    download(VOCAB_URL, folder / "gpt2.tiktoken", lambda p: None)
  if not (folder / "tiny.en.pt").is_file():
    download(MODEL_URL, folder / "tiny.en.pt", report, MODEL_SHA256)


# ---- the worker ----

def record(stop: threading.Event, open_stream=None) -> np.ndarray | None:
  """Listen until the endpointer or a "stop" says so, printing levels. None if no microphone opens."""
  blocks: queue.Queue = queue.Queue()

  def callback(indata, frames, at, status):
    blocks.put(indata[:, 0].copy())

  try:
    if open_stream is None:
      import sounddevice as sd
      def open_stream(cb):
        return sd.InputStream(channels=1, samplerate=RATE, blocksize=BLOCK, dtype="float32", callback=cb)
    stream = open_stream(callback)
  except Exception as error:
    traceback.print_exception(error, file=sys.stderr)
    return None
  heard, ends = [], Endpointer()
  opened = time.monotonic()
  with stream:
    say(state="listening")
    while not stop.is_set():
      try:
        block = blocks.get(timeout=0.5)
      except queue.Empty:
        if not heard and time.monotonic() - opened > FIRST_AUDIO_S:
          print("Speech: no audio arrived", file=sys.stderr, flush=True)
          return None
        continue
      heard.append(block)
      value = level(block)
      say(level=round(value, 3))
      reason = ends.add(value)
      if reason == "no_speech":
        return np.zeros(0, dtype=np.float32)
      if reason:
        break
  return np.concatenate(heard) if heard and ends.heard else np.zeros(0, dtype=np.float32)


class MicdStream:
  """While driving, openpilot's micd has the microphone and publishes what it hears (rawAudioData: 16 kHz int16, 800
  samples a message, the same blocks the recorder uses). Hand those to the recorder as the microphone would."""

  def __init__(self, callback):
    from cereal import messaging
    self._sock = messaging.sub_sock("rawAudioData", timeout=100)
    self._callback = callback
    self._running = False

  def __enter__(self):
    self._running = True
    threading.Thread(target=self._pump, daemon=True).start()
    return self

  def __exit__(self, *_):
    self._running = False
    return False

  def _pump(self) -> None:
    from cereal import messaging
    while self._running:
      msg = messaging.recv_one(self._sock)
      if msg is None:
        continue
      data = np.frombuffer(msg.rawAudioData.data, dtype=np.int16).astype(np.float32) / 32768.0
      if data.size:
        self._callback(data.reshape(-1, 1), data.size, None, None)


def main(style: str = "text") -> int:
  folder = model_dir()
  if not model_ready(folder):
    try:
      fetch_model(folder)
    except Exception as e:
      report_error("download", e)
      return 1

  loaded: dict = {}

  def load_model():
    try:
      loaded["model"] = load(folder)
    except Exception as e:
      loaded["error"] = e

  loader = threading.Thread(target=load_model, daemon=True)
  loader.start()                                   # the model loads while the person speaks

  stop = threading.Event()

  def watch_stdin():
    for line in sys.stdin:
      if line.strip() == "stop":
        stop.set()
    stop.set()

  threading.Thread(target=watch_stdin, daemon=True).start()
  samples = record(stop, MicdStream if DRIVING else None)
  if samples is None:
    say(error="no_audio_driving" if DRIVING else "no_mic")
    return 1
  if samples.size == 0:
    say(error="no_speech")
    return 0
  say(state="transcribing")
  started = time.monotonic()
  loader.join()
  if "error" in loaded:
    report_error("failed", loaded["error"])
    return 1
  try:
    text = transcribe(*loaded["model"], samples, style=style)
  except Exception as e:
    report_error("failed", e)
    return 1
  mode = f"{'driving' if DRIVING else 'parked'}, {os.environ.get('TANDEM_SPEECH_THREADS', 'default')} threads"
  print(f"Speech transcription: {time.monotonic() - started:.3f} s ({mode})", file=sys.stderr, flush=True)
  say(text=text) if text else say(error="no_speech")
  return 0


if __name__ == "__main__":
  t0 = time.monotonic()
  if sys.argv[1:2] == ["--prepare"]:
    if not model_ready():
      fetch_model(model_dir())
    sys.exit(0)
  if len(sys.argv) > 1 and sys.argv[1] == "--file":       # for testing: transcribe a 16 kHz mono float32 .npy file
    folder = model_dir()
    if not model_ready(folder):
      fetch_model(folder)
    style = sys.argv[3] if len(sys.argv) > 3 else "text"   # e.g. --file clip.npy address
    print(transcribe(*load(folder), np.load(sys.argv[2]), style=style), f"({time.monotonic() - t0:.1f} s)")
    sys.exit(0)
  sys.exit(main(sys.argv[2] if len(sys.argv) > 2 and sys.argv[1] == "--style" else "text"))
