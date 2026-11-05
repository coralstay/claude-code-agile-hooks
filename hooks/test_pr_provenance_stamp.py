import io
import json
import re

import pytest

import pr_provenance_stamp as pps


def run_main(monkeypatch, command, session_id="s1", extra_input=None):
    tool_input = {"command": command, **(extra_input or {})}
    stdin_data = {
        "tool_name": "Bash",
        "tool_input": tool_input,
        "session_id": session_id,
    }
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(stdin_data)))
    with pytest.raises(SystemExit) as exc_info:
        pps.main()
    return exc_info.value.code


def test_non_pr_create_command_is_no_op(monkeypatch, capsys):
    code = run_main(monkeypatch, "gh pr view 5")
    assert code == 0
    assert capsys.readouterr().out == ""


def test_appends_receipt_to_existing_body_flag(monkeypatch, capsys):
    code = run_main(monkeypatch, 'gh pr create --title x --body "original body"')
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    hso = payload["hookSpecificOutput"]
    assert hso["permissionDecision"] == "allow"
    new_command = hso["updatedInput"]["command"]
    assert "original body" in new_command
    assert "AI 관여도" in new_command


def test_adds_body_flag_when_none_given(monkeypatch, capsys):
    code = run_main(monkeypatch, "gh pr create --title x")
    payload = json.loads(capsys.readouterr().out)
    new_command = payload["hookSpecificOutput"]["updatedInput"]["command"]
    assert "--body" in new_command
    assert "AI 관여도" in new_command


def test_preserves_other_tool_input_fields(monkeypatch, capsys):
    code = run_main(
        monkeypatch,
        "gh pr create --title x",
        extra_input={"description": "keep me", "timeout": 30},
    )
    payload = json.loads(capsys.readouterr().out)
    updated = payload["hookSpecificOutput"]["updatedInput"]
    assert updated["description"] == "keep me"
    assert updated["timeout"] == 30


def test_skips_body_file_form(monkeypatch, capsys):
    code = run_main(monkeypatch, "gh pr create --title x --body-file /tmp/body.md")
    assert code == 0
    assert capsys.readouterr().out == ""


def test_includes_prompt_count_when_session_log_exists(monkeypatch, capsys, tmp_path):
    import os

    log_dir = tmp_path / "sessions"
    log_dir.mkdir()
    (log_dir / "s2.jsonl").write_text(
        json.dumps({"event": "prompt", "prompt": "a"})
        + "\n"
        + json.dumps({"event": "prompt", "prompt": "b"})
        + "\n"
    )
    real_expanduser = os.path.expanduser
    monkeypatch.setattr(
        os.path,
        "expanduser",
        lambda p: (
            p.replace("~/.claude/hooks-logs", str(tmp_path))
            if "hooks-logs" in p
            else real_expanduser(p)
        ),
    )
    code = run_main(monkeypatch, "gh pr create --title x", session_id="s2")
    payload = json.loads(capsys.readouterr().out)
    new_command = payload["hookSpecificOutput"]["updatedInput"]["command"]
    assert "프롬프트 수: 2" in new_command


def test_main_exits_cleanly_on_malformed_stdin(monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO("not json"))
    with pytest.raises(SystemExit) as exc_info:
        pps.main()
    assert exc_info.value.code == 0


def test_count_session_prompts_none_when_log_missing():
    assert pps.count_session_prompts("no-such-session") is None


def test_inject_receipt_into_command_no_body_flag():
    result = pps.inject_receipt_into_command("gh pr create --title x", "RECEIPT")
    assert "--body" in result
    assert "RECEIPT" in result


def test_inject_receipt_into_command_equals_form():
    result = pps.inject_receipt_into_command("gh pr create --body=short", "RECEIPT")
    assert "RECEIPT" in result
    assert "short" in result


# --- TASK-28: compound commands / phrase inside quoted args ---------------

import shlex as _shlex
import subprocess

PRC = "gh pr create"


def _new_command(capsys):
    out = capsys.readouterr().out
    if not out:
        return None
    return json.loads(out)["hookSpecificOutput"]["updatedInput"]["command"]


