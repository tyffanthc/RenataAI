from __future__ import annotations

import argparse
import pathlib
import sys
import urllib.request


def _download(url: str, out_path: pathlib.Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url) as response, open(out_path, "wb") as f:
        f.write(response.read())


def main() -> int:
    parser = argparse.ArgumentParser(description="Download Piper model/config.")
    parser.add_argument("--model-url", required=True, help="URL to .onnx model")
    parser.add_argument("--config-url", help="URL to .json config (optional)")
    parser.add_argument(
        "--out-dir",
        default="models/piper",
        help="Output directory for model/config",
    )
    args = parser.parse_args()

    out_dir = pathlib.Path(args.out_dir)
    model_name = pathlib.Path(args.model_url).name or "model.onnx"
    model_path = out_dir / model_name
    print(f"Downloading model -> {model_path}")
    _download(args.model_url, model_path)

    if args.config_url:
        config_name = pathlib.Path(args.config_url).name or "model.json"
        config_path = out_dir / config_name
        print(f"Downloading config -> {config_path}")
        _download(args.config_url, config_path)

    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
