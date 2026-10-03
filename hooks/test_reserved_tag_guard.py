import io
import json

import pytest

import reserved_tag_guard as rtg


def run_main(monkeypatch, stdin_text):
    monkeypatch.setattr("sys.stdin", io.StringIO(stdin_text))
    with pytest.raises(SystemExit) as exc_info:
        rtg.main()
    return exc_info.value.code


def run_payload(monkeypatch, payload):
    return run_main(monkeypatch, json.dumps(payload))


# --- find_reserved_tags: detection -------------------------------------------


def test_detects_bash_input_pair_in_prose():
    text = "남은 push는 이렇게 하세요:\n<bash-input>git status</bash-input>\n"
    assert rtg.find_reserved_tags(text) == ["bash-input"]


@pytest.mark.parametrize("tag", rtg.RESERVED_TAGS)
def test_detects_every_reserved_tag_opening_form(tag):
    assert rtg.find_reserved_tags(f"hello <{tag}> world") == [tag]


@pytest.mark.parametrize("tag", rtg.RESERVED_TAGS)
def test_detects_every_reserved_tag_closing_form(tag):
    assert rtg.find_reserved_tags(f"hello </{tag}> world") == [tag]


def test_detection_is_case_insensitive():
    assert rtg.find_reserved_tags("<BASH-STDOUT>ok") == ["bash-stdout"]
    assert rtg.find_reserved_tags("</System-Reminder>") == ["system-reminder"]


def test_detects_tag_with_attributes_and_whitespace():
    assert rtg.find_reserved_tags('< bash-input id="1" >x') == ["bash-input"]
    assert rtg.find_reserved_tags("</ bash-stderr >") == ["bash-stderr"]
    assert rtg.find_reserved_tags("<persisted-output\n>") == ["persisted-output"]
    assert rtg.find_reserved_tags("<command-name/>") == ["command-name"]


def test_reports_each_tag_once_in_first_seen_order():
    text = (
        "<bash-stdout>a</bash-stdout> <bash-input>b</bash-input> "
        "<bash-stdout>c</bash-stdout>"
    )
    assert rtg.find_reserved_tags(text) == ["bash-stdout", "bash-input"]


def test_does_not_match_longer_tag_names_sharing_a_prefix():
    assert rtg.find_reserved_tags("<bash-inputs>x</bash-inputs>") == []
    assert rtg.find_reserved_tags("<command-name-x>") == []
    assert rtg.find_reserved_tags("<my-bash-input>") == []


def test_ignores_plain_prose_mention_without_angle_brackets():
    text = "bash-input 태그는 하네스가 쓰는 예약 형식이라 출력하지 않습니다."
    assert rtg.find_reserved_tags(text) == []


def test_ignores_ordinary_html_and_comparisons():
    assert rtg.find_reserved_tags("<div>hi</div> a < b > c <br/>") == []


def test_empty_text():
    assert rtg.find_reserved_tags("") == []


# --- find_reserved_tags: code exclusions --------------------------------------


def test_ignores_tag_inside_backtick_fence():
    text = "예시:\n```\n<bash-input>git status</bash-input>\n```\n끝"
    assert rtg.find_reserved_tags(text) == []


def test_ignores_tag_inside_tilde_fence_with_info_string():
    text = "~~~markdown title=x\n<system-reminder>x</system-reminder>\n~~~\n"
    assert rtg.find_reserved_tags(text) == []


def test_ignores_tag_inside_fence_with_info_string_backticks():
    text = "```bash\n<bash-stdout>ok</bash-stdout>\n```"
    assert rtg.find_reserved_tags(text) == []


def test_detects_tag_after_fence_closes():
    text = "```\n<bash-input>x</bash-input>\n```\n<bash-stdout>y"
    assert rtg.find_reserved_tags(text) == ["bash-stdout"]


