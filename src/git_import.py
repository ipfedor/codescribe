# -*- coding: utf-8 -*-
# REMEMBER: this is python 2.7
import os

from util import _cmdline_for_shell, ensure_unicode_path


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


def _get_cwd_unicode():
    if hasattr(os, "getcwdu"):
        return os.getcwdu()
    cwd = os.getcwd()
    if isinstance(cwd, str):
        try:
            return cwd.decode("mbcs")
        except UnicodeDecodeError:
            return cwd.decode("utf-8", "replace")
    return cwd


def _run_git(cwd, args):
    """
    Run git in cwd via unicode os.chdir (wide WinAPI).

    Do NOT pass Cyrillic paths as git -C / cmdline args: os.popen + mbcs/utf-8
    encoding mojibakes them. chdir(unicode) works; then use relative args (e.g. ".").
    """
    cwd = ensure_unicode_path(cwd)
    if not os.path.isdir(cwd):
        raise ValueError(u"Path does not exist: " + cwd)

    # Keep argv ASCII-safe: commands, refs, ".", pathspecs relative to cwd.
    argv = ["git", "-c", "core.quotepath=false"] + list(args)
    cmd = _cmdline_for_shell(argv) + " 2>&1"

    old_cwd = _get_cwd_unicode()
    try:
        os.chdir(cwd)
        try:
            pipe = os.popen(cmd)
        except OSError as e:
            raise ValueError(u"Cannot run git: " + unicode(e))
        try:
            raw = pipe.read()
        finally:
            status = pipe.close()
    finally:
        try:
            os.chdir(old_cwd)
        except Exception:
            pass

    out = _decode_git_output(raw)
    if status not in (None, 0):
        err_text = out.strip()
        raise ValueError(u"git " + u" ".join([unicode(a) for a in args[:3]]) + u"... failed: " + err_text)
    stripped = out.lstrip()
    if stripped.startswith("fatal:") or stripped.startswith("error:"):
        raise ValueError(
            u"git " + u" ".join([unicode(a) for a in args[:3]]) + u"... failed: " + stripped.strip()
        )
    return out


def _unescape_git_path(path):
    """
    Decode git quoted paths (\"a\\320\\234b\") if quotepath was still on.

    If quoted with octal escapes: unescape → latin-1 bytes → utf-8 unicode.
    Otherwise return as-is.
    """
    if not path:
        return path
    if isinstance(path, str) and not isinstance(path, unicode):
        path = _decode_git_output(path)
    if len(path) >= 2 and path[0] == u'"' and path[-1] == u'"':
        path = path[1:-1]
    if u"\\" not in path:
        return path

    out = []
    i = 0
    n = len(path)
    while i < n:
        ch = path[i]
        if ch == u"\\" and i + 1 < n:
            nxt = path[i + 1]
            if nxt in (u"\\", u'"'):
                out.append(nxt)
                i += 2
                continue
            # Git quotepath: \NNN with exactly three octal digits
            if i + 3 < n and path[i + 1 : i + 4].isdigit():
                out.append(unichr(int(path[i + 1 : i + 4], 8)))
                i += 4
                continue
        out.append(ch)
        i += 1

    text = u"".join(out)
    try:
        return text.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return text


def find_git_repo_root(start_path):
    start_path = ensure_unicode_path(start_path)
    out = _run_git(start_path, ["rev-parse", "--show-toplevel"])
    root = out.strip().strip('"')
    root = _unescape_git_path(root)
    if not root:
        raise ValueError(u"git rev-parse returned empty path")
    return ensure_unicode_path(root)


def _git_path_lines(text):
    lines = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        line = _unescape_git_path(line)
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
        elif not prefix_rel:
            result.append(path)
    return result


def list_git_changed_under(application_folder, base_ref=None):
    """
    Return paths relative to application_folder that differ from base_ref in git.

    Includes modified/staged vs base_ref, deleted files, and new untracked files.
    """
    if base_ref is None:
        base_ref = import_git_base_ref()

    # Resolve on-disk Cyrillic folder before chdir (never put it on the git cmdline).
    application_folder = ensure_unicode_path(application_folder)

    prefix = _run_git(application_folder, ["rev-parse", "--show-prefix"]).strip()
    prefix = _unescape_git_path(prefix).replace("\\", "/").strip("/")
    prefix_rel = prefix  # repo-relative path of cwd (no trailing slash)

    # Pathspec "." is cwd-relative after unicode chdir — no Cyrillic on argv.
    modified = _git_path_lines(
        _run_git(application_folder, ["diff", "--name-only", base_ref, "--", "."])
    )
    deleted = _git_path_lines(
        _run_git(
            application_folder,
            ["diff", "--name-only", "--diff-filter=D", base_ref, "--", "."],
        )
    )
    untracked = _git_path_lines(
        _run_git(
            application_folder,
            ["ls-files", "--others", "--exclude-standard", "--", "."],
        )
    )

    rel_modified = _paths_under_prefix(modified, prefix_rel)
    rel_deleted = _paths_under_prefix(deleted, prefix_rel)
    rel_untracked = _paths_under_prefix(untracked, prefix_rel)

    changed = set(rel_modified) | set(rel_untracked)
    return sorted(changed), sorted(rel_deleted)
