from abc import ABC, abstractmethod

class BaseExtractor(ABC):
    @abstractmethod
    async def process(self, text: str) -> dict:
        """Ogni estrattore deve restituire un dizionario nel formato {'locations': [...]}"""
        pass