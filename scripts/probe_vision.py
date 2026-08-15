"""Does the local runtime accept images at all?

Before building photo upload into the product, find out whether Foundry Local's
ONNX build takes multimodal input through the same chat client. Cheap to answer,
expensive to assume.

The catalog lists qwen3-vl-2b/4b/8b-instruct. They are marked as reasoning
models, which caused a separate problem in the Turkish work, so the reasoning
switch is applied here too.

Run:  python -m scripts.probe_vision
      python -m scripts.probe_vision --model qwen3-vl-4b-instruct --image photo.jpg
"""

from __future__ import annotations

import argparse
import base64
import io
import time
from pathlib import Path

from src import foundry


def synthetic_image() -> bytes:
    """A picture with an unmistakable answer, so a vague reply is detectable."""
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (320, 240), (245, 245, 240))
    draw = ImageDraw.Draw(image)
    draw.ellipse([80, 60, 240, 180], fill=(200, 40, 40))
    draw.rectangle([20, 20, 60, 60], fill=(30, 90, 200))

    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def as_data_url(data: bytes, mime: str = "image/png") -> str:
    return f"data:{mime};base64,{base64.b64encode(data).decode()}"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="qwen3-vl-2b-instruct")
    parser.add_argument("--image", help="path to a real photo (optional)")
    parser.add_argument("--prompt",
                        default="Describe this image in one sentence.")
    args = parser.parse_args()

    if args.image:
        path = Path(args.image)
        if not path.exists():
            print(f"No such file: {path}")
            return
        data = path.read_bytes()
        mime = "image/jpeg" if path.suffix.lower() in {".jpg", ".jpeg"} else "image/png"
        print(f"Image: {path} ({len(data) / 1024:.0f} KB)")
    else:
        data = synthetic_image()
        mime = "image/png"
        print("Image: generated — a red circle and a small blue square")

    print(f"Model: {args.model}\nLoading (first run downloads it)...\n")

    # Point the wrapper at the vision model before anything loads.
    from src import config
    config.CHAT_MODEL_ALIAS = args.model
    config.MAX_TOKENS = 160

    try:
        model = foundry.get_model(args.model)
    except Exception as exc:
        print(f"Could not load the model: {type(exc).__name__}: {exc}")
        return

    print(f"input modalities : {model.input_modalities}")
    print(f"output modalities: {model.output_modalities}")
    print(f"capabilities     : {model.capabilities}\n")

    if model.input_modalities and "image" not in str(model.input_modalities):
        print("The catalog does not advertise image input for this model. "
              "Trying anyway — the metadata is not always complete.\n")

    client = model.get_chat_client()
    client.settings.max_tokens = 160
    client.settings.temperature = 0.2

    messages = [
        {"role": "system", "content": "You describe images factually and briefly."},
        {"role": "user", "content": [
            {"type": "text", "text": f"{args.prompt} /no_think"},
            {"type": "image_url", "image_url": {"url": as_data_url(data, mime)}},
        ]},
    ]

    started = time.perf_counter()
    try:
        response = client.complete_chat(messages)
        text = " ".join((response.choices[0].message.content or "").split())
        print(f"OK in {time.perf_counter() - started:.1f}s\n")
        print(text[:600])
        print("\n" + "-" * 66)
        if not args.image:
            print("Expected: a red circle, and ideally the small blue square.")
        print("If the reply ignores the picture, the runtime accepted the "
              "message but dropped the image.")
    except Exception as exc:
        print(f"FAILED after {time.perf_counter() - started:.1f}s")
        print(f"{type(exc).__name__}: {exc}")
        print("\nIf this is a validation or serialisation error, the SDK does "
              "not take image content and photo analysis is off the table.")
    finally:
        foundry.unload_all()


if __name__ == "__main__":
    main()
