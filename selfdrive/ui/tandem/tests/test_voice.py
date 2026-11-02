"""Voice typing: the worker's audio and word handling (speech.py), the session that follows it (voice.py), and the mic key.

The full checkpoint needs a 75 MB download; a small synthetic model tests decoder precision here instead.
speech.py --file runs the full model on a recording."""
import json
import io
import sys
import threading
import time

import numpy as np
import pytest

from openpilot.selfdrive.ui.tandem import keyboard as K, speech, voice


@pytest.fixture(autouse=True)
def speech_cache(tmp_path, monkeypatch):
  monkeypatch.setenv("TANDEM_SPEECH_DIR", str(tmp_path))


# ---- speech.py ----

def test_level_maps_quiet_to_zero_and_loud_to_one():
  assert speech.level(np.zeros(800, np.float32)) == 0.0
  assert speech.level(np.full(800, 0.5, np.float32)) == 1.0
  assert 0.2 < speech.level(np.full(800, 0.01, np.float32)) < 0.4          # -40 dB


def _feed(ends, levels):
  for value in levels:
    if reason := ends.add(value):
      return reason
  return None


def test_listening_ends_after_a_pause_once_someone_spoke():
  ends = speech.Endpointer(block_s=0.05)
  assert _feed(ends, [0.0] * 20 + [0.5] * 20) is None            # quiet, then talking
  assert _feed(ends, [0.0] * 29) is None                          # a short pause between words
  assert ends.add(0.0) == "pause"                                 # 1.5 s of quiet


def test_listening_gives_up_without_speech_and_has_a_limit():
  assert _feed(speech.Endpointer(block_s=0.05), [0.0] * 200) == "no_speech"
  assert _feed(speech.Endpointer(block_s=0.05), [0.5] * 400) == "max"


def test_spectrogram_is_whispers_shape():
  filters = speech.mel_filters()
  assert filters.shape == (80, 201) and filters.min() >= 0
  tone = (0.3 * np.sin(2 * np.pi * 440 * np.arange(32000) / 16000)).astype(np.float32)
  spec = speech.log_mel(tone)
  assert spec.shape == (1, 80, 3000) and spec.dtype == np.float32
  assert spec.max() - spec.min() <= 2.0 + 1e-6                    # Whisper clips to 8 decades, scaled by 4


def test_vocab_decodes_bytes_and_finds_the_special_tokens(tmp_path):
  import base64
  pieces = [b"hard", b"ware", b" store", "é".encode()]
  (tmp_path / "v.tiktoken").write_text("".join(f"{base64.b64encode(p).decode()} {i}\n" for i, p in enumerate(pieces)))
  vocab = speech.Vocab(tmp_path / "v.tiktoken")
  assert (vocab.eot, vocab.sot) == (4, 5)
  assert vocab.no_timestamps == 4 + 106                           # 50362 with GPT-2's 50256 pieces
  assert vocab.start_of_prev == 4 + 104                           # 50360
  assert vocab.decode([0, 1, 2, vocab.eot, vocab.sot]) == "hardware store"
  assert vocab.decode([3]) == "é"


def test_clean_drops_whisper_habits():
  assert speech.clean(" Hardware store.") == "Hardware store"
  assert speech.clean("Thank you.") == ""
  assert speech.clean("you") == ""
  assert speech.clean("1 Main St. Springfield") == "1 Main St. Springfield"


@pytest.mark.parametrize("spoken, typed", [
  ("1, 2, 3 First Street, New York, New York", "123 1st Street, New York, New York"),
  ("one two three first street new york new york", "123 1st street new york new york"),
  ("One oh five Main St", "105 Main St"),
  ("1-2-3 Second Avenue", "123 2nd Avenue"),
  ("123 First Street, New York, NY", "123 1st Street, New York, NY"),
  ("Twelfth Street", "12th Street"),
  ("2 Broadway", "2 Broadway"),                                   # one digit is already a number
  ("5-10 Main", "5-10 Main"),                                     # not single digits
  ("Oh my burger", "Oh my burger"),                               # "oh" is zero only inside a number
  ("First Watch", "First Watch"),                                 # a name, not a street
])
def test_addresses_read_as_typed(spoken, typed):
  assert speech.address_text(spoken) == typed


def test_address_prompt_is_plain_gpt2_tokens():
  assert 0 < len(speech.ADDRESS_PROMPT) < 64 and all(0 <= t < 50256 for t in speech.ADDRESS_PROMPT)


