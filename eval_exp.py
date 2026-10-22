
import argparse

import os

project_root_path = os.path.dirname(os.path.abspath(__file__))


def default_method_list(llm_name=None, *, lang="zh"):
    from chinatravel.agent.load_model import build_method_name, resolve_llm_name

    resolved_llm_name = resolve_llm_name(llm_name)
    if not resolved_llm_name:
        raise ValueError(
            "--method all requires --llm <model> or CHINATRAVEL_OPENAI_MODEL/OPENAI_MODEL."
        )

    return [
        build_method_name("RuleNeSy", "rule", lang=lang),
        build_method_name("LLMNeSy", resolved_llm_name, lang=lang),
        build_method_name("Act", resolved_llm_name, lang=lang),
        build_method_name("ReAct", resolved_llm_name, lang=lang),
        build_method_name("ReAct0", resolved_llm_name, lang=lang),
        build_method_name(
            "LLM-modulo",
            resolved_llm_name,
            lang=lang,
            refine_steps=10,
            oracle_translation=True,
        ),
        build_method_name("TPCAgent", resolved_llm_name, lang=lang),
    ]

def load_result(args, query_index, verbose=False):
    def load_result_for_method(method):
        plans = {}
        for query_id in query_index:
            result_file = os.path.join(
                "results/", method, "{}.json".format(query_id)
            )

            try:
                if os.path.exists(result_file):
                    from chinatravel.evaluation.utils import load_json_file

                    result = load_json_file(result_file)
                    plans[query_id] = result
                else:
                    plans[query_id] = {}
            except:
                plans[query_id] = {}
        return plans

    result = {}
    if args.method == "all":
        method_list = default_method_list(
            getattr(args, "llm", None),
            lang=getattr(args, "lang", "zh"),
        )
    else:
        method_list = [args.method]

    for method in method_list:
        result[method] = load_result_for_method(method)

    if verbose:
        print(result)

    return method_list, result

def evaluate_final_plans(query_data, plans, output_dir, *, lang="zh", preference=False):
    """Score an exact query population without loading queries or making model calls.

    Rates retain the benchmark's percentage scale and definitions.
    """
    import json
    from pathlib import Path
    from chinatravel.evaluation.commonsense_constraint import evaluate_commonsense_constraints
    from chinatravel.evaluation.hard_constraint import evaluate_hard_constraints_v2
    from chinatravel.evaluation.schema_constraint import evaluate_schema_constraints
    from chinatravel.evaluation.preference import evaluate_preference_v2

    ids = list(query_data)
    if not ids or set(plans) != set(ids):
        raise ValueError("Benchmark requires a nonempty, exactly aligned query/plan population")
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    schema = json.loads((Path(__file__).resolve().parent / "chinatravel/evaluation/output_schema.json").read_text())
    schema_rate, schema_rows, schema_pass = evaluate_schema_constraints(ids, plans, schema)
    comm_macro, comm_micro, comm_rows, comm_pass = evaluate_commonsense_constraints(ids, query_data, plans, lang=lang)
    log_macro, log_micro, conditional_macro, conditional_micro, log_rows, log_pass = evaluate_hard_constraints_v2(
        ids, query_data, plans, env_pass_id=comm_pass, lang=lang)
    schema_rows.to_csv(output / "schema.csv", index=False)
    comm_rows.to_csv(output / "commonsense.csv", index=False)
    log_rows.to_csv(output / "logical_py.csv", index=False)
    summary = dict(schema_pass_rate=schema_rate, commonsense_micro=comm_micro,
                   commonsense_macro=comm_macro, logical_micro=log_micro, logical_macro=log_macro,
                   conditional_logical_micro=conditional_micro, conditional_logical_macro=conditional_macro,
                   conditional_lpr=conditional_micro,
                   all_pass_ratio=len(set(schema_pass) & set(comm_pass) & set(log_pass)) / len(ids) * 100,
                   query_count=len(ids), query_uids=ids, language=lang, rate_scale="percent")
    if preference:
        evaluate_preference_v2(ids, query_data, plans, list(set(comm_pass) & set(log_pass)), lang=lang).to_csv(
            output / "preference.csv", index=False)
    (output / "benchmark_summary.json").write_text(json.dumps(summary, indent=2, allow_nan=False) + "\n")
    return summary


if __name__ == "__main__":

    parser = argparse.ArgumentParser()
    parser.add_argument("--splits", "-s", type=str, default="example")
    parser.add_argument(
        "--method", "-m", type=str, default="example"
    )
    parser.add_argument(
        "--llm",
        "-l",
        type=str,
        default=None,
        help="Model name used to derive default result directories when --method all.",
    )
    parser.add_argument("--preference", "-p", action="store_true", default=False)
    parser.add_argument("--lang", "--locale", choices=["zh", "en"], default="en")
    args = parser.parse_args()
    if args.method == "all":
        from chinatravel.agent.load_model import resolve_llm_name

        if not resolve_llm_name(args.llm):
            parser.error(
                "--method all requires --llm <model> or CHINATRAVEL_OPENAI_MODEL/OPENAI_MODEL."
            )
    if args.method != "all":
        from chinatravel.agent.load_model import ensure_method_language

        args.method = ensure_method_language(args.method, args.lang)

    # print(args.splits)

    from chinatravel.data.load_datasets import load_query
    args.oracle_translation = True  # Evaluation requires the reference constraints.
    query_index, query_data = load_query(args)
    method_list, result_data = load_result(args, query_index)

    # print(result_data)



    for method in method_list:
        summary = evaluate_final_plans(query_data, result_data[method],
                                       os.path.join("eval_res", "splits_" + args.splits, method),
                                       lang=args.lang, preference=args.preference)
        print("Method:", method)
        for field, value in summary.items():
            print(field + ":", value)
