"""Extract an Electron ASAR archive (Myth.Cool ships them renamed to .gpk).

Layout: 16-byte Chromium pickle prefix (sizes), then a JSON header describing a file
tree; each file entry has an "offset" (string) relative to the end of the header and a
"size". Entries marked "unpacked" live outside the archive and are skipped.

  uv run python asar_extract.py <archive.gpk> <out_dir>
"""

import json
import struct
import sys
from pathlib import Path


def extract(archive: Path, out: Path) -> int:
    data = archive.read_bytes()
    header_size = struct.unpack_from("<I", data, 12)[0]
    header = json.loads(data[16:16 + header_size])
    base = 8 + struct.unpack_from("<I", data, 4)[0]  # end of the header pickle
    count = 0

    def walk(node, path: Path):
        nonlocal count
        for name, entry in node.get("files", {}).items():
            p = path / name
            if "files" in entry:
                walk(entry, p)
            elif entry.get("unpacked"):
                continue
            else:
                off = base + int(entry["offset"])
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(data[off:off + entry["size"]])
                count += 1

    walk(header, out)
    return count


if __name__ == "__main__":
    n = extract(Path(sys.argv[1]), Path(sys.argv[2]))
    print(f"{sys.argv[1]}: {n} files")