def _body_of(segment):
    tokens = _shlex.split(segment)
    return tokens[tokens.index("--body") + 1]


def test_cd_and_chain_keeps_cd_intact(monkeypatch, capsys):
    cmd = f'cd /tmp/some-dir && {PRC} --title "t" --body "b"'
    assert run_main(monkeypatch, cmd) == 0
    new = _new_command(capsys)
    assert new is not None
    assert new.startswith("cd /tmp/some-dir && ")
    body = _body_of(new[len("cd /tmp/some-dir && ") :])
    assert body.startswith("b\n\n") and "AI 관여도" in body


def test_pipe_to_tail_keeps_pipe_intact(monkeypatch, capsys):
    cmd = f'{PRC} --title "t" --body "b" | tail -1'
    assert run_main(monkeypatch, cmd) == 0
    new = _new_command(capsys)
    assert new is not None
    assert new.endswith(" | tail -1")
    assert "AI 관여도" in _body_of(new[: -len(" | tail -1")])


def test_semicolon_chain_preserved(monkeypatch, capsys):
    cmd = f'make build; {PRC} --title "t" --body "b"'
    assert run_main(monkeypatch, cmd) == 0
    new = _new_command(capsys)
    assert new is not None
    assert new.startswith("make build; ")
    assert "AI 관여도" in _body_of(new[len("make build; ") :])


def test_or_chain_preserved(monkeypatch, capsys):
    cmd = f'{PRC} --title "t" --body "b" || echo "failed && done"'
    assert run_main(monkeypatch, cmd) == 0
    new = _new_command(capsys)
    assert new is not None
    assert new.endswith(' || echo "failed && done"')
    assert "AI 관여도" in _body_of(new[: -len(' || echo "failed && done"')])


def test_phrase_inside_quoted_arg_is_untouched(monkeypatch, capsys):
    cmd = f'backlog draft create "x" -d "mentions {PRC} && | inside text"'
    assert run_main(monkeypatch, cmd) == 0
    assert capsys.readouterr().out == ""


def test_phrase_inside_quoted_arg_of_compound_is_untouched(monkeypatch, capsys):
    cmd = f"cd /tmp && git commit -m 'note: {PRC} later' | tail -1"
    assert run_main(monkeypatch, cmd) == 0
    assert capsys.readouterr().out == ""


def test_newline_separated_commands_preserved(monkeypatch, capsys):
    cmd = f'echo one\n{PRC} --title "t" --body "b"'
    assert run_main(monkeypatch, cmd) == 0
    new = _new_command(capsys)
    assert new is not None
    assert new.startswith("echo one\n")


def test_two_pr_segments_pass_through(monkeypatch, capsys):
    cmd = f"{PRC} --title a && {PRC} --title b"
    assert run_main(monkeypatch, cmd) == 0
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize(
    "cmd",
    [
        f"{PRC} --title t --body \"$(cat <<'EOF'\nhello && world\nEOF\n)\"",
        f"{PRC} --title t --body `cat body.md`",
        f"cat <<EOF | {PRC} --title t\nbody\nEOF",
        f"( cd /tmp && {PRC} --title t --body b )",
        f'{PRC} --title t --body "$BODY"',
        f"{PRC} --title t --body b > /tmp/out.txt 2>&1",
        f"{PRC} --title t --body b # trailing comment && x",
        f"{PRC} --title t --body b*",
        f'{PRC} --title t --body "a\\\nb"',
        f"echo ${{x:-a;b}} && {PRC} --title t",
        f"echo $'it\\'s; ok' && {PRC} --title t",
        f'{PRC} --title t --body "costs \\$5"',
    ],
)
def test_risky_constructs_pass_through_unchanged(monkeypatch, capsys, cmd):
    assert run_main(monkeypatch, cmd) == 0
    assert capsys.readouterr().out == ""


