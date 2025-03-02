import pytest
from datetime import datetime
from unittest.mock import patch, MagicMock
from nodetool.workflows.processing_context import ProcessingContext
from nodetool.metadata.types import Datetime, RSSEntry
from nodetool.nodes.lib.network.rss import (
    FetchRSSFeed,
    RSSEntryFields,
    ExtractFeedMetadata,
)


@pytest.fixture
def processing_context():
    return ProcessingContext(user_id="test_user", auth_token="test_token")


@pytest.fixture
def mock_feedparser():
    with patch("nodetool.lib.network.rss.feedparser") as mock_feed:
        # Create a mock feed response
        mock_feed.parse.return_value = MagicMock(
            feed=MagicMock(
                title="Test Feed",
                description="Test Description",
                link="https://example.com",
                language="en-us",
                updated="Mon, 01 Jan 2023 12:00:00 GMT",
                generator="Test Generator",
            ),
            entries=[
                MagicMock(
                    title="Test Entry 1",
                    link="https://example.com/entry1",
                    published_parsed=(2023, 1, 1, 12, 0, 0, 0, 0, 0),
                    summary="Test Summary 1",
                    author="Test Author 1",
                ),
                MagicMock(
                    title="Test Entry 2",
                    link="https://example.com/entry2",
                    published_parsed=(2023, 1, 2, 12, 0, 0, 0, 0, 0),
                    summary="Test Summary 2",
                    author="Test Author 2",
                ),
            ],
        )
        yield mock_feed


class TestFetchRSSFeed:
    async def test_process(self, processing_context, mock_feedparser):
        # Arrange
        node = FetchRSSFeed(url="https://example.com/rss")

        # Act
        result = await node.process(processing_context)

        # Assert
        assert len(result) == 2
        assert isinstance(result[0], RSSEntry)
        assert result[0].title == "Test Entry 1"
        assert result[0].link == "https://example.com/entry1"
        assert result[0].published.to_datetime() == datetime(2023, 1, 1, 12, 0, 0)
        assert result[0].summary == "Test Summary 1"
        assert result[0].author == "Test Author 1"

        mock_feedparser.parse.assert_called_once_with("https://example.com/rss")

    async def test_process_with_missing_fields(self, processing_context):
        # Arrange
        with patch("nodetool.lib.network.rss.feedparser") as mock_feed:
            mock_feed.parse.return_value = MagicMock(
                feed=MagicMock(),
                entries=[
                    MagicMock(
                        # Missing title, link, etc.
                        published_parsed=None  # Test fallback datetime
                    )
                ],
            )
            node = FetchRSSFeed(url="https://example.com/rss")

            # Act
            result = await node.process(processing_context)

            # Assert
            assert len(result) == 1
            assert result[0].title == ""
            assert result[0].link == ""
            assert isinstance(result[0].published.to_datetime(), datetime)
            assert result[0].summary == ""
            assert result[0].author == ""


class TestRSSEntryFields:
    async def test_process(self, processing_context):
        # Arrange
        test_datetime = datetime(2023, 1, 1, 12, 0, 0)
        entry = RSSEntry(
            title="Test Title",
            link="https://example.com/test",
            published=Datetime.from_datetime(test_datetime),
            summary="Test Summary",
            author="Test Author",
        )
        node = RSSEntryFields(entry=entry)

        # Act
        result = await node.process(processing_context)

        # Assert
        assert result["title"] == "Test Title"
        assert result["link"] == "https://example.com/test"
        assert result["published"].to_datetime() == test_datetime
        assert result["summary"] == "Test Summary"
        assert result["author"] == "Test Author"

    def test_return_type(self):
        # Arrange & Act
        return_types = RSSEntryFields.return_type()

        # Assert
        assert return_types["title"] == str
        assert return_types["link"] == str
        assert return_types["published"] == Datetime
        assert return_types["summary"] == str
        assert return_types["author"] == str


class TestExtractFeedMetadata:
    async def test_process(self, processing_context, mock_feedparser):
        # Arrange
        node = ExtractFeedMetadata(url="https://example.com/rss")

        # Act
        result = await node.process(processing_context)

        # Assert
        assert result["title"] == "Test Feed"
        assert result["description"] == "Test Description"
        assert result["link"] == "https://example.com"
        assert result["language"] == "en-us"
        assert result["updated"] == "Mon, 01 Jan 2023 12:00:00 GMT"
        assert result["generator"] == "Test Generator"
        assert result["entry_count"] == 2

        mock_feedparser.parse.assert_called_once_with("https://example.com/rss")

    async def test_process_with_missing_fields(self, processing_context):
        # Arrange
        with patch("nodetool.lib.network.rss.feedparser") as mock_feed:
            mock_feed.parse.return_value = MagicMock(
                feed=MagicMock(), entries=[]  # Empty feed with no attributes
            )
            node = ExtractFeedMetadata(url="https://example.com/rss")

            # Act
            result = await node.process(processing_context)

            # Assert
            assert result["title"] == ""
            assert result["description"] == ""
            assert result["link"] == ""
            assert result["language"] == ""
            assert result["updated"] == ""
            assert result["generator"] == ""
            assert result["entry_count"] == 0
