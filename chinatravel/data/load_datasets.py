import os
import json
## added
import ast

project_root_path = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)

from chinatravel.environment.language import normalize_lang, CITY_NAMES


class NpEncoder(json.JSONEncoder):
    def default(self, obj):
        try:
            import numpy as np
        except ImportError:
            np = None
        if np is None:
            return super(NpEncoder, self).default(obj)
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.floating):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        return super(NpEncoder, self).default(obj)


DEFAULT_HUGGINGFACE_SPLITS = {
    "easy",
    "medium",
    "human",
    "preference_base50",
    "preference0_base50",
    "preference1_base50",
    "preference2_base50",
    "preference3_base50",
    "preference4_base50",
    "preference5_base50",
}
PREFERENCE_HUGGINGFACE_SPLITS = {
    "preference0_base50",
    "preference1_base50",
    "preference2_base50",
    "preference3_base50",
    "preference4_base50",
    "preference5_base50",
}
ORACLE_FIELDS = {"hard_logic", "hard_logic_py", "hard_logic_nl"}


def _strip_oracle_fields(data_i):
    for key in ORACLE_FIELDS:
        data_i.pop(key, None)
    return data_i

## changed
def _validate_query_record(data_i):

    ## Convert string-encoded constraint lists from the original Hugging Face dataset into actual Python lists.
    ## This fixes a data-format mismatch without changing the constraints.
    if isinstance(data_i.get("hard_logic_py"), str):
        try:
            data_i["hard_logic_py"] = ast.literal_eval(
                data_i["hard_logic_py"]
            )
        except (ValueError, SyntaxError) as e:
            raise ValueError(
                f"Cannot parse hard_logic_py for {data_i.get('uid')}"
            ) from e

    ## Ensure the resulting constraints have the expected structure.
    if "hard_logic_py" in data_i:
        if not isinstance(data_i["hard_logic_py"], list):
            raise ValueError(
                f"Expected hard_logic_py to be a list for {data_i.get('uid')}"
            )

        if not all(isinstance(x, str) for x in data_i["hard_logic_py"]):
            raise ValueError(
                f"Expected all hard_logic_py entries to be strings "
                f"for {data_i.get('uid')}"
            )

    return data_i


def _load_huggingface_split(split):
    from datasets import load_dataset as hg_load_dataset

    config_name = "preference" if split in PREFERENCE_HUGGINGFACE_SPLITS else "default"
    return hg_load_dataset("LAMDA-NeSy/ChinaTravel", name=config_name)[split].to_list()


## Map Chinese city names to their canonical English equivalents using the
## authoritative CITY_NAMES table from environment/language.py.
_ZH_TO_EN_CITY = dict(zip(CITY_NAMES["zh"], CITY_NAMES["en"]))


def _adapt_record_to_english(data_i):
    """Turn a Hugging Face query record into its English form in place.

    The HF query files are bilingual: they carry both ``nature_language`` (zh)
    and ``nature_language_en`` (en), with Chinese city names. For an English run
    the agent reads ``nature_language`` and looks up cities against the English
    sandbox (database_en), so we promote the English query text and translate
    the city fields using the canonical CITY_NAMES mapping. Constraints
    (``hard_logic_py``) are language-neutral DSL and are left unchanged.
    """
    english_query = data_i.get("nature_language_en")
    if not english_query:
        raise ValueError(
            f"Query {data_i.get('uid')!r} has no 'nature_language_en'; cannot "
            f"run in English. Use --lang zh for this split, or supply English "
            f"query text."
        )
    data_i["nature_language"] = english_query

    for field in ("start_city", "target_city"):
        city = data_i.get(field)
        if city in _ZH_TO_EN_CITY:
            data_i[field] = _ZH_TO_EN_CITY[city]
        elif city in CITY_NAMES["en"]:
            pass  # already English
        elif city is not None:
            raise ValueError(
                f"Query {data_i.get('uid')!r} has unrecognized {field}={city!r}; "
                f"cannot map to an English city name."
            )
    return data_i