def test_compound_rewrite_runs_correctly_in_bash(monkeypatch, capsys, tmp_path):
    """Execute the rewritten command with a fake gh to prove shell semantics survive."""
    cmd = f'cd {tmp_path} && {PRC} --title "t" --body "line1" | tail -1'
    assert run_main(monkeypatch, cmd) == 0
    new = _new_command(capsys)
    assert new is not None
    script = 'gh() { printf "%s|" "$@"; echo; }\n' + new
    result = subprocess.run(["bash", "-c", script], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    # tail -1 keeps only the last line of the receipt-bearing output
    assert result.stdout.strip() == "- 작성 도구: Claude Code|"


@pytest.mark.parametrize(
    "cmd",
    [
        f'{PRC} --title "a \\"q\\" b" --body \'it has && and | and ; inside\'',
        f'echo pre; {PRC} -t x --body "multi\nline \\\\ body" && echo post',
        f"false || {PRC} --title 'x' --body=eq | cat",
        f"echo a | {PRC} --title x",
    ],
)
def test_rewrite_matches_bash_argv_except_receipt(monkeypatch, capsys, cmd):
    """Differential check: bash sees the same argv for every command, with
    only the receipt appended to the PR body."""
    assert run_main(monkeypatch, cmd) == 0
    new = _new_command(capsys)
    assert new is not None
    fake = 'gh() { printf "<%s>" "$@"; echo; }; echo() { printf "E:%s\\n" "$*"; }\n'

    def run(c):
        r = subprocess.run(["bash", "-c", fake + c], capture_output=True, text=True)
        assert r.stderr == ""
        return r.stdout

    before, after = run(cmd), run(new)
    stripped = re.sub(
        r"(\n\n)?---\n\*\*AI 관여도.*?- 작성 도구: Claude Code", "", after, flags=re.S
    )
    assert stripped != after
    stripped = stripped.replace("<--body><>", "")
    assert stripped == before


def test_single_command_still_stamped_exactly_once(monkeypatch, capsys):
    cmd = f'{PRC} --title "t" --body "b"'
    assert run_main(monkeypatch, cmd) == 0
    new = _new_command(capsys)
    assert new is not None
    assert _body_of(new).count("AI 관여도") == 1


# --- TASK-41: defensive branches --------------------------------------------


def test_count_session_prompts_skips_corrupt_lines_and_non_prompt_events(
    monkeypatch, tmp_path
):
    import os

    log_dir = tmp_path / "sessions"
    log_dir.mkdir()
    (log_dir / "s3.jsonl").write_text(
        json.dumps({"event": "prompt"})
        + "\n{not json\n"
        + json.dumps({"event": "tool"})
        + "\n"
        + json.dumps({"event": "prompt"})
        + "\n"
    )
    real_expanduser = os.path.expanduser
    monkeypatch.setattr(
        os.path,
        "expanduser",
        lambda p: (
            p.replace("~/.claude/hooks-logs", str(tmp_path))
            if "hooks-logs" in p
            else real_expanduser(p)
        ),
    )
    assert pps.count_session_prompts("s3") == 2


def test_inject_receipt_returns_command_unchanged_when_unparseable():
    cmd = 'gh pr create --title "unterminated'
    assert pps.inject_receipt_into_command(cmd, "RECEIPT") == cmd


def test_trailing_escaped_space_segment_is_left_byte_identical(monkeypatch, capsys):
    # Stripping the trailing blank leaves a dangling backslash shlex can't
    # parse; inject_receipt_into_command then gives the segment back as-is.
    cmd = f"{PRC} --title x\\ ; echo hi"
    assert run_main(monkeypatch, cmd) == 0
    new = _new_command(capsys)
    assert new == cmd
    assert "AI 관여도" not in new


@pytest.mark.parametrize(
    "cmd",
    [
        f"{PRC} --title t --body b &>/dev/null",  # &> redirection
        f'{PRC} --title "unterminated',  # unterminated quote
        f"{PRC} --title t \\",  # trailing backslash: shlex can't split the segment
    ],
)
def test_unsafe_or_unparseable_pr_command_passes_through_unstamped(
    monkeypatch, capsys, cmd
):
    assert run_main(monkeypatch, cmd) == 0
    assert capsys.readouterr().out == ""


def test_ampersand_redirection_marks_only_its_segment_unsafe():
    segments = pps.split_top_level_segments("echo a &>/dev/null; gh pr create")
    assert [safe for _, _, safe in segments] == [False, True]