def test_unclosed_fence_runs_to_end():
    text = "```\n<bash-input>x</bash-input>\nno closing fence"
    assert rtg.find_reserved_tags(text) == []


def test_fence_closes_only_with_same_char_and_at_least_same_length():
    # ~~~ cannot close a ``` fence; ``` cannot close a ```` fence.
    text = "````\n```\n~~~\n<bash-input>x\n````\n"
    assert rtg.find_reserved_tags(text) == []
    text2 = "````\n<bash-input>x\n```\n<bash-stdout>y\n````\n<bash-stderr>z"
    assert rtg.find_reserved_tags(text2) == ["bash-stderr"]


def test_fence_line_with_trailing_text_does_not_close():
    text = "```\n<bash-input>x\n``` not a close\n<bash-stdout>y\n```\n<bash-stderr>z"
    assert rtg.find_reserved_tags(text) == ["bash-stderr"]


def test_indented_fence_inside_list_item_is_respected():
    text = "1. 예시\n   ```\n   <bash-input>x</bash-input>\n   ```\n"
    assert rtg.find_reserved_tags(text) == []


def test_ignores_tag_inside_inline_code():
    text = "하네스는 `<bash-input>` 블록으로 사용자 실행을 표시합니다."
    assert rtg.find_reserved_tags(text) == []


def test_ignores_tag_inside_multi_backtick_inline_code():
    text = "예: ``<bash-input>`x`</bash-input>`` 처럼 씁니다."
    assert rtg.find_reserved_tags(text) == []


def test_inline_code_needs_matching_backtick_run_length():
    # A lone ` with no matching closer is literal, so the tag is real.
    text = "this ` is literal <bash-input>x"
    assert rtg.find_reserved_tags(text) == ["bash-input"]
    # ``...` is not closed by a single backtick.
    text2 = "``<bash-stdout>` still open"
    assert rtg.find_reserved_tags(text2) == ["bash-stdout"]


def test_detects_tag_outside_inline_code_on_same_line():
    text = "`<bash-input>` 대신 <bash-stdout>ok</bash-stdout>"
    assert rtg.find_reserved_tags(text) == ["bash-stdout"]


# --- main ---------------------------------------------------------------------


def test_main_blocks_on_detection(monkeypatch, capsys):
    code = run_payload(
        monkeypatch,
        {
            "stop_hook_active": False,
            "last_assistant_message": "<bash-input>git status</bash-input>",
        },
    )
    assert code == 2
    err = capsys.readouterr().err
    assert "bash-input" in err
    assert "예약" in err
    assert "실행하지 않았" in err
    assert "코드블록" in err


def test_main_passes_clean_message(monkeypatch, capsys):
    code = run_payload(
        monkeypatch,
        {
            "stop_hook_active": False,
            "last_assistant_message": "```bash\ngit status\n```",
        },
    )
    assert code == 0
    assert capsys.readouterr().err == ""


def test_main_never_blocks_when_stop_hook_active(monkeypatch):
    code = run_payload(
        monkeypatch,
        {
            "stop_hook_active": True,
            "last_assistant_message": "<bash-input>git status</bash-input>",
        },
    )
    assert code == 0


def test_main_passes_when_last_assistant_message_missing(monkeypatch):
    assert run_payload(monkeypatch, {"stop_hook_active": False}) == 0


def test_main_passes_when_last_assistant_message_not_a_string(monkeypatch):
    assert run_payload(monkeypatch, {"last_assistant_message": None}) == 0
    assert run_payload(monkeypatch, {"last_assistant_message": ["<bash-input>"]}) == 0


def test_main_passes_on_malformed_stdin(monkeypatch):
    assert run_main(monkeypatch, "not json at all") == 0


def test_main_passes_on_non_object_json(monkeypatch):
    assert run_main(monkeypatch, "[1, 2]") == 0


def test_main_passes_on_empty_stdin(monkeypatch):
    assert run_main(monkeypatch, "") == 0
