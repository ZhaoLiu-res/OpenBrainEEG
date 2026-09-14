"""Brainifly Local: python start.py setup, then python start.py."""
from pathlib import Path
import argparse
import hashlib
import os
import shutil
import subprocess
import sys
from urllib.request import urlopen
import venv

ROOT = Path(__file__).resolve().parent
PYTHON = ROOT / "backend/.venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def environment():
    env = {k: v for k, v in os.environ.items() if not k.startswith(("NC_", "DEEPSEEK_", "VITE_")) and k != "DATABASE_URL"}
    env.update(PYTHONUTF8="1", PYTHONUNBUFFERED="1", MPLBACKEND="Agg")
    return env


def npm(args):
    node = shutil.which("node")
    if not node:
        found = sorted((ROOT / ".tools").glob("node-*/node.exe"))
        node = str(found[-1]) if found else None
    if not node:
        raise RuntimeError("Install Node.js 22, reopen the terminal, and run setup again.")
    node = Path(node)
    env = environment()
    env["PATH"] = str(node.parent) + os.pathsep + env.get("PATH", "")
    cli = node.parent / "node_modules/npm/bin/npm-cli.js"
    executable = [str(node), str(cli)] if cli.exists() else [shutil.which("npm", path=env["PATH"]) or "npm"]
    subprocess.run([*executable, *args], cwd=ROOT / "frontend", env=env, check=True)


def sample():
    path = ROOT / "backend/test_data/physionet/S001R01.edf"
    expected = "4743b736131a7e147c150e8b37711029b6cda5e356c4b3e8261a03cdcaaf8b0c"
    if path.exists():
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise RuntimeError("Existing sample differs from PhysioNet. It was preserved; inspect it before replacing.")
        print("Verified existing PhysioNet sample.")
        return
    print("Downloading PhysioNet S001R01 (ODC-By 1.0); see backend/test_data/README.md for attribution.")
    with urlopen("https://physionet.org/files/eegmmidb/1.0.0/S001/S001R01.edf", timeout=60) as response:
        data = response.read(2 * 1024 * 1024)
    if hashlib.sha256(data).hexdigest() != expected:
        raise RuntimeError("Sample checksum mismatch; nothing was written.")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", nargs="?", default="start", choices=["setup", "start", "backend", "frontend", "build", "sample", "check"])
    args = parser.parse_args()
    if args.command == "sample":
        return sample()
    if args.command == "setup":
        if sys.version_info < (3, 11):
            raise RuntimeError("Python 3.11 or newer is required.")
        if not PYTHON.exists():
            venv.EnvBuilder(with_pip=True).create(ROOT / "backend/.venv")
        subprocess.run([str(PYTHON), "-m", "pip", "install", "-r", str(ROOT / "backend/requirements.txt"), "-c", str(ROOT / "backend/constraints-local.txt")], env=environment(), check=True)
        npm(["ci"])
        npm(["run", "build"])
        sample()
        print("Setup complete. Run: python start.py")
        return
    if args.command in {"build", "frontend"}:
        return npm(["run", "build" if args.command == "build" else "dev"])
    if not PYTHON.exists():
        raise RuntimeError("Run python start.py setup first.")
    if args.command == "check":
        subprocess.run([str(PYTHON), "-c", "import local_app; print('Brainifly Local imports OK; no cloud database required')"], cwd=ROOT / "backend", env=environment(), check=True)
        return
    if args.command == "start" and not (ROOT / "frontend/dist/index.html").exists():
        raise RuntimeError("Frontend is not built. Run python start.py setup or python start.py build.")
    print("Brainifly Local: http://127.0.0.1:8765  |  Ctrl+C to stop")
    subprocess.run([str(PYTHON), "-m", "uvicorn", "local_app:app", "--host", "127.0.0.1", "--port", "8765"], cwd=ROOT / "backend", env=environment(), check=True)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
    except (RuntimeError, subprocess.CalledProcessError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
