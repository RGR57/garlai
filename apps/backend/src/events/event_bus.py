from collections import defaultdict
from typing import Callable

from src.events.event import Event


class EventBus:

    def __init__(self):

        self.listeners = defaultdict(list)

    def subscribe(
        self,
        event_name: str,
        callback: Callable,
    ):

        self.listeners[event_name].append(callback)

    async def publish(
        self,
        event: Event,
    ):

        for callback in self.listeners[event.name]:

            await callback(event)