import sys
sys.path.insert(0, "lambda")

import unittest  # noqa: E402
from unittest.mock import MagicMock, patch  # noqa: E402
from botocore.exceptions import ClientError  # noqa: E402
from handler import _parse, _process, handler  # noqa: E402


class TestParse(unittest.TestCase):

    def test_empty_string_returns_empty_format(self):
        # empty input should return format "empty" and None value
        r = _parse("")
        self.assertEqual(r["format"], "empty")
        self.assertIsNone(r["value"])

    def test_json_object_is_parsed_correctly(self):
        # valid JSON should be parsed into a dict
        r = _parse('{"name": "Anirudh", "role": "engineer"}')
        self.assertEqual(r["format"], "json")
        self.assertEqual(r["value"]["name"], "Anirudh")

    def test_key_value_pairs_are_parsed_correctly(self):
        # comma separated key=value pairs should be parsed into a dict
        r = _parse("name=Anirudh,role=engineer")
        self.assertEqual(r["format"], "key_value")
        self.assertEqual(r["value"], {"name": "Anirudh", "role": "engineer"})

    def test_csv_values_are_split_into_list(self):
        # comma separated values without = should be treated as CSV
        r = _parse("foo,bar,baz")
        self.assertEqual(r["format"], "csv")
        self.assertEqual(r["value"], ["foo", "bar", "baz"])

    def test_plain_text_returned_as_is(self):
        # anything that doesn't match other formats should come back as plain text
        r = _parse("hello world")
        self.assertEqual(r["format"], "text")
        self.assertEqual(r["value"], "hello world")

    def test_malformed_json_falls_through_to_next_format(self):
        # bad JSON should not raise, it should try the next format instead
        self.assertNotEqual(_parse("{bad json}")["format"], "json")


class TestProcess(unittest.TestCase):

    def _mock_body(self, content: str):
        m = MagicMock()
        m.read.return_value = content.encode("utf-8")
        return m

    @patch("handler.s3")
    def test_success_returns_parsed_data(self, mock_s3):
        # happy path — file exists, first line is key=value, should parse cleanly
        mock_s3.get_object.return_value = {"Body": self._mock_body("name=Anirudh,role=engineer")}
        r = _process("my-bucket", "test.txt")
        self.assertEqual(r["status"], "success")
        self.assertEqual(r["data"]["format"], "key_value")

    @patch("handler.s3")
    def test_only_reads_first_line_of_file(self, mock_s3):
        # multi-line files should only process the first line
        mock_s3.get_object.return_value = {"Body": self._mock_body("first\nsecond\nthird")}
        r = _process("my-bucket", "test.txt")
        self.assertEqual(r["data"]["value"], "first")

    @patch("handler.s3")
    def test_missing_file_returns_error_status(self, mock_s3):
        # if the file doesn't exist in S3, return error status instead of raising
        mock_s3.get_object.side_effect = ClientError(
            {"Error": {"Code": "NoSuchKey", "Message": "Not found"}}, "GetObject"
        )
        r = _process("my-bucket", "missing.txt")
        self.assertEqual(r["status"], "error")

    @patch("handler.s3")
    def test_unexpected_error_bubbles_up_to_lambda(self, mock_s3):
        # unexpected errors should re-raise so Lambda retries and routes to DLQ
        mock_s3.get_object.side_effect = RuntimeError("unexpected")
        with self.assertRaises(RuntimeError):
            _process("my-bucket", "test.txt")


class TestHandler(unittest.TestCase):

    def _event(self, key: str) -> dict:
        return {"Records": [{"s3": {"bucket": {"name": "my-bucket"}, "object": {"key": key}}}]}

    @patch("handler.s3")
    def test_processes_s3_record_successfully(self, mock_s3):
        # basic end to end — S3 event comes in, file gets processed
        body = MagicMock()
        body.read.return_value = b"hello,world"
        mock_s3.get_object.return_value = {"Body": body}
        r = handler(self._event("file.txt"), None)
        self.assertEqual(r["processed"][0]["status"], "success")

    @patch("handler.s3")
    def test_url_encoded_key_is_decoded_before_s3_call(self, mock_s3):
        # S3 URL-encodes keys with spaces, need to decode before calling get_object
        body = MagicMock()
        body.read.return_value = b"text"
        mock_s3.get_object.return_value = {"Body": body}
        handler(self._event("my+file.txt"), None)
        self.assertEqual(mock_s3.get_object.call_args.kwargs["Key"], "my file.txt")

    @patch("handler.s3")
    def test_empty_event_returns_empty_list(self, mock_s3):
        # no records in the event should return an empty processed list
        r = handler({"Records": []}, None)
        self.assertEqual(r["processed"], [])


if __name__ == "__main__":
    unittest.main()
