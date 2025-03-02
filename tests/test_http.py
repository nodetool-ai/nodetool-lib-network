import pytest
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

from nodetool.nodes.lib.network.http import (
    HTTPBaseNode,
    GetRequest,
    PostRequest,
    PutRequest,
    DeleteRequest,
    HeadRequest,
    FetchPage,
    ImageDownloader,
    GetRequestBinary,
    GetRequestDocument,
    PostRequestBinary,
    FilterValidURLs,
    DownloadFiles,
    JSONPostRequest,
    JSONPutRequest,
    JSONPatchRequest,
    JSONGetRequest,
)
from nodetool.metadata.types import DataframeRef, FilePath, DocumentRef, ImageRef
from nodetool.workflows.processing_context import ProcessingContext
from nodetool.workflows.types import NodeProgress


class MockResponse:
    def __init__(
        self,
        content=b"test content",
        status=200,
        headers=None,
        encoding="utf-8",
        json_data=None,
    ):
        self.content = content
        self.status = status
        self.headers = headers or {}
        self.encoding = encoding
        self._json_data = json_data

    def json(self):
        return self._json_data


@pytest.fixture
def mock_context():
    context = MagicMock(spec=ProcessingContext)
    context.http_get = AsyncMock(return_value=MockResponse())
    context.http_post = AsyncMock(return_value=MockResponse())
    context.http_put = AsyncMock(return_value=MockResponse())
    context.http_delete = AsyncMock(return_value=MockResponse())
    context.http_head = AsyncMock(
        return_value=MockResponse(headers={"Content-Type": "text/html"})
    )
    context.http_patch = AsyncMock(return_value=MockResponse())
    context.image_from_bytes = AsyncMock(return_value=ImageRef())
    context.post_message = MagicMock()
    return context


class TestHTTPBaseNode:
    def test_is_visible(self):
        assert not HTTPBaseNode.is_visible()
        assert GetRequest.is_visible()

    def test_get_request_kwargs(self):
        node = HTTPBaseNode(url="https://example.com", auth="basic_auth")
        kwargs = node.get_request_kwargs()
        assert kwargs["auth"] == "basic_auth"

    def test_get_basic_fields(self):
        assert HTTPBaseNode.get_basic_fields() == ["url"]


class TestGetRequest:
    @pytest.mark.asyncio
    async def test_process(self, mock_context):
        node = GetRequest(url="https://example.com")
        result = await node.process(mock_context)

        mock_context.http_get.assert_called_once_with("https://example.com", auth=None)
        assert result == "test content"


class TestPostRequest:
    @pytest.mark.asyncio
    async def test_process(self, mock_context):
        node = PostRequest(url="https://example.com", data="test data")
        result = await node.process(mock_context)

        mock_context.http_post.assert_called_once_with(
            "https://example.com", data="test data", auth=None
        )
        assert result == "test content"


class TestPutRequest:
    @pytest.mark.asyncio
    async def test_process(self, mock_context):
        node = PutRequest(url="https://example.com", data="test data")
        result = await node.process(mock_context)

        mock_context.http_put.assert_called_once_with(
            "https://example.com", data="test data", auth=None
        )
        assert result == "test content"


class TestDeleteRequest:
    @pytest.mark.asyncio
    async def test_process(self, mock_context):
        node = DeleteRequest(url="https://example.com")
        result = await node.process(mock_context)

        mock_context.http_delete.assert_called_once_with(
            "https://example.com", auth=None
        )
        assert result == "test content"


class TestHeadRequest:
    @pytest.mark.asyncio
    async def test_process(self, mock_context):
        node = HeadRequest(url="https://example.com")
        result = await node.process(mock_context)

        mock_context.http_head.assert_called_once_with("https://example.com", auth=None)
        assert result == {"Content-Type": "text/html"}


class TestFetchPage:
    @pytest.mark.asyncio
    @patch("nodetool.lib.network.http.webdriver.Chrome")
    async def test_process_success(self, mock_chrome, mock_context):
        mock_driver = MagicMock()
        mock_driver.page_source = "<html><body>Test Page</body></html>"
        mock_chrome.return_value = mock_driver

        node = FetchPage(url="https://example.com", wait_time=5)
        result = await node.process(mock_context)

        assert result["html"] == "<html><body>Test Page</body></html>"
        assert result["success"] is True
        assert result["error_message"] is None
        mock_driver.quit.assert_called_once()

    @pytest.mark.asyncio
    @patch("nodetool.lib.network.http.webdriver.Chrome")
    async def test_process_failure(self, mock_chrome, mock_context):
        mock_driver = MagicMock()
        mock_driver.get.side_effect = Exception("Connection error")
        mock_chrome.return_value = mock_driver

        node = FetchPage(url="https://example.com", wait_time=5)
        result = await node.process(mock_context)

        assert result["html"] == ""
        assert result["success"] is False
        assert "Connection error" in result["error_message"]
        mock_driver.quit.assert_called_once()


