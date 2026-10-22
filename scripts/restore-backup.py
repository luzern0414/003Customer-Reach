"""验证并恢复项目密文备份；须另行提供恢复钥文件，默认仅验证、不覆盖现有文件。"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import tarfile
import tempfile

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

MAGIC = b"CLIENTREACH-AES256-GCM-V1\n"
CHUNK = 1024 * 1024


def restore(args):
    """args 指定备份目录/恢复钥和可选目标；目标非空时拒绝执行，哈希/认证失败不释放恢复文件。"""
    source = Path(args.backup).resolve()
    meta = json.loads((source / "backup.json").read_text(encoding="utf-8"))
    key = json.loads(Path(args.key_file).read_text(encoding="utf-8"))
    if key["key_id"] != meta["key_id"]:
        raise ValueError("恢复钥与备份不匹配")
    work = Path(args.work_dir).resolve()
    work.mkdir(parents=True, exist_ok=True)
    # 第一遍验证全部密文，再验证 GCM 标签；只在认证通过后解压。
    digest = hashlib.sha256()
    for part in meta["parts"]:
        part_path = source / part["name"]
        if part_path.parent != source:
            raise ValueError("无效分片路径")
        local = hashlib.sha256()
        size = 0
        with part_path.open("rb") as stream:
            while data := stream.read(CHUNK):
                local.update(data)
                digest.update(data)
                size += len(data)
        if local.hexdigest() != part["sha256"] or size != part["bytes"]:
            raise ValueError("密文分片损坏")
    if digest.hexdigest() != meta["sha256"]:
        raise ValueError("完整密文哈希不匹配")
    # GCM 标签也可能跨分片边界，不能假设最后一个分片至少有 16 字节。
    tag = b""
    for part in reversed(meta["parts"]):
        count = min(16 - len(tag), part["bytes"])
        with (source / part["name"]).open("rb") as stream:
            stream.seek(-count, 2)
            tag = stream.read(count) + tag
        if len(tag) == 16:
            break
    first = source / meta["parts"][0]["name"]
    with first.open("rb") as stream:
        if stream.read(len(MAGIC)) != MAGIC:
            raise ValueError("未知备份格式")
        nonce = stream.read(12)
    decryptor = Cipher(algorithms.AES(bytes.fromhex(key["key_hex"])), modes.GCM(nonce, tag)).decryptor()
    decryptor.authenticate_additional_data(MAGIC)
    with tempfile.TemporaryFile(dir=work) as plaintext:
        ciphertext_end = meta["encrypted_bytes"] - 16
        absolute_offset = 0
        for index, part in enumerate(meta["parts"]):
            with (source / part["name"]).open("rb") as stream:
                skip = len(MAGIC) + 12 if index == 0 else 0
                stream.seek(skip)
                remaining = max(0, min(part["bytes"], ciphertext_end - absolute_offset) - skip)
                while remaining:
                    data = stream.read(min(CHUNK, remaining))
                    if not data:
                        raise ValueError("密文提前结束")
                    plaintext.write(decryptor.update(data))
                    remaining -= len(data)
            absolute_offset += part["bytes"]
        plaintext.write(decryptor.finalize())
        plaintext.seek(0)
        target = Path(args.destination).resolve() if args.destination else None
        if target and target.exists() and any(target.iterdir()):
            raise ValueError("恢复目标必须为空，避免覆盖当前运行项目")
        if target:
            target.mkdir(parents=True, exist_ok=True)
        observed = {}
        expected = None
        with tarfile.open(fileobj=plaintext, mode="r|gz") as archive:
            for item in archive:
                path = PurePosixPath(item.name)
                if path.is_absolute() or ".." in path.parts or "\\" in item.name or ":" in item.name:
                    raise ValueError("归档包含不安全路径")
                if item.isdir():
                    if target:
                        (target / item.name).mkdir(parents=True, exist_ok=True)
                    continue
                if not item.isfile():
                    raise ValueError("不自动恢复链接或特殊文件")
                member = archive.extractfile(item)
                if item.name == "_backup/manifest.jsonl":
                    expected = [json.loads(line) for line in member.read().decode("utf-8").splitlines()]
                    continue
                if item.name.startswith("_backup/"):
                    if target:
                        destination = target / item.name
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        destination.write_bytes(member.read())
                    continue
                destination = target / item.name if target else None
                output = None
                if destination:
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    output = destination.open("xb")
                digest = hashlib.sha256()
                size = 0
                try:
                    while data := member.read(CHUNK):
                        digest.update(data)
                        size += len(data)
                        if output:
                            output.write(data)
                finally:
                    if output:
                        output.close()
                if item.name in observed:
                    raise ValueError("归档出现重复文件路径")
                observed[item.name] = {"bytes": size, "sha256": digest.hexdigest()}
        if expected is None or len(expected) != len(observed) or len(observed) != meta["files"]:
            raise ValueError("恢复文件数量与清单不符")
        for record in expected:
            actual = observed.get(record["path"])
            if actual != {"bytes": record["bytes"], "sha256": record["sha256"]}:
                raise ValueError("恢复文件内容与清单不符")
        print(json.dumps({"verified": True, "files": len(observed), "destination": str(target) if target else None,
                          "encrypted_sha256": meta["sha256"]}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backup", required=True)
    parser.add_argument("--key-file", required=True)
    parser.add_argument("--work-dir", required=True)
    parser.add_argument("--destination")
    restore(parser.parse_args())
