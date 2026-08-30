import logging


logger = logging.getLogger(
    "GARL"
)

logger.setLevel(
    logging.INFO
)

# Let the centralized root configuration
# handle output.
logger.propagate = True