def _resolve_local_query_paths(data_dir, split, query_ids, lang):
    preferred_names = [split]
    if lang == "en" and not split.endswith("_EN"):
        preferred_names.append(f"{split}_EN")
    preferred_dirs = [
        os.path.join(data_dir, name)
        for name in preferred_names
        if os.path.isdir(os.path.join(data_dir, name))
    ]
    for split_dir in preferred_dirs:
        paths = {
            query_id: os.path.join(split_dir, f"{query_id}.json")
            for query_id in query_ids
        }
        if all(os.path.isfile(path) for path in paths.values()):
            return paths
    if preferred_dirs:
        missing = {
            split_dir: [
                query_id
                for query_id in query_ids
                if not os.path.isfile(
                    os.path.join(split_dir, f"{query_id}.json")
                )
            ]
            for split_dir in preferred_dirs
        }
        raise ValueError(
            f"Split directory does not contain every configured UID: {missing}"
        )

    indexed_paths = {query_id: [] for query_id in query_ids}
    for directory_name in sorted(os.listdir(data_dir)):
        directory = os.path.join(data_dir, directory_name)
        if not os.path.isdir(directory):
            continue
        for query_id in query_ids:
            path = os.path.join(directory, f"{query_id}.json")
            if os.path.isfile(path):
                indexed_paths[query_id].append(path)

    missing = [
        query_id for query_id, paths in indexed_paths.items() if not paths
    ]
    ambiguous = {
        query_id: paths
        for query_id, paths in indexed_paths.items()
        if len(paths) > 1
    }
    if missing or ambiguous:
        raise ValueError(
            "Unable to resolve local split {!r}: missing={}, ambiguous={}".format(
                split,
                missing,
                ambiguous,
            )
        )
    return {
        query_id: paths[0] for query_id, paths in indexed_paths.items()
    }


def load_query_local(args, version="", verbose=False):
    query_data = {}
    lang = normalize_lang(getattr(args, "lang", None))

    # split_config_file = 'default_splits/{}.txt'.format(args.splits)

    split_config_file = os.path.join(
        project_root_path,
        "chinatravel",
        "evaluation",
        "default_splits",
        "{}.txt".format(args.splits),
    )

    print("config file for testing split: {}".format(split_config_file))

    query_id_list = []
    with open(split_config_file, "r") as f:
        for line in f.readlines():
            line = line.strip()
            query_id_list.append(line)

    if verbose:
        print(query_id_list)

    data_dir = os.path.join(project_root_path, "chinatravel", "data")
    if lang == "en":
        data_dir = os.path.join(data_dir, "en")

    query_paths = _resolve_local_query_paths(
        data_dir,
        args.splits,
        query_id_list,
        lang,
    )
    for query_id in query_id_list:
        with open(query_paths[query_id], encoding="utf-8") as query_file:
            data_i = _validate_query_record(json.load(query_file))
        if data_i.get("uid") != query_id:
            raise ValueError(
                f"Query UID mismatch for {query_paths[query_id]}: "
                f"expected {query_id!r}, got {data_i.get('uid')!r}"
            )
        if hasattr(args, 'oracle_translation') and not args.oracle_translation:
            _strip_oracle_fields(data_i)
        query_data[query_id] = data_i

    # print(query_data)

    if verbose:
        for query_id in query_id_list:
            print(query_id, query_data[query_id])

    return query_id_list, query_data


def load_json_file(file_path):
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json_file(json_data, file_path):
    with open(file_path, "w", encoding="utf8") as dump_f:
        json.dump(json_data, dump_f, ensure_ascii=False, indent=4, cls=NpEncoder)



