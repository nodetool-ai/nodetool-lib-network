import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime
import email
from email.message import EmailMessage

from nodetool.lib.network.imap import (
    create_gmail_connection,
    decode_bytes_with_fallback,
    fetch_emails,
    get_email_body,
    build_imap_query,
    search_emails,
    EmailFields,
    ConfigureIMAP,
    IMAPSearch,
)
from nodetool.metadata.types import (
    Email,
    IMAPConnection,
    EmailSearchCriteria,
    Datetime,
    EmailFlag,
)
from nodetool.workflows.processing_context import ProcessingContext


class TestCreateGmailConnection:
    def test_create_gmail_connection_valid(self):
        connection = create_gmail_connection("test@gmail.com", "app_password")
        assert connection.host == "imap.gmail.com"
        assert connection.port == 993
        assert connection.username == "test@gmail.com"
        assert connection.password == "app_password"
        assert connection.use_ssl is True

    def test_create_gmail_connection_empty_email(self):
        with pytest.raises(ValueError, match="Email address is required"):
            create_gmail_connection("", "app_password")

    def test_create_gmail_connection_empty_password(self):
        with pytest.raises(ValueError, match="App password is required"):
            create_gmail_connection("test@gmail.com", "")


class TestDecodeBytes:
    def test_decode_utf8(self):
        result = decode_bytes_with_fallback("hello".encode("utf-8"))
        assert result == "hello"

    def test_decode_latin1(self):
        result = decode_bytes_with_fallback("café".encode("latin-1"))
        assert result == "café"

    def test_decode_fallback(self):
        # Create bytes that will fail with the default encodings
        test_bytes = b"\x80\x81\x82\x83"
        result = decode_bytes_with_fallback(test_bytes, encodings=("utf-8",))
        assert result == ""


class TestFetchEmails:
    def setup_mock_email(self):
        msg = EmailMessage()
        msg["Subject"] = "Test Subject"
        msg["From"] = "sender@example.com"
        msg["Date"] = "Thu, 1 Jan 2023 12:00:00 +0000"
        msg.set_content("Test body")
        return msg

    @patch("email.message_from_bytes")
    def test_fetch_emails(self, mock_message_from_bytes):
        # Setup
        mock_imap = Mock()
        mock_imap.fetch.return_value = ("OK", [(b"1", b"raw_email_data")])

        mock_email_msg = self.setup_mock_email()
        mock_message_from_bytes.return_value = mock_email_msg

        # Execute
        result = fetch_emails(mock_imap, ["1"])

        # Assert
        assert len(result) == 1
        assert result[0].id == "1"
        assert result[0].subject == "Test Subject"
        assert result[0].sender == "sender@example.com"
        assert isinstance(result[0].date, Datetime)
        assert result[0].body == "Test body"

    @patch("email.message_from_bytes")
    def test_fetch_emails_batch_processing(self, mock_message_from_bytes):
        # Setup
        mock_imap = Mock()
        mock_imap.fetch.return_value = ("OK", [(b"1", b"raw_email_data")])

        mock_email_msg = self.setup_mock_email()
        mock_message_from_bytes.return_value = mock_email_msg

        # Execute with 150 message IDs and batch size of 100
        message_ids = [str(i) for i in range(150)]
        result = fetch_emails(mock_imap, message_ids, batch_size=100)

        # Assert
        assert len(result) == 150
        assert mock_imap.fetch.call_count == 150


class TestGetEmailBody:
    def test_get_email_body_plain_text(self):
        # Create a multipart email with text/plain
        msg = EmailMessage()
        msg.set_content("Plain text content")

        result = get_email_body(msg)
        assert result == "Plain text content"

    def test_get_email_body_html(self):
        # Create a multipart email with text/html
        msg = EmailMessage()
        msg.add_alternative(
            "<html><body><p>HTML content</p></body></html>", subtype="html"
        )

        with patch(
            "nodetool.lib.network.imap.convert_html_to_text",
            return_value="HTML content",
        ):
            result = get_email_body(msg)
            assert result == "HTML content"

    def test_get_email_body_multipart_preference(self):
        # Create a multipart email with both text/plain and text/html
        msg = EmailMessage()
        msg.set_content("Plain text content")
        msg.add_alternative(
            "<html><body><p>HTML content</p></body></html>", subtype="html"
        )

        result = get_email_body(msg)
        assert result == "Plain text content\n"


