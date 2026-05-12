"""Pre‑built index for fast name→UID resolution."""
from typing import Dict, List, Optional, Set
from .models import Entity

class NameIndex:
    def __init__(self, entities: List[Entity]):
        self.by_name: Dict[str, str] = {}          # normalised full name → uid
        self.by_token: Dict[str, List[str]] = {}    # token → list of uids
        for e in entities:
            key = e.name.strip().lower()
            self.by_name[key] = e.uid
            for token in key.split():
                self.by_token.setdefault(token, []).append(e.uid)

    def resolve(self, name: str, valid_uids: Set[str]) -> Optional[str]:
        """Resolve a name/UID against a set of valid node IDs."""
        if not name or not isinstance(name, str):
            return None
        name = name.strip()
        # 1. direct UID match
        if name in valid_uids:
            return name
        # 2. normalised full name
        low = name.lower()
        if low in self.by_name:
            uid = self.by_name[low]
            if uid in valid_uids:
                return uid
        # 3. token‑based fuzzy match (only if exactly one candidate)
        candidates = set()
        for token in low.split():
            candidates.update(self.by_token.get(token, []))
        valid_candidates = [u for u in candidates if u in valid_uids]
        if len(valid_candidates) == 1:
            return valid_candidates[0]
        return None