def test_record_stops_on_a_pause_and_on_stop(capsys):
  def stream_of(levels):
    class Stream:
      def __init__(self, callback):
        self._callback = callback

      def __enter__(self):
        def run():
          for amp in levels:
            self._callback(np.full((speech.BLOCK, 1), amp, np.float32), speech.BLOCK, None, None)
        threading.Thread(target=run, daemon=True).start()
        return self

      def __exit__(self, *_):
        return False
    return Stream

  samples = speech.record(threading.Event(), stream_of([0.0] * 5 + [0.3] * 10 + [0.0] * 40))
  assert samples is not None and samples.size == speech.BLOCK * 45    # stopped 1.5 s into the pause
  lines = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
  assert lines[0] == {"state": "listening"} and all("level" in line for line in lines[1:])

  stop = threading.Event()
  stop.set()
  assert speech.record(stop, stream_of([0.3] * 10)).size == 0

  def broken(callback):
    raise OSError("no device")
  assert speech.record(threading.Event(), broken) is None
  assert "OSError: no device" in capsys.readouterr().err


@pytest.mark.parametrize("stage", ["load", "transcribe"])
def test_worker_failures_keep_a_traceback_and_report_failure(stage, monkeypatch, capsys):
  monkeypatch.setattr(speech, "model_ready", lambda folder=None: True)
  monkeypatch.setattr(speech, "record", lambda stop: np.ones(800, dtype=np.float32))
  monkeypatch.setattr(speech.sys, "stdin", io.StringIO("stop\n"))
  monkeypatch.setattr(speech, "load", lambda folder: (object(), object()))

  def broken(*args, **kwargs):
    raise RuntimeError(f"synthetic {stage} failure")

  monkeypatch.setattr(speech, stage, broken)
  assert speech.main() == 1
  output = capsys.readouterr()
  assert f"RuntimeError: synthetic {stage} failure" in output.err
  assert json.loads(output.out.splitlines()[-1])["error"] == "failed"


def test_half_precision_checkpoint_keeps_decoder_normalization_in_float32(tmp_path, monkeypatch):
  monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
  from tinygrad import Context, Tensor, dtypes
  from tinygrad.nn.state import get_state_dict

  dims = dict(n_mels=2, n_audio_ctx=3, n_audio_state=4, n_audio_head=2, n_audio_layer=1,
              n_vocab=8, n_text_ctx=8, n_text_state=4, n_text_head=2, n_text_layer=1)
  with Context(DEV="CPU", PARALLEL=0):
    model = speech.build_model({"dims": dims, "model_state_dict": {}})
    for key, value in get_state_dict(model).items():
      if key != "decoder.mask":
        value.replace(Tensor.full(value.shape, 0.01, dtype=dtypes.float16).realize())
    normalization = model.decoder.blocks[0].attn_ln
    seen = []

    def normalize(x):
      seen.append(x.dtype)
      return normalization(x)

    model.decoder.blocks[0].attn_ln = normalize
    audio = Tensor.full((1, 3, 4), 0.2, dtype=dtypes.float32)
    for position in (0, 2, 3):
      tokens = [[0, 1]] if position == 0 else [[1]]
      output = model.decoder(Tensor(tokens, dtype=dtypes.int32), position, audio).numpy()
      assert output.shape == (1, len(tokens[0]), 8) and np.isfinite(output).all()
    assert seen and all(dtype == dtypes.float32 for dtype in seen)


# ---- voice.py ----

def _worker(*lines, linger=0.0):
  script = "import json,time\n" + "".join(f"print({line!r}, flush=True)\ntime.sleep(0.02)\n" for line in lines)
  return [sys.executable, "-c", script + f"time.sleep({linger})\n"]


def _until(session, done, timeout=5.0):
  end = time.monotonic() + timeout
  while time.monotonic() < end:
    session.update()
    if done():
      return True
    time.sleep(0.02)
  return False


@pytest.fixture
def ready(monkeypatch):
  monkeypatch.setattr(speech, "model_ready", lambda folder=None: True)


def test_session_follows_the_worker_to_the_words(ready):
  heard = []
  lines = [json.dumps({"state": "listening"}), json.dumps({"level": 0.7}), json.dumps({"state": "transcribing"}),
           json.dumps({"text": "hardware store"})]
  session = voice.VoiceTyping(heard.append, _worker(*lines))
  session.start()
  assert session.state == "listening"
  assert _until(session, lambda: heard)
  assert heard == ["hardware store"] and session.state == "idle" and 0.7 in session.levels


