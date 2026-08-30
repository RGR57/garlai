from pathlib import Path

import mimetypes

from src.models.document import Document
from docx import Document as DocxDocument
from src.utils.logger import logger
from pypdf import PdfReader

class DocumentLoader:

    SUPPORTED_EXTENSIONS = {
        ".txt",
        ".md",
        ".py",
        ".json",
        ".csv",
        ".html",
        ".css",
        ".js",
        ".ts",
        ".java",
        ".cpp",
        ".c",
        ".h",
        ".hpp",
        ".xml",
        ".yaml",
        ".yml",
        ".sql",
        ".pdf",
        ".docx",
    }

    def load(
        self,
        path: str,
    ) -> Document:

        path = str(
            Path(path).resolve()
        )

        extension = (
            Path(path)
            .suffix
            .lower()
        )

        if (
            extension
            not in self.SUPPORTED_EXTENSIONS
        ):
            raise ValueError(
                f"Unsupported document type: "
                f"{extension}"
            )

        logger.info(
            f"Loading document: {path}"
        )

        if extension == ".pdf":
            content = self._load_pdf(
                path
            )

        elif extension == ".docx":
            content = self._load_docx(
                path
            )

        else:
            content = self._load_text(
                path
            )

        mime_type = (
            mimetypes.guess_type(
                path
            )[0]
            or "text/plain"
        )

        return Document.from_file(
            path=path,
            content=content,
            mime_type=mime_type,
        )
    def _load_text(
        self,
        path: str,
    ) -> str:

        with open(
            path,
            "r",
            encoding="utf-8",
            errors="ignore",
        ) as file:

            return file.read()

    def _load_pdf(
        self,
        path: str,
    ) -> str:



        reader = PdfReader(path)

        pages: list[str] = []

        for page in reader.pages:

            text = (
                page.extract_text()
                or ""
            )

            pages.append(text)

        return "\n".join(
            pages
        )

    def _load_docx(
        self,
        path: str,
    ) -> str:



        document = DocxDocument(
            path
        )

        paragraphs: list[str] = []

        for paragraph in document.paragraphs:

            if paragraph.text.strip():

                paragraphs.append(
                    paragraph.text
                )

        return "\n".join(
            paragraphs
        )
    def load_directory(
        self,
        directory: str,
        recursive: bool = True,
    ) -> list[Document]:

        root = Path(
            directory
        )

        if not root.exists():

            raise FileNotFoundError(
                directory
            )

        documents: list[
            Document
        ] = []

        iterator = (
            root.rglob("*")
            if recursive
            else root.glob("*")
        )

        for file in iterator:

            if not file.is_file():
                continue

            if (
                file.suffix.lower()
                not in self.SUPPORTED_EXTENSIONS
            ):
                continue

            try:

                documents.append(
                    self.load(
                        str(file)
                    )
                )

            except Exception as exc:

                logger.warning(
                    f"Failed to load "
                    f"{file}: {exc}"
                )

        logger.info(
            f"Loaded "
            f"{len(documents)} "
            f"documents."
        )

        return documents
    def supports(
        self,
        path: str,
    ) -> bool:

        return (
            Path(path)
            .suffix
            .lower()
            in self.SUPPORTED_EXTENSIONS
        )

    def supported_extensions(
        self,
    ) -> list[str]:

        return sorted(
            self.SUPPORTED_EXTENSIONS
        )

    def count_documents(
        self,
        directory: str,
    ) -> int:

        root = Path(
            directory
        )

        if not root.exists():
            return 0

        count = 0

        for file in root.rglob("*"):

            if (
                file.is_file()
                and file.suffix.lower()
                in self.SUPPORTED_EXTENSIONS
            ):
                count += 1

        return count
    def load_many(
        self,
        paths: list[str],
    ) -> list[Document]:

        documents: list[
            Document
        ] = []

        for path in paths:

            try:

                documents.append(
                    self.load(path)
                )

            except Exception as exc:

                logger.warning(
                    f"Skipping {path}: {exc}"
                )

        return documents

    def __call__(
        self,
        path: str,
    ) -> Document:

        return self.load(
            path
        )
