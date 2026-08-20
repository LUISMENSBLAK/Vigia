import argparse
import asyncio
import json
from dataclasses import asdict
from pathlib import Path

from services.api.vigia_api.config import get_settings
from vigia_geospatial.materialize import load_materialization_config, materialize


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Materializa una AOI geoespacial VIGÍA.")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config/geospatial/avila-tile-356-4502.json"),
    )
    parser.add_argument("--storage-root", type=Path, default=Path("data"))
    parser.add_argument("--code-commit", required=True)
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    report = await materialize(
        config=load_materialization_config(args.config),
        settings=get_settings(),
        storage_root=args.storage_root,
        code_commit=args.code_commit,
    )
    print(json.dumps(asdict(report), indent=2, sort_keys=True))


if __name__ == "__main__":
    asyncio.run(main())
