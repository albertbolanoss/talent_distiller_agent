from candidate_match_agent.libs.file_reader.errors import UnsupportedFileTypeError


def test_message_includes_extension_and_supported_list():
    error = UnsupportedFileTypeError(".csv", [".pdf", ".txt"])

    assert str(error) == "Unsupported file type '.csv'. Supported extensions: .pdf, .txt"


def test_exposes_extension_and_supported_as_attributes():
    error = UnsupportedFileTypeError(".csv", [".pdf", ".txt"])

    assert error.extension == ".csv"
    assert error.supported == [".pdf", ".txt"]


def test_empty_extension_is_rendered_as_none():
    error = UnsupportedFileTypeError("", [".pdf", ".txt"])

    assert "'(none)'" in str(error)


def test_is_a_value_error():
    assert isinstance(UnsupportedFileTypeError(".csv", [".pdf"]), ValueError)
