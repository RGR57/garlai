import logging
import sys


def setup_logging() -> None:

    root_logger = logging.getLogger()

    root_logger.setLevel(
        logging.INFO
    )

    # Remove existing root handlers so Uvicorn/reloads
    # don't leave GARL with conflicting handlers.
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(
            handler
        )

    console_handler = logging.StreamHandler(
        sys.stdout
    )

    console_handler.setLevel(
        logging.INFO
    )

    console_handler.setFormatter(
        logging.Formatter(
            "%(asctime)s | "
            "%(levelname)s | "
            "%(name)s | "
            "%(message)s"
        )
    )

    root_logger.addHandler(
        console_handler
    )

    # Keep Uvicorn access logging enabled.
    logging.getLogger(
        "uvicorn.access"
    ).setLevel(
        logging.INFO
    )

    logging.getLogger(
        "uvicorn.error"
    ).setLevel(
        logging.INFO
    )