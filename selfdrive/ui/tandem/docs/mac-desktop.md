# Run the desktop UI on macOS

The repository's `c3` and `c4` executables are shell launchers. They build the native Mac libraries they need, then run the real Python/raylib UI from this checkout.

| Launcher | UI | Use it for |
| --- | --- | --- |
| `./c3` | Large screen (`BIG=1`) | Tandem's Essentials home, settings and driving screens. |
| `./c4` | Small screen (`BIG=0`) | Upstream's small-screen UI. Essentials currently integrates with the large UI. |

Verified on an Apple Silicon Mac running macOS 27.2, with Python 3.11.13 and uv 0.13.6 on November 2, 2026. Both launchers built their native runtime and started the UI. Intel Macs have not been verified with this guide.

## 1. Install the Mac tools

Install Apple's [Command Line Tools](https://developer.apple.com/documentation/xcode/installing-the-command-line-tools/), then finish the installer before continuing:

```sh
xcode-select --install
```

If they are already installed, check the selected developer directory with `xcode-select -p`.

Install [Homebrew](https://brew.sh/) if needed and follow its instructions to put `brew` on your shell's `PATH`. Use native Apple Silicon Homebrew on an Apple Silicon Mac. Install the host dependencies and [uv](https://docs.astral.sh/uv/getting-started/installation/):

```sh
HOMEBREW_NO_INSTALL_CLEANUP=1 brew install \
  uv capnp coreutils eigen glfw libtool libusb pkgconf portaudio zeromq
```

The launchers select Apple's Clang on macOS. A device sysroot, ARM cross compiler and Homebrew LLVM are not needed for this desktop UI setup.

## 2. Create the Python environment

For a new checkout:

```sh
git clone --branch release https://github.com/jfgordon2/Tandem.git
cd Tandem
```

For an existing checkout, open a terminal in its repository root instead. Then run:

```sh
uv sync --frozen --all-extras --python 3.11
```

Use Python 3.11 for this setup. The project allows 3.11 and 3.12, but its native dependency selection differs between them. uv can download the requested Python version automatically. `--frozen` uses the committed `uv.lock`; `--all-extras` matches what the desktop launchers install.

This creates `.venv/` in the repository. Leave it in place: the host runner uses its Python interpreter to create its separate desktop environment. You do not need to activate either environment before running a launcher.

## 3. Launch the UI

From the repository root:

```sh
./c3 8
```

The optional number is the build job count. The first run synchronizes a host copy of the checkout, installs its Python environment, and compiles the Mac extensions. It can take several minutes. Once ready, a window titled **UI** opens with Tandem's large-screen interface.

Close the window or press Ctrl+C in the launching terminal before switching to the small UI:

```sh
./c4 8
```

Both launchers use the same host cache and lock, so a second launch waits while the first is running. `./dev c3 8` and `./dev c4 8` are equivalent commands.

The window automatically scales to the display. To choose a scale explicitly:

```sh
SCALE=0.6 ./c3 8
```

These commands start a desktop preview without driving hardware. The launchers seed local setup values and themes, and provide fake Wi-Fi and Bluetooth state. c3 also provides sample drive statistics. A road video and live lead/path data require a replay or another message source; opening `./c3` alone does not supply them. The repository's `./onroad` launcher is the separate replay workflow.

## Check the build without opening a window

```sh
SP_C3_COMPILE_ONLY=1 ./c3 8
SP_C4_COMPILE_ONLY=1 ./c4 8
```

A successful command exits with `C3 runtime artifacts prepared.` or `C4 runtime artifacts prepared.` This verifies the native runtime imports; it does not check the appearance of a screen. The runner cleans up its native outputs on exit. To retain them in the isolated host cache for a separate native test run, use `SP_KEEP_DESKTOP_RUNTIME_ARTIFACTS=1 SP_C3_COMPILE_ONLY=1 ./c3 8`.

For the owned Galaxy HTTP tests, also install the small test dependency set into the host environment after the build:

```sh
uv pip install --python .host_runtime/darwin/venv/bin/python -r selfdrive/ui/tandem/tests/requirements.txt
```

## Development workflow and local files

Edit files in your normal checkout, then close and relaunch the UI to pick up changes. Each launch copies the current source, including uncommitted changes, into the host cache. Avoid editing that generated copy directly.

| Location | Purpose |
| --- | --- |
| `.venv/` | Root Python environment created by `uv sync`. |
| `.host_runtime/darwin/worktree/` | Generated source copy and Mac build artifacts. |
| `.host_runtime/darwin/venv/` | Python environment used by the desktop UI. |
| `.host_runtime/darwin/scons_cache/` | Compiled artifacts reused on later launches. |
| `~/.comma/` | Default desktop settings, themes, logs and other runtime state. Shared by desktop tools unless `OPENPILOT_PREFIX` is set. |

The repository ignores `.venv/` and `.host_runtime/`. Mac extension builds happen inside the host cache, preserving the device binaries in the main checkout. `./build` is the separate device build command.

The storage meter uses the Mac's home filesystem for total and free space. Its data categories still measure the device's `/data` folders, so those categories are empty on a Mac without those folders. Hardware actions and device file operations need a device for verification.

## Troubleshooting

- **`Missing .venv` or `Missing uv`:** check `command -v uv`, then run the Python setup command from the repository root.
- **`capnpc` not found or missing `zmq.h`:** complete the Homebrew dependency installation and make sure Homebrew's `bin` directory is on `PATH`.
- **An extension reports ELF, an incompatible architecture, or a missing module:** launch through `./c3` or `./c4`. Running `python selfdrive/ui/ui.py` directly from the root environment can load the committed Linux/device extensions. The wrappers rebuild and load Mac versions from their host cache.
- **`Waiting for host runtime lock`:** close the other desktop command using that cache. The runner removes a stale lock automatically once its owning process has exited.
- **SDK headers cannot be found:** check `xcode-select -p` and `xcrun --show-sdk-path`; finish or repair the Command Line Tools installation before rebuilding.
- **c4 still shows upstream branding or a different layout:** c4 runs upstream's small-screen UI. Use c3 to work on Tandem Essentials.

For road replay, additional native dependencies are needed, including FFmpeg; that workflow is separate from the c3/c4 UI setup described here. The broader upstream [`tools/mac_setup.sh`](../../../../tools/mac_setup.sh) also configures device and other development tooling.
