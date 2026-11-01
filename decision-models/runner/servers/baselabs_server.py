"""Serve Base Labs' elephant-1 or mammoth-1 over HTTP with TypeSafe's System One format, through qev's own server.

    docker run --rm --runtime nvidia --gpus device=GPU -p 127.0.0.1:PORT:PORT -v ~/.cache/huggingface/hub:/hf:ro \
        -v "$PWD/servers:/servers:ro" baselabs-serve:81ce62f \
        python /servers/baselabs_server.py --checkpoint SNAPSHOT --name baselabs/elephant-1 --host 0.0.0.0 --port PORT

SNAPSHOT is the downloaded Hugging Face snapshot of baselabs/elephant-1 at revision
b3f8a93462fb1051a9de031e94a7ff380e254072 (18.8 GB) or of baselabs/mammoth-1 at revision
61cec44c281c693992e3d6ebeb44dd3402dfa186 (54.7 GB). baselabs-serve:81ce62f is the environment the model card's setup.sh
installs, built by running that script in the image the card names (pytorch/pytorch:2.8.0-cuda12.8-cudnn9-devel,
sha256:a7103283ea71): OneJev (github.com/OmniJev/OneJev) at commit 81ce62f1597c91e46767d4d02d6ac2e18534fe94 with the
checkpoint's serve.patch applied, its constraints.txt, and the Decision Index kit at f5a6e4fd85fed05e77878dfc4966d0568bfb45ec
(Python 3.11, torch 2.8.0+cu128, transformers 5.19.0). Both checkpoints ship the same setup.sh, serve.patch and
constraints.txt. GPU: one RTX PRO 6000 Blackwell (96 GB).

The card scores requests with qev's DecisionEngine at its defaults (bf16, fork mode chosen at load), as in its example
and in its engine.py. This script builds that engine from the local snapshot directory, because the engine reads the
checkpoint's readout.json and config.json (block-bidirectional attention in the full-attention layers, slot_lm readout)
only from a local path; given a Hub ID it would fall back to causal attention. It refuses to serve when the engine does
not report the noncausal attention the card says the model was trained with. `qev serve` cannot be used as it is: for a
checkpoint with a vision_config, as both have, it loads OneJev's multimodal engine, which Base Labs' patch leaves
unchanged. So this server takes text only.

The app is qev's own (qev.server.create_app, as `qev serve` runs it): POST /v1/systemone takes the System One request,
answers it with DecisionEngine.decide, and returns {"model", "answers", "usage", "qev"}; usage.input_tokens counts the
prompt tokens the engine ran (the shared prefix and each question's suffix), and "qev" holds the engine's metadata. The
model field must name the loaded checkpoint (--name). A request over the engine's length limits is refused with 422,
never cut. Requests are answered one at a time; each response carries an x-typesafe-request-id header.
"""

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--checkpoint", type=Path, required=True, help="the downloaded snapshot directory")
    parser.add_argument("--name", required=True, help="the checkpoint's name, which every request's model field must give")
    parser.add_argument("--device", default="cuda:0", help="torch device (default: cuda:0)")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18101)
    args = parser.parse_args()
    checkpoint = args.checkpoint.resolve()
    if not (checkpoint / "readout.json").is_file():
        raise SystemExit(f"{checkpoint} has no readout.json: give the downloaded snapshot directory")

    import uvicorn
    from qev.engine import DecisionEngine
    from qev.server import create_app

    engine = DecisionEngine(str(checkpoint), device=args.device)  # the model card's call, on the local snapshot
    info = engine.info
    print(json.dumps({"url": f"http://{args.host}:{args.port}", "model": args.name, "checkpoint": str(checkpoint),
                      "device": info.device, "dtype": info.dtype, "fork_mode": info.fork_mode, **info.extra,
                      "transformers": info.transformers_version, "torch": info.torch_version}), flush=True)
    if info.extra.get("attention") != "noncausal":
        raise SystemExit(f"the engine loaded {info.extra.get('attention')} attention, not the trained noncausal one")
    uvicorn.run(create_app(engine, model_name=args.name), host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
