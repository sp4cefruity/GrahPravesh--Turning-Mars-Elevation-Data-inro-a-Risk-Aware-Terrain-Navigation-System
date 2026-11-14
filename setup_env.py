"""One command to get a working environment.

    python setup_env.py              creates .venv and installs everything
    python setup_env.py --core       skips the Streamlit dashboard packages
    python setup_env.py --venv PATH  uses another folder for the environment

Needs Python 3.11 or newer. The pins in requirements.txt were tested on 3.14.
"""

import argparse
import subprocess
import sys
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DASHBOARD_PKGS = ("streamlit", "plotly", "pandas")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--venv", default=str(ROOT / ".venv"))
    ap.add_argument("--core", action="store_true", help="skip dashboard packages")
    args = ap.parse_args()

    if sys.version_info < (3, 11):
        sys.exit(f"Python 3.11 or newer is required, this is {sys.version.split()[0]}.")

    env = Path(args.venv)
    if not env.exists():
        print(f"Creating environment in {env}")
        venv.create(env, with_pip=True)
    py = env / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")

    req = ROOT / "requirements.txt"
    if args.core:
        lines = [l for l in req.read_text(encoding="utf-8").splitlines()
                 if l.strip() and not l.startswith("#") and not l.split("==")[0] in DASHBOARD_PKGS]
        tmp = env / "requirements-core.txt"
        tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
        req = tmp

    subprocess.check_call([str(py), "-m", "pip", "install", "-r", str(req)])
    subprocess.check_call([str(py), "-m", "pip", "install", "-e", str(ROOT), "--no-deps"])
    print("\nDone. Activate with:")
    print("  Windows:  .venv\Scripts\activate")
    print("  Mac/Linux: source .venv/bin/activate")
    print("Then:  python -m odyssey.pipeline   or   pytest")


if __name__ == "__main__":
    main()
