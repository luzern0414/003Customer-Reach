"""完整归档项目并用 AES-256-GCM 加密；凭据只进入密文，恢复钥独立保存。"""
from __future__ import annotations

import argparse
import ctypes
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import secrets
import stat
import tarfile
import time
import uuid

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

MAGIC = b"CLIENTREACH-AES256-GCM-V1\n"
CHUNK = 1024 * 1024
PART_SIZE = 16 * CHUNK


def shared_read(path: Path):
    """打开只读源文件；path 必须存在，Windows 允许其他进程持有共享写句柄，失败直接抛错。"""
    if os.name != "nt":
        return path.open("rb")
    import msvcrt
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateFileW.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_uint32,
                                  ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p]
    kernel.CreateFileW.restype = ctypes.c_void_p
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    absolute = "\\\\?\\" + str(path.resolve())
    handle = kernel.CreateFileW(absolute, 0x80000000, 7, None, 3, 0x80, None)
    if handle == ctypes.c_void_p(-1).value:
        raise OSError(ctypes.get_last_error(), "无法读取备份源文件", str(path))
    try:
        fd = msvcrt.open_osfhandle(handle, os.O_RDONLY | os.O_BINARY)
    except Exception:
        kernel.CloseHandle(handle)
        raise
    return os.fdopen(fd, "rb")


class Parts:
    """将密文拆为固定大小分片，同时记录可用于远端复验的 SHA-256。"""
    def __init__(self, output: Path):
        self.output = output
        self.file = None
        self.items = []
        self.total = 0
        self.whole = hashlib.sha256()
        self.part_hash = None
        self.part_bytes = 0

    def write(self, data: bytes) -> int:
        """data 为待写密文；空字节无操作，返回实际长度，磁盘错误向外传播。"""
        original = len(data)
        self.whole.update(data)
        self.total += original
        while data:
            if self.file is None:
                self.name = f"snapshot.enc.part{len(self.items):04d}"
                self.file = (self.output / self.name).open("xb")
                self.part_hash = hashlib.sha256()
                self.part_bytes = 0
            piece = data[:PART_SIZE - self.part_bytes]
            self.file.write(piece)
            self.part_hash.update(piece)
            self.part_bytes += len(piece)
            data = data[len(piece):]
            if self.part_bytes == PART_SIZE:
                self.finish_part()
        return original

    def finish_part(self):
        """关闭当前分片并保存哈希；没有打开分片时不操作，返回值为空。"""
        if self.file is not None:
            self.file.close()
            self.items.append({"name": self.name, "bytes": self.part_bytes,
                               "sha256": self.part_hash.hexdigest()})
            self.file = None


class EncryptedWriter:
    """gzip/tar 的流式密文输出；不在临时目录生成含密钥的明文归档。"""
    def __init__(self, parts: Parts, encryptor):
        self.parts = parts
        self.encryptor = encryptor

    def write(self, data: bytes) -> int:
        """data 为 gzip 字节，空输入允许；返回原始长度，错误直接上抛。"""
        self.parts.write(self.encryptor.update(data))
        return len(data)

    def flush(self):
        """满足标准流接口；实际磁盘刷新在分片关闭时完成。"""


class HashReader:
    """只对实际进入 tar 的字节计数，避免在线日志变化导致清单哈希失真。"""
    def __init__(self, source):
        self.source = source
        self.digest = hashlib.sha256()
        self.bytes = 0

    def read(self, size=-1):
        """size 为读取上限，-1 表示剩余全部；返回字节并累计哈希，错误向外传播。"""
        data = self.source.read(size)
        self.digest.update(data)
        self.bytes += len(data)
        return data


def inventory(project: Path, exclusions: list[Path], frozen: Path | None):
    """枚举全部隐藏/忽略文件；project 为源根，exclusions 为自身产物，frozen 非空则替换 data/app。"""
    files, directories, links = [], [], []
    def walk(base: Path, prefix: str):
        for entry in sorted(os.scandir(base), key=lambda x: x.name.casefold()):
            path = Path(entry.path)
            if any(path == excluded or excluded in path.parents for excluded in exclusions):
                continue
            relative = prefix + entry.name
            info = entry.stat(follow_symlinks=False)
            if getattr(info, "st_file_attributes", 0) & 0x400 or stat.S_ISLNK(info.st_mode):
                links.append({"path": relative, "target": os.readlink(path), "kind": "reparse_point"})
            elif entry.is_dir(follow_symlinks=False):
                directories.append((relative, info.st_mtime))
                # 服务停止时冻结业务库和附件；压缩期间运行库的变化不会混入该快照。
                walk(frozen if frozen is not None and relative == "data/app" else path, relative + "/")
            elif entry.is_file(follow_symlinks=False):
                files.append((relative, path))
            else:
                raise ValueError(f"不能归档的源类型: {relative}")
    walk(project, "")
    return files, directories, links