class TestBuildImapQuery:
    def test_build_query_empty_criteria(self):
        criteria = EmailSearchCriteria()
        query = build_imap_query(criteria)
        assert query == "ALL"

    def test_build_query_from_address(self):
        criteria = EmailSearchCriteria(from_address="test@example.com")
        query = build_imap_query(criteria)
        assert query == 'FROM "test@example.com"'

    def test_build_query_multiple_criteria(self):
        criteria = EmailSearchCriteria(
            from_address="sender@example.com", subject="Test Subject", text="important"
        )
        query = build_imap_query(criteria)
        assert 'FROM "sender@example.com"' in query
        assert 'SUBJECT "Test Subject"' in query
        assert 'TEXT "important"' in query

    # def test_build_query_with_date(self):
    #     date = Datetime.from_datetime(datetime(2023, 1, 1))
    #     date_condition = EmailDateCondition(criteria=EmailDateCriteria.SINCE, date=date)
    #     criteria = EmailSearchCriteria(date_condition=date_condition)
    #     query = build_imap_query(criteria)
    #     assert 'SINCE "01-Jan-2023"' in query

    def test_build_query_with_flags(self):
        criteria = EmailSearchCriteria(flags=[EmailFlag.SEEN, EmailFlag.FLAGGED])
        query = build_imap_query(criteria)
        assert "SEEN" in query
        assert "FLAGGED" in query


class TestSearchEmails:
    @patch("imaplib.IMAP4_SSL")
    def test_search_emails(self, mock_imap_class):
        # Setup mock IMAP connection
        mock_imap = MagicMock()
        mock_imap_class.return_value = mock_imap

        # Mock search results
        mock_imap.search.return_value = ("OK", [b"1 2 3"])

        # Mock fetch results
        mock_email = EmailMessage()
        mock_email["Subject"] = "Test Subject"
        mock_email["From"] = "sender@example.com"
        mock_email["Date"] = "Thu, 1 Jan 2023 12:00:00 +0000"
        mock_email.set_content("Test body")

        with patch("nodetool.lib.network.imap.fetch_emails") as mock_fetch:
            mock_fetch.return_value = [
                Email(
                    id="1",
                    subject="Test Subject",
                    sender="sender@example.com",
                    date=Datetime.from_datetime(datetime(2023, 1, 1)),
                    body="Test body",
                )
            ]

            # Execute
            connection = IMAPConnection(
                host="imap.example.com",
                port=993,
                username="user",
                password="pass",
                use_ssl=True,
            )
            criteria = EmailSearchCriteria(subject="Test")
            result = search_emails(connection, criteria)

            # Assert
            assert len(result) == 1
            assert result[0].subject == "Test Subject"
            mock_imap.login.assert_called_once_with("user", "pass")
            mock_imap.select.assert_called_once_with("INBOX")
            mock_imap.logout.assert_called_once()


class TestEmailFields:
    async def test_email_fields_process(self):
        # Setup
        email = Email(
            id="1",
            subject="Test Subject",
            sender="sender@example.com",
            date=Datetime.from_datetime(datetime(2023, 1, 1)),
            body="Test body",
        )
        node = EmailFields(email=email)
        context = ProcessingContext(user_id="test_user", auth_token="test_token")

        # Execute
        result = await node.process(context)

        # Assert
        assert result["id"] == "1"
        assert result["subject"] == "Test Subject"
        assert result["sender"] == "sender@example.com"
        assert result["date"] == email.date
        assert result["body"] == "Test body"

    async def test_email_fields_missing_email(self):
        node = EmailFields()
        context = ProcessingContext(user_id="test_user", auth_token="test_token")

        with pytest.raises(ValueError, match="Email is required"):
            await node.process(context)


class TestConfigureIMAP:
    async def test_configure_imap_valid(self):
        # Setup
        node = ConfigureIMAP(
            host="imap.example.com",
            port=993,
            username="user@example.com",
            password="password",
            use_ssl=True,
        )
        context = ProcessingContext(user_id="test_user", auth_token="test_token")

        # Execute
        result = await node.process(context)

        # Assert
        assert result.host == "imap.example.com"
        assert result.port == 993
        assert result.username == "user@example.com"
        assert result.password == "password"
        assert result.use_ssl is True

    async def test_configure_imap_incomplete(self):
        # Setup with missing host
        node = ConfigureIMAP(host="", username="user@example.com", password="password")
        context = ProcessingContext(user_id="test_user", auth_token="test_token")

        # Execute and assert
        with pytest.raises(ValueError, match="IMAP configuration is incomplete"):
            await node.process(context)


class TestIMAPSearch:
    @patch("nodetool.lib.network.imap.search_emails")
    async def test_imap_search_process(self, mock_search_emails):
        # Setup
        mock_search_emails.return_value = [
            Email(
                id="1",
                subject="Test Subject",
                sender="sender@example.com",
                date=Datetime.from_datetime(datetime(2023, 1, 1)),
                body="Test body",
            )
        ]

        connection = IMAPConnection(
            host="imap.example.com",
            port=993,
            username="user",
            password="pass",
            use_ssl=True,
        )
        criteria = EmailSearchCriteria(subject="Test")

        node = IMAPSearch(
            connection=connection, search_criteria=criteria, max_results=10
        )
        context = ProcessingContext(user_id="test_user", auth_token="test_token")

        # Execute
        result = await node.process(context)

        # Assert
        assert len(result) == 1
        assert result[0].subject == "Test Subject"
        mock_search_emails.assert_called_once_with(connection, criteria, 10)
