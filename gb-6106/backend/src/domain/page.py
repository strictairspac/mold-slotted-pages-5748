"""Byte-packed heap page with a forward directory and backward record arena."""
from dataclasses import dataclass, replace


HEADER_BYTES = 16
SLOT_BYTES = 8


@dataclass(frozen=True)
class Slot:
    offset: int
    length: int
    key: str


class SlottedPage:
    def __init__(self, size):
        self.data = bytearray(size)
        self.size = size
        self.slots: list[Slot | None] = []
        self.tail = size

    @property
    def contiguous(self):
        return self.tail - HEADER_BYTES - SLOT_BYTES * len(self.slots)

    @property
    def free(self):
        return self.size - HEADER_BYTES - SLOT_BYTES * len(self.slots) - sum(
            item.length for item in self.slots if item is not None
        )

    @property
    def fragmented(self):
        return self.free - self.contiguous

    def find(self, key):
        return next(
            (index for index, item in enumerate(self.slots) if item and item.key == key),
            None,
        )

    def read(self, slot_id):
        item = self.slots[slot_id]
        return bytes(self.data[item.offset:item.offset + item.length])

    def compact(self):
        snapshot = [(index, item, self.read(index)) for index, item in enumerate(self.slots) if item]
        self.data = bytearray(self.size)
        self.tail = self.size
        for index, item, data in snapshot:
            self.tail -= item.length
            self.data[self.tail:self.tail + item.length] = data
            self.slots[index] = replace(item, offset=self.tail)

    def _write(self, slot_id, key, data):
        self.tail -= len(data)
        self.data[self.tail:self.tail + len(data)] = data
        self.slots[slot_id] = Slot(self.tail, len(data), key)

    def insert(self, key, data):
        if self.find(key) is not None:
            raise ValueError("记录号已占用")
        if self.free < SLOT_BYTES + len(data):
            raise ValueError("页面剩余空间不足")
        compacted = self.contiguous < SLOT_BYTES + len(data)
        if compacted:
            self.compact()
        slot_id = len(self.slots)
        self.slots.append(None)
        self._write(slot_id, key, data)
        return slot_id, compacted

    def delete(self, key):
        index = self.find(key)
        if index is None:
            raise ValueError("记录号不存在")
        self.slots[index] = None
        return index

    def update(self, key, data):
        index = self.find(key)
        if index is None:
            raise ValueError("记录号不存在")
        old = self.slots[index]
        if len(data) <= old.length:
            self.data[old.offset:old.offset + len(data)] = data
            self.slots[index] = replace(old, length=len(data))
            return index, False
        if self.free + old.length < len(data):
            raise ValueError("页面剩余空间不足")
        self.slots[index] = None
        compacted = self.contiguous < len(data)
        if compacted:
            self.compact()
        self._write(index, key, data)
        return index, compacted