class TestImageDownloader:
    @pytest.mark.asyncio
    @patch("nodetool.lib.network.http.aiohttp.ClientSession")
    async def test_process(self, mock_session, mock_context):
        mock_session_instance = AsyncMock()
        mock_session.return_value.__aenter__.return_value = mock_session_instance

        # Mock responses for different image URLs
        responses = {
            "https://example.com/image1.jpg": AsyncMock(
                __aenter__=AsyncMock(
                    return_value=MagicMock(
                        status=200, read=AsyncMock(return_value=b"image1 data")
                    )
                )
            ),
            "https://example.com/image2.png": AsyncMock(
                __aenter__=AsyncMock(
                    return_value=MagicMock(
                        status=200, read=AsyncMock(return_value=b"image2 data")
                    )
                )
            ),
            "https://example.com/invalid.jpg": AsyncMock(
                __aenter__=AsyncMock(return_value=MagicMock(status=404))
            ),
            "https://example.com/error.png": AsyncMock(
                __aenter__=AsyncMock(side_effect=Exception("Connection error"))
            ),
        }

        def mock_get(url, **kwargs):
            return responses.get(url)

        mock_session_instance.get = mock_get

        images = [
            "image1.jpg",
            "image2.png",
            "invalid.jpg",
            "error.png",
        ]

        node = ImageDownloader(
            images=images, base_url="https://example.com/", max_concurrent_downloads=2
        )

        result = await node.process(mock_context)

        # Verify results
        assert len(result["images"]) == 2
        assert len(result["failed_urls"]) == 2
        assert "https://example.com/invalid.jpg" in result["failed_urls"]
        assert "https://example.com/error.png" in result["failed_urls"]


class TestGetRequestBinary:
    @pytest.mark.asyncio
    async def test_process(self, mock_context):
        node = GetRequestBinary(url="https://example.com/file.bin")
        result = await node.process(mock_context)

        mock_context.http_get.assert_called_once_with(
            "https://example.com/file.bin", auth=None
        )
        assert result == b"test content"


class TestGetRequestDocument:
    @pytest.mark.asyncio
    async def test_process(self, mock_context):
        node = GetRequestDocument(url="https://example.com/doc.pdf")
        result = await node.process(mock_context)

        mock_context.http_get.assert_called_once_with(
            "https://example.com/doc.pdf", auth=None
        )
        assert isinstance(result, DocumentRef)
        assert result.data == b"test content"


class TestPostRequestBinary:
    @pytest.mark.asyncio
    async def test_process_with_string_data(self, mock_context):
        node = PostRequestBinary(url="https://example.com/upload", data="test data")
        result = await node.process(mock_context)

        mock_context.http_post.assert_called_once_with(
            "https://example.com/upload", data="test data", auth=None
        )
        assert result == b"test content"

    @pytest.mark.asyncio
    async def test_process_with_binary_data(self, mock_context):
        binary_data = b"binary test data"
        node = PostRequestBinary(url="https://example.com/upload", data=binary_data)
        result = await node.process(mock_context)

        mock_context.http_post.assert_called_once_with(
            "https://example.com/upload", data=binary_data, auth=None
        )
        assert result == b"test content"


class TestFilterValidURLs:
    @pytest.mark.asyncio
    @patch("nodetool.lib.network.http.aiohttp.ClientSession")
    async def test_process(self, mock_session, mock_context):
        mock_session_instance = AsyncMock()
        mock_session.return_value.__aenter__.return_value = mock_session_instance

        # Mock responses for different URLs
        responses = {
            "https://valid1.com": AsyncMock(
                __aenter__=AsyncMock(return_value=MagicMock(status=200))
            ),
            "https://valid2.com": AsyncMock(
                __aenter__=AsyncMock(return_value=MagicMock(status=301))
            ),
            "https://invalid.com": AsyncMock(
                __aenter__=AsyncMock(return_value=MagicMock(status=404))
            ),
            "https://error.com": AsyncMock(
                __aenter__=AsyncMock(side_effect=Exception("Connection error"))
            ),
        }

        def mock_head(url, **kwargs):
            return responses.get(url)

        mock_session_instance.head = mock_head

        node = FilterValidURLs(
            urls=[
                "https://valid1.com",
                "https://valid2.com",
                "https://invalid.com",
                "https://error.com",
            ],
            max_concurrent_requests=2,
        )

        result = await node.process(mock_context)

        assert set(result) == {"https://valid1.com", "https://valid2.com"}


