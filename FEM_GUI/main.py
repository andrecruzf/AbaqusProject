from __future__ import annotations

import os
from pathlib import Path


def _prepare_environment() -> None:
    base = Path(__file__).resolve().parent
    mpl_dir = base / ".cache" / "matplotlib"
    mpl_dir.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("MPLCONFIGDIR", str(mpl_dir))


def main() -> None:
    _prepare_environment()

    try:
        from gui.shell import FEMApp
    except ModuleNotFoundError as exc:
        if exc.name == "customtkinter":
            raise SystemExit(
                "customtkinter is required. Install with: "
                "python3 -m pip install -r FEM_GUI/requirements.txt"
            ) from exc
        raise

    app = FEMApp()
    app.mainloop()


if __name__ == "__main__":
    main()

