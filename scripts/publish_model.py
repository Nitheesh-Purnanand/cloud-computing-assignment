"""Package a trained model, upload it to s3://models/<version>/ and write its checksum.

Usage: python scripts/publish_model.py VERSION [--dir artifacts/VERSION] [--from-tar FILE]

Creates artifacts/model-<version>.tar.gz deterministically (sorted names, fixed mtimes), so the
SHA-256 in s3://models/<version>/model.sha256 equals the checksum of the GitHub Release asset.
"""
import argparse
import gzip
import hashlib
import io
import pathlib
import sys
import tarfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "worker"))
from common import s3  # noqa: E402

MODEL_FILES = ("config.json", "generation_config.json", "model.safetensors", "special_tokens_map.json",
               "tokenizer.json", "tokenizer_config.json", "version.json")


def make_tar(src, dest):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w", format=tarfile.USTAR_FORMAT) as tar:
        for name in MODEL_FILES:
            data = (src / name).read_bytes()
            info = tarfile.TarInfo(f"{src.name}/{name}")
            info.size, info.mtime, info.mode = len(data), 0, 0o644
            tar.addfile(info, io.BytesIO(data))
    with open(dest, "wb") as f, gzip.GzipFile(filename="", mode="wb", fileobj=f, mtime=0) as gz:
        gz.write(buf.getvalue())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("version")
    ap.add_argument("--dir")
    ap.add_argument("--from-tar", help="use an existing release tarball (e.g. downloaded from GitHub)")
    a = ap.parse_args()
    art = pathlib.Path("artifacts")
    art.mkdir(exist_ok=True)
    tar_path = pathlib.Path(a.from_tar) if a.from_tar else art / f"model-{a.version}.tar.gz"
    src = pathlib.Path(a.dir or art / a.version)
    if a.from_tar:
        with tarfile.open(tar_path) as t:
            t.extractall(art, filter="data")
        src = art / a.version
    else:
        make_tar(src, tar_path)
    digest = hashlib.sha256(tar_path.read_bytes()).hexdigest()
    sha_line = f"{digest}  {tar_path.name}\n"
    (art / f"model-{a.version}.sha256").write_text(sha_line)
    client = s3()
    for name in MODEL_FILES:
        client.upload_file(str(src / name), "models", f"{a.version}/{name}")
    client.upload_file(str(tar_path), "models", f"{a.version}/{tar_path.name}")
    client.put_object(Bucket="models", Key=f"{a.version}/model.sha256", Body=sha_line.encode())
    keys = [o["Key"] for o in client.list_objects_v2(Bucket="models", Prefix=f"{a.version}/")["Contents"]]
    print(f"uploaded {keys}\nsha256 {digest}")


if __name__ == "__main__":
    main()
