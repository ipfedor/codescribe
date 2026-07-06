# -*- coding: utf-8 -*-
# REMEMBER: this is python 2.7
import os
import subprocess

from util import ensure_unicode_path, safe_print


def import_git_base_ref():
    ref = os.environ.get("CODESCRIBE_IMPORT_GIT_BASE", "HEAD").strip()
    return ref or "HEAD"


def _decode_git_output(data):
    if not data:
        return u""
    if isinstance(data, unicode):
        return data
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("mbcs", "replace")


def _run_git(repo_root, args):
    repo_root = ensure_unicode_path(repo_root)
    argv = ["git", "-C", repo_root] + list(args)
    try:
        proc = subprocess.Popen(
            argv,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
        )
    except OSError as e:
        raise ValueError(u"Cannot run git: " + unicode(e))
    out, err = proc.communicate()
    if proc.returncode != 0:
        err_text = _decode_git_output(err).strip()
        raise ValueError(u"git " + u" ".join(args[:3]) + u"... failed: " + err_text)
    return _decode_git_output(out)


def find_git_repo_root(start_path):
    start_path = ensure_unicode_path(start_path)
    out = _run_git(start_path, ["rev-parse", "--show-toplevel"])
    root = out.strip()
    if not root:
        raise ValueError(u"git rev-parse returned empty path")
    return ensure_unicode_path(root)


def _git_path_lines(text):
    lines = []
    for line in text.splitlines():
        line = line.strip()
        if line:
            lines.append(line.replace("\\", "/"))
    return lines


def _paths_under_prefix(git_paths, prefix_rel):
    prefix_rel = prefix_rel.replace("\\", "/").rstrip("/")
    prefix_slash = prefix_rel + "/"
    result = []
    for path in git_paths:
        path = path.replace("\\", "/")
        if path == prefix_rel:
            continue
        if path.startswith(prefix_slash):
            result.append(path[len(prefix_slash) :])
    return result


def list_git_changed_under(application_folder, base_ref=None):
    """
    Return paths relative to application_folder that differ from base_ref in git.

    Includes modified/staged vs base_ref, deleted files, and new untracked files.
    """
    if base_ref is None:
        base_ref = import_git_base_ref()

    application_folder = ensure_unicode_path(application_folder)
    repo_root = find_git_repo_root(application_folder)
    prefix_rel = os.path.relpath(application_folder, repo_root).replace("\\", "/")

    modified = _git_path_lines(
        _run_git(repo_root, ["diff", "--name-only", base_ref, "--", prefix_rel])
    )
    deleted = _git_path_lines(
        _run_git(
            repo_root,
            ["diff", "--name-only", "--diff-filter=D", base_ref, "--", prefix_rel],
        )
    )
    untracked = _git_path_lines(
        _run_git(
            repo_root,
            ["ls-files", "--others", "--exclude-standard", "--", prefix_rel],
        )
    )

    rel_modified = _paths_under_prefix(modified, prefix_rel)
    rel_deleted = _paths_under_prefix(deleted, prefix_rel)
    rel_untracked = _paths_under_prefix(untracked, prefix_rel)

    changed = set(rel_modified) | set(rel_untracked)
    return sorted(changed), sorted(rel_deleted)
