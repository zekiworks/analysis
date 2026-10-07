"""Serve Strands Decider 2B over HTTP with TypeSafe's System One request and response format.

    .venv/bin/python server.py --gpu 1 --port 18096

Runs the package's own server (strands_decider.server.serve, what `strands-decider serve` runs):
POST /v1/systemone and GET /health, with the checkpoint's own readout and fitted temperatures.
The checkpoint is model/ (StrandsAgents/strands-decider-2B-hobson-v21 at 2b52a62); its base,
Qwen/Qwen3.5-2B-Base at the revision model/provenance.json records, is read offline from hf-cache/.
Only the chosen GPU is made visible, so the Triton kernels cannot touch another one.
"""

import argparse
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent
MODEL_DIR = HERE / "model"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--gpu", default="1", help="CUDA device index to serve on (default: 1)")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18096)
    parser.add_argument("--model-name", default="strands-decider-2b", help="`model` in responses")
    args = parser.parse_args()
    os.environ["CUDA_VISIBLE_DEVICES"] = args.gpu
    os.environ["HF_HUB_CACHE"] = str(HERE / "hf-cache")
    os.environ["HF_HUB_OFFLINE"] = "1"

    from strands_decider.server import serve

    serve(str(MODEL_DIR), host=args.host, port=args.port, device="cuda", model_name=args.model_name)


if __name__ == "__main__":
    main()
