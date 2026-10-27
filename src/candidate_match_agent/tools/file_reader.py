"""MCP tool definition for extracting text from documents."""

from typing import Annotated, TypedDict

from claude_agent_sdk import ToolAnnotations, tool

from labs_agent_lib.file_reader import SUPPORTED_EXTENSIONS, extract_text


class ReadDocumentInput(TypedDict):
    file_path: Annotated[str, "Path to the document to read."]


@tool(
    "read_document",
    "Extract the text content of a document (resume, job posting, etc). "
    f"Supported extensions: {', '.join(SUPPORTED_EXTENSIONS)}.",
    ReadDocumentInput,
    annotations=ToolAnnotations(read_only_hint=True),
)
async def read_document(args: ReadDocumentInput) -> dict:
    text = extract_text(args["file_path"])
    return {"content": [{"type": "text", "text": text}]}
