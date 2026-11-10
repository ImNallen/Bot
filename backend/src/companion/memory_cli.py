"""See and edit what the companion remembers.

  companion-memory              list everything
  companion-memory forget 3     forget memory 3
  companion-memory clear        forget everything
"""

import sys

from companion.config import Settings
from companion.memory import MemoryStore


def main() -> None:
    store = MemoryStore(Settings.from_env().memory_path)
    match sys.argv[1:]:
        case []:
            memories = store.all()
            for m in memories:
                print(f"{m.id:>4}  {m.kind:<5}  {m.text}{'  · ' + str(m.on) if m.on else ''}")
            print(f"{len(memories)} memories, stored only on this Mac.")
        case ["forget", memory_id] if memory_id.isdigit():
            print("Forgotten." if store.forget(int(memory_id)) else f"No memory {memory_id}.")
        case ["clear"]:
            if input("Forget everything? Type yes: ").strip().lower() == "yes":
                store.clear()
                print("Everything forgotten.")
        case _:
            print(__doc__)
            sys.exit(2)
