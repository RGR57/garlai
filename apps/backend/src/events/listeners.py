from src.events.event import Event


class LoggingListener:

    async def handle(
        self,
        event: Event,
    ):

        print(
            f"{event.name}: {event.payload}"
        )