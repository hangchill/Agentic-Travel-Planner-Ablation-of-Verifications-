"""Guard the committed subset splits used by `--splits subset_train` / `subset_test`.

Difficulty comes from the official ChinaTravel split files (easy/medium/human.txt),
never from the UID prefix: upstream's easy split is mostly `m...`/`t...` UIDs and
its medium split is all `e...` UIDs.
"""
import json
import unittest
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "chinatravel" / "evaluation"
SPLITS = ROOT / "default_splits"
EXPECTED = {
    "subset_train": {"easy": 20, "medium": 20, "human": 20},
    "subset_test": {"easy": 10, "medium": 10, "human": 10},
}


def read_uids(name):
    return [line.strip() for line in (SPLITS / f"{name}.txt").read_text(encoding="utf-8").splitlines() if line.strip()]


class SubsetSplitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.official = {name: set(read_uids(name)) for name in ("easy", "medium", "human")}
        cls.origin_file = json.loads((ROOT / "splits" / "subset_origin.json").read_text(encoding="utf-8"))
        cls.origin = cls.origin_file["origin"]

    def difficulty(self, uid):
        hits = [name for name, uids in self.official.items() if uid in uids]
        self.assertEqual(len(hits), 1, f"{uid} must be in exactly one official split, found {hits}")
        return hits[0]

    def test_splits_are_balanced_by_official_difficulty(self):
        for split, expected in EXPECTED.items():
            uids = read_uids(split)
            self.assertEqual(len(uids), len(set(uids)), f"{split} has duplicate UIDs")
            self.assertEqual(dict(Counter(self.difficulty(u) for u in uids)), expected, split)

    def test_train_and_test_are_disjoint_and_pilot5_is_in_train(self):
        train, test = set(read_uids("subset_train")), set(read_uids("subset_test"))
        self.assertFalse(train & test)
        self.assertLessEqual(set(read_uids("pilot5")), train)

    def test_origin_map_matches_splits_and_official_difficulty(self):
        uids = read_uids("subset_train") + read_uids("subset_test")
        self.assertEqual(set(self.origin), set(uids))
        for uid in uids:
            self.assertEqual(self.origin[uid], self.difficulty(uid), uid)
        self.assertEqual(self.origin_file["split_sizes"], EXPECTED)


if __name__ == "__main__":
    unittest.main()