def _read_split_uids(split):
    """Read the ordered UID list for a named split from default_splits/<split>.txt."""
    path = os.path.join(
        project_root_path, "chinatravel", "evaluation",
        "default_splits", f"{split}.txt",
    )
    with open(path, "r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]


def _hf_base_split(split):
    """Resolve the base Hugging Face split for a (possibly suffixed) split name.

    A train/test subset is named ``<base>_train`` / ``<base>_test`` where
    ``<base>`` is a known HF split. It loads the base HF queries and then keeps
    only the UIDs listed in ``default_splits/<split>.txt``. Returns the base
    split name plus the UID filter (or None for no filtering).
    """
    if split in DEFAULT_HUGGINGFACE_SPLITS:
        return split, None
    for suffix in ("_train", "_test"):
        if split.endswith(suffix):
            base = split[: -len(suffix)]
            if base in DEFAULT_HUGGINGFACE_SPLITS:
                return base, set(_read_split_uids(split))
    return None, None


## Combined (stratified, multi-category) splits: a single train/test list whose
## UIDs come from several base HF splits (easy/medium/human). The UID->origin map
## is recorded in evaluation/splits/combined_origin.json so each query is fetched
## from the correct base split.
COMBINED_SPLITS = {"combined_train", "combined_test"}


def _combined_origin_map():
    path = os.path.join(
        project_root_path, "chinatravel", "evaluation",
        "splits", "combined_origin.json",
    )
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)["origin"]


def _load_combined_split(args, split):
    """Load a stratified combined split by fetching each UID from its base HF split."""
    lang = normalize_lang(getattr(args, "lang", None))
    wanted = set(_read_split_uids(split))
    origin = _combined_origin_map()

    ## Group the wanted UIDs by which base HF split they came from.
    by_base = {}
    for uid in wanted:
        base = origin.get(uid)
        if base is None:
            raise ValueError(f"UID {uid!r} missing from combined_origin.json")
        by_base.setdefault(base, set()).add(uid)

    query_id_list, data_dict = [], {}
    for base, uids in by_base.items():
        for data_i in _load_huggingface_split(base):
            if data_i.get("uid") not in uids:
                continue
            if lang == "en":
                data_i = _adapt_record_to_english(data_i)
            data_i = _validate_query_record(data_i)
            if not getattr(args, "oracle_translation", False):
                _strip_oracle_fields(data_i)
            data_dict[data_i["uid"]] = data_i
    query_id_list = sorted(data_dict)
    missing = wanted - set(query_id_list)
    if missing:
        raise ValueError(f"Combined split {split!r} missing queries: {sorted(missing)}")
    return query_id_list, data_dict


def load_query(args):
    lang = normalize_lang(getattr(args, "lang", None))

    ## Stratified combined splits draw from several base HF splits at once.
    if args.splits in COMBINED_SPLITS:
        return _load_combined_split(args, args.splits)

    base_split, uid_filter = _hf_base_split(args.splits)

    ## Local query files take priority when they exist (e.g. a locally generated
    ## split). Fall back to the bilingual Hugging Face dataset otherwise.
    if base_split is None:
        return load_query_local(args)

    ## The HF query files are bilingual. For both languages we load the same
    ## records; for English we promote nature_language_en and translate cities.
    ## A train/test subset reuses the base HF split and filters by UID, so no
    ## local query files are required.
    raw_records = _load_huggingface_split(base_split)

    query_id_list = []
    data_dict = {}
    for data_i in raw_records:
        if uid_filter is not None and data_i.get("uid") not in uid_filter:
            continue
        if lang == "en":
            data_i = _adapt_record_to_english(data_i)
        data_i = _validate_query_record(data_i)

        if not getattr(args, "oracle_translation", False):
            _strip_oracle_fields(data_i)

        query_id_list.append(data_i["uid"])
        data_dict[data_i["uid"]] = data_i

    return query_id_list, data_dict


if __name__ == "__main__":
    import argparse

    argparser = argparse.ArgumentParser()
    argparser.add_argument("--splits", type=str, default="easy")
    argparser.add_argument("--lang", type=str, choices=["zh", "en"], default="en")

    # from datasets import load_dataset as hg_load_dataset

    # # Login using e.g. `huggingface-cli login` to access this dataset
    # ds = hg_load_dataset("LAMDA-NeSy/ChinaTravel")
    # print(ds)
    # print(ds["easy"].to_list())

    # exit(0)
    args = argparser.parse_args()
    query_id_list, query_data = load_query(args)
    # print(query_id_list)
    # print(query_data)

    for uid in query_id_list:
        if uid in query_data:
            print(uid, query_data[uid])
        else:
            raise ValueError(f"{uid} not in query_data")
