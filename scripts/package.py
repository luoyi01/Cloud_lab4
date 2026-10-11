"""Package only tracked course deliverables, never the entire working directory."""
import argparse
from pathlib import Path
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]
DIRECTORIES = {"src", "docker", "k8s", "scripts", "tests", "docs", "results", "screenshots"}
FILES = {"README.md", "report.pdf", "pytest.ini", ".gitignore", ".gitattributes", ".dockerignore", ".env.example"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--student-id", default="待填写")
    parser.add_argument("--name", default="待填写")
    args = parser.parse_args()
    for value in (args.student_id, args.name):
        if not value or any(c in value for c in '/\\:*?"<>|\r\n') or value in (".", ".."):
            parser.error("学号和姓名不能包含路径或文件名保留字符。")
    raw = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT).decode("utf-8")
    tracked = [Path(name) for name in raw.split("\0") if name]
    selected = [p for p in tracked if p.parts[0] in DIRECTORIES or str(p) in FILES]
    required = ["README.md", "report.pdf", "src/app/main.py", "docker/compose.yaml", "k8s/base/api.yaml"]
    if any(Path(name) not in selected for name in required):
        raise SystemExit("课程材料尚未全部被 Git 跟踪，请先核验并提交。")
    changed = subprocess.check_output(["git", "status", "--porcelain", "--", *[p.as_posix() for p in selected]],
                                      cwd=ROOT, text=True)
    if changed:
        raise SystemExit("提交材料含未提交修改；请先提交，以保证 ZIP 与记录的 HEAD 一致。")
    for relative in selected:
        source = ROOT / relative
        if not source.resolve().is_relative_to(ROOT) or relative.name in ("secret.yaml", "kubeconfig", ".env"):
            raise SystemExit(f"Refuse unexpected source: {relative}")
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    target = ROOT / f"{args.student_id}_{args.name}_云原生实验.zip"
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for relative in selected:
            archive.write(ROOT / relative, arcname=relative.as_posix())
        archive.writestr("SUBMISSION.txt", f"Repository: https://github.com/luoyi01/Cloud_lab4\nCommit: {commit}\nStudent ID: {args.student_id}\nName: {args.name}\n")
    with zipfile.ZipFile(target) as archive:
        assert archive.testzip() is None
        names = archive.namelist()
        assert not any(name.startswith((".git/", ".local/")) or name in ("findings.md", "progress.md", "task_plan.md", ".env") for name in names)
    print(f"Packaged {len(selected)} tracked files: {target.name} (commit {commit[:12]})")


if __name__ == "__main__":
    main()
