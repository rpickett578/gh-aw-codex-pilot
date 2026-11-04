"""Host-only, fail-closed snapshots after gh-aw restoration; no GitHub writes."""
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys

ALLOWED = {"review": None, "repair": "src/slugify.mjs", "next": "src/reverse-ascii.mjs"}


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args], env=dict(os.environ, GIT_OPTIONAL_LOCKS="0"))


def snapshot(root):
    root = Path(root).resolve()
    require(Path(git(root, "rev-parse", "--show-toplevel").decode().strip()).resolve() == root, "wrong workspace root")
    entries = {}
    total = 0

    def visit(directory):
        nonlocal total
        for path in sorted(directory.iterdir()):
            if path.parent == root and path.name == ".git":
                continue  # Git administration is checked separately, not part of the working tree.
            info = path.lstat()
            name = path.relative_to(root).as_posix()
            row = {"mode": stat.S_IMODE(info.st_mode)}
            if stat.S_ISLNK(info.st_mode):
                row.update(kind="link", target=os.readlink(path))
            elif stat.S_ISDIR(info.st_mode):
                row.update(kind="directory")
            elif stat.S_ISREG(info.st_mode):
                total += info.st_size
                require(total <= 32 * 1024 * 1024, "workspace exceeds bounded snapshot size")
                require(info.st_nlink == 1, "hard-linked workspace file")
                fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
                with os.fdopen(fd, "rb") as stream:
                    opened = os.fstat(stream.fileno())
                    require((info.st_ino, info.st_size, info.st_mode) ==
                            (opened.st_ino, opened.st_size, opened.st_mode), "file replaced during snapshot")
                    digest = hashlib.sha256(stream.read()).hexdigest()
                after = path.lstat()
                require((info.st_ino, info.st_size, info.st_mtime_ns, info.st_mode) ==
                        (after.st_ino, after.st_size, after.st_mtime_ns, after.st_mode), "file changed during snapshot")
                row.update(kind="file", size=info.st_size, sha256=digest)
            else:
                raise ValueError("unsupported workspace entry: " + name)
            entries[name] = row
            require(len(entries) <= 4096, "workspace entry limit exceeded")
            if row["kind"] == "directory":
                visit(path)
    visit(root)
    index = {}
    for entry in git(root, "ls-files", "--stage", "-z").split(b"\0"):
        if entry:
            meta, name = entry.split(b"\t", 1)
            require(meta.endswith(b" 0"), "unmerged index entry")
            index[name.decode()] = meta.decode()
    return {"entries": entries, "head": git(root, "rev-parse", "HEAD").decode().strip(), "index": index}


def compare(before, after, stage):
    require(stage in ALLOWED, "unknown guard stage")
    require(before["head"] == after["head"], "agent changed Git HEAD")
    allowed = ALLOWED[stage]
    for section in ["entries", "index"]:
        left, right = before[section], after[section]
        changed = {name for name in left.keys() | right.keys() if left.get(name) != right.get(name)}
        require(changed <= ({allowed} if allowed else set()), "unauthorized " + section + " changes: " + ",".join(sorted(changed)))
    if allowed:
        old, new = before["entries"].get(allowed), after["entries"].get(allowed)
        require(old and new and old != new, "approved source must change")
        require(new["kind"] == "file" and old["mode"] == new["mode"] and 0 < new["size"] <= 16384,
                "approved source must remain a bounded regular file with unchanged mode")


def baseline_path(root):
    temporary = Path(os.environ["RUNNER_TEMP"]).resolve()
    directory = temporary / "phase2-workspace-guard"
    require(not directory.is_symlink(), "symlink baseline directory")
    require(not directory.is_relative_to(root), "baseline cannot be in workspace")
    # These are the only temporary trees mounted by the pinned compiled sandbox.
    require(not directory.is_relative_to(temporary / "gh-aw") and
            not directory.is_relative_to(Path("/tmp/gh-aw").resolve()), "baseline cannot be agent-mounted")
    return directory / "baseline.json"


def main():
    mode, stage = sys.argv[1:]
    require(stage in ALLOWED, "unknown stage")
    root = Path.cwd().resolve()
    path = baseline_path(root)
    identity = {"run_id": os.environ["GITHUB_RUN_ID"], "workflow_sha": os.environ["GITHUB_WORKFLOW_SHA"],
                "root": str(root), "stage": stage}
    if mode == "capture":
        path.parent.mkdir(mode=0o700, exist_ok=False)
        record = dict(identity=identity, snapshot=snapshot(root))
        # Host RUNNER_TEMP outside both workspace and sandbox mounts. Never upload.
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o400)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(record, stream, sort_keys=True)
    elif mode == "check":
        require(path.is_file() and not path.is_symlink(), "trusted baseline missing")
        record = json.loads(path.read_text(encoding="utf-8"))
        require(record["identity"] == identity, "baseline context differs")
        compare(record["snapshot"], snapshot(root), stage)
    else:
        raise ValueError("unknown guard operation")
    print("PASS: host-only workspace guard " + mode + " " + stage)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, KeyError, OSError, subprocess.SubprocessError) as error:
        raise SystemExit("STOP: " + str(error))