def pack(args):
    """args 为命令行配置且路径不能为空；成功写出密文与清单，任一源读取失败终止。"""
    project = Path(args.project).resolve()
    output = Path(args.output).resolve()
    keyfile = Path(args.key_file).resolve()
    frozen = Path(args.frozen_data).resolve() if args.frozen_data else None
    output.mkdir(parents=True, exist_ok=False)
    keyfile.parent.mkdir(parents=True, exist_ok=True)
    key = secrets.token_bytes(32)
    key_id = uuid.uuid4().hex
    with keyfile.open("x", encoding="utf-8") as stream:
        json.dump({"format": "clientreach-recovery-key-v1", "key_id": key_id,
                   "key_hex": key.hex()}, stream)
    excluded = [Path(p).resolve() for p in args.exclude]
    excluded.extend([output, keyfile, project / "config/backup-keys"])
    files, directories, links = inventory(project, excluded, frozen)
    external = [("_external/codex/" + Path(p).name, Path(p)) for p in args.external]
    files.extend(external)
    print(json.dumps({"stage": "inventory", "files": len(files), "directories": len(directories),
                      "junctions": len(links)}, ensure_ascii=False), flush=True)
    parts = Parts(output)
    nonce = secrets.token_bytes(12)
    parts.write(MAGIC + nonce)
    encryptor = Cipher(algorithms.AES(key), modes.GCM(nonce)).encryptor()
    encryptor.authenticate_additional_data(MAGIC)
    content = []
    total_source = 0
    last_update = time.monotonic()
    with gzip.GzipFile(fileobj=EncryptedWriter(parts, encryptor), mode="wb", compresslevel=3, mtime=0) as gz:
        with tarfile.open(fileobj=gz, mode="w|", format=tarfile.PAX_FORMAT, dereference=True) as archive:
            for relative, mtime in directories:
                item = tarfile.TarInfo(project.name + "/" + relative)
                item.type = tarfile.DIRTYPE
                item.mtime = mtime
                archive.addfile(item)
            for index, (relative, path) in enumerate(files, 1):
                with shared_read(path) as source:
                    info = os.fstat(source.fileno())
                    item = tarfile.TarInfo(project.name + "/" + relative)
                    item.size = info.st_size
                    item.mtime = info.st_mtime
                    item.mode = 0o600
                    reader = HashReader(source)
                    archive.addfile(item, reader)
                content.append({"path": item.name, "bytes": reader.bytes,
                                "sha256": reader.digest.hexdigest(), "mtime": item.mtime})
                total_source += reader.bytes
                if time.monotonic() - last_update > 20:
                    print(json.dumps({"stage": "packing", "done": index, "total": len(files),
                                      "source_bytes": total_source, "encrypted_bytes": parts.total}), flush=True)
                    last_update = time.monotonic()
            # 路径和原文件哈希也在密文内，公开清单只展示总量及密文分片哈希。
            for name, data in [("_backup/manifest.jsonl", "".join(json.dumps(x, ensure_ascii=False) + "\n" for x in content).encode()),
                               ("_backup/junctions.json", json.dumps(links, ensure_ascii=False).encode()),
                               ("_backup/snapshot.json", json.dumps({"created_at": args.created_at,
                                  "frozen_data": bool(frozen), "excluded": [str(p.relative_to(project)) for p in excluded if p.is_relative_to(project)]}, ensure_ascii=False).encode())]:
                item = tarfile.TarInfo(name)
                item.size = len(data)
                item.mode = 0o600
                archive.addfile(item, io.BytesIO(data))
    parts.write(encryptor.finalize())
    parts.write(encryptor.tag)
    parts.finish_part()
    public = {"format": "clientreach-encrypted-backup-v1", "algorithm": "AES-256-GCM",
              "key_id": key_id, "created_at": args.created_at, "source_root": project.name,
              "files": len(files), "directories": len(directories), "junctions": len(links),
              "source_bytes": total_source, "encrypted_bytes": parts.total,
              "sha256": parts.whole.hexdigest(), "parts": parts.items,
              "database_snapshot": "services_stopped_then_copied" if frozen else "not_frozen"}
    (output / "backup.json").write_text(json.dumps(public, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"stage": "packed", "files": len(files), "source_bytes": total_source,
                      "encrypted_bytes": parts.total, "parts": len(parts.items), "sha256": public["sha256"]}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--key-file", required=True)
    parser.add_argument("--frozen-data")
    parser.add_argument("--exclude", action="append", default=[])
    parser.add_argument("--external", action="append", default=[])
    parser.add_argument("--created-at", required=True)
    pack(parser.parse_args())