def test_session_shows_download_progress_and_errors(monkeypatch):
  monkeypatch.setattr(speech, "model_ready", lambda folder=None: False)
  session = voice.VoiceTyping(lambda text: None, _worker(json.dumps({"state": "download", "progress": 0.42}),
                                                         json.dumps({"error": "no_speech"})))
  session.start()
  assert session.state == "download"
  assert _until(session, lambda: session.state == "message")
  assert session.message == voice.ERRORS["no_speech"]


def test_a_worker_that_dies_says_so(ready):
  session = voice.VoiceTyping(lambda text: None, [sys.executable, "-c", "raise SystemExit(1)"])
  session.start()
  assert _until(session, lambda: session.state == "message")
  assert session.message == voice.ERRORS["failed"]


def test_type_instead_and_closing_the_page_end_the_worker(ready, monkeypatch):
  session = voice.VoiceTyping(lambda text: None, _worker(json.dumps({"state": "listening"}), linger=30))
  session.start()
  process = session._process
  session.cancel()
  assert session.state == "idle" and process.wait(timeout=5) is not None

  monkeypatch.setattr(voice, "UNSEEN_S", 0.2)
  session.start()
  process = session._process                                      # nothing calls update(): the panel isn't drawn
  assert process.wait(timeout=5) is not None and session.state == "idle"


# ---- the mic key ----

@pytest.fixture
def keyboard(monkeypatch):
  monkeypatch.setattr(K.upstream, "Label", lambda *a, **k: None)
  monkeypatch.setattr(K.upstream, "Button", lambda *a, **k: None)
  monkeypatch.setattr(K.upstream.gui_app, "texture", lambda *a, **k: None)
  monkeypatch.setattr(voice, "available", lambda: True)
  started = []
  monkeypatch.setattr(voice.VoiceTyping, "start", lambda self: started.append(self))
  return started


def test_mic_key_only_for_plain_text_while_parked(keyboard, monkeypatch):
  assert K.EssentialsKeyboard().voice_offered()
  assert not K.EssentialsKeyboard(password_mode=True, show_password_toggle=True).voice_offered()
  monkeypatch.setattr(voice, "available", lambda: False)
  assert not K.EssentialsKeyboard().voice_offered()


def test_mic_key_starts_voice_typing_and_words_land_after_the_text(keyboard):
  pad = K.KeyPad(lambda: None, "Search", voice_hint="Say a place")
  pad._all_keys[K.MIC]._click_callback()
  assert keyboard == [pad._voice] and pad.text == ""              # the key types nothing itself
  pad._insert_spoken("hardware store")
  assert pad.text == "hardware store"
  pad.set_text("near ")
  pad._insert_spoken("the lake")
  assert pad.text == "near the lake"
  assert pad._voice_panel.hint == "Say a place"

  kb = K.EssentialsKeyboard()
  kb._all_keys[K.MIC]._click_callback()
  assert keyboard[-1] is kb._voice and kb.text == ""
  assert kb._voice._command[-2:] == ["--style", "text"]
  assert K.KeyPad(lambda: None, "Search", voice_style="address")._voice._command[-2:] == ["--style", "address"]


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="Linux scheduling")
def test_worker_runs_as_a_background_job_not_at_the_uis_priority(ready, tmp_path, monkeypatch):
  """The UI is SCHED_FIFO on one core; a worker that kept that would freeze it while the model loads."""
  import os
  monkeypatch.setenv("TANDEM_SPEECH_DIR", str(tmp_path))
  probe = "\n".join(["import os, json", "print(json.dumps({'policy': os.sched_getscheduler(0), 'nice': os.getpriority(os.PRIO_PROCESS, 0),",
                     "  'cpus': len(os.sched_getaffinity(0))}), flush=True)"])
  seen = []
  session = voice.VoiceTyping(lambda text: None, [sys.executable, "-c", probe])
  monkeypatch.setattr(session, "_handle", lambda line: seen.append(json.loads(line)))
  session.start()
  assert _until(session, lambda: seen)
  assert seen[0]["policy"] == os.SCHED_OTHER and seen[0]["nice"] >= 10 and seen[0]["cpus"] == os.cpu_count()
  assert (tmp_path / "worker.log").exists()                       # the worker's errors land here