class TestDownloadFiles:
    @pytest.mark.asyncio
    @patch("nodetool.lib.network.http.aiohttp.ClientSession")
    @patch("nodetool.lib.network.http.os.makedirs")
    @patch("nodetool.lib.network.http.open")
    async def test_process(self, mock_open, mock_makedirs, mock_session, mock_context):
        mock_session_instance = AsyncMock()
        mock_session.return_value.__aenter__.return_value = mock_session_instance

        # Mock responses for different URLs
        responses = {
            "https://example.com/file1.txt": AsyncMock(
                __aenter__=AsyncMock(
                    return_value=MagicMock(
                        status=200,
                        headers={"Content-Disposition": "filename=file1.txt"},
                        read=AsyncMock(return_value=b"file1 content"),
                    )
                )
            ),
            "https://example.com/file2.txt": AsyncMock(
                __aenter__=AsyncMock(
                    return_value=MagicMock(
                        status=200,
                        headers={},
                        read=AsyncMock(return_value=b"file2 content"),
                    )
                )
            ),
            "https://example.com/error": AsyncMock(
                __aenter__=AsyncMock(return_value=MagicMock(status=404))
            ),
        }

        def mock_get(url, **kwargs):
            return responses.get(url)

        mock_session_instance.get = mock_get

        with tempfile.TemporaryDirectory() as temp_dir:
            node = DownloadFiles(
                urls=[
                    "https://example.com/file1.txt",
                    "https://example.com/file2.txt",
                    "https://example.com/error",
                ],
                output_folder=FilePath(path=temp_dir),
                max_concurrent_downloads=2,
            )

            result = await node.process(mock_context)

            assert len(result["successful"]) == 2
            assert "https://example.com/error" in result["failed"]
            assert mock_context.post_message.call_count == 2
            assert isinstance(mock_context.post_message.call_args[0][0], NodeProgress)


class TestJSONPostRequest:
    @pytest.mark.asyncio
    async def test_process(self, mock_context):
        mock_context.http_post.return_value = MockResponse(
            json_data={"status": "success"}
        )

        node = JSONPostRequest(
            url="https://api.example.com/data", data={"name": "test", "value": 123}
        )
        result = await node.process(mock_context)

        mock_context.http_post.assert_called_once_with(
            "https://api.example.com/data",
            json={"name": "test", "value": 123},
            headers={"Content-Type": "application/json"},
            auth=None,
        )
        assert result == {"status": "success"}


class TestJSONPutRequest:
    @pytest.mark.asyncio
    async def test_process(self, mock_context):
        mock_context.http_put.return_value = MockResponse(
            json_data={"status": "updated"}
        )

        node = JSONPutRequest(
            url="https://api.example.com/data/1", data={"name": "updated", "value": 456}
        )
        result = await node.process(mock_context)

        mock_context.http_put.assert_called_once_with(
            "https://api.example.com/data/1",
            json={"name": "updated", "value": 456},
            headers={"Content-Type": "application/json"},
            auth=None,
        )
        assert result == {"status": "updated"}


class TestJSONPatchRequest:
    @pytest.mark.asyncio
    async def test_process(self, mock_context):
        mock_context.http_patch.return_value = MockResponse(
            json_data={"status": "patched"}
        )

        node = JSONPatchRequest(
            url="https://api.example.com/data/1", data={"value": 789}
        )
        result = await node.process(mock_context)

        mock_context.http_patch.assert_called_once_with(
            "https://api.example.com/data/1",
            json={"value": 789},
            headers={"Content-Type": "application/json"},
            auth=None,
        )
        assert result == {"status": "patched"}


class TestJSONGetRequest:
    @pytest.mark.asyncio
    async def test_process(self, mock_context):
        mock_context.http_get.return_value = MockResponse(json_data={"data": [1, 2, 3]})

        node = JSONGetRequest(url="https://api.example.com/data")
        result = await node.process(mock_context)

        mock_context.http_get.assert_called_once_with(
            "https://api.example.com/data",
            headers={"Accept": "application/json"},
            auth=None,
        )
        assert result == {"data": [1, 2, 3]}
