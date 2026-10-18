
import json
import time
from collections import Counter
from chinatravel.evaluation.repair_attempt import failed_constraint_indices

from chinatravel.json_utils import repair_json
from chinatravel.agent.nesy_verifier.prompts.llm_modulo import BACK_PROMPT
from chinatravel.agent.nesy_verifier.repair_strategies.base import (
    BaseRepairStrategy,
    RepairResult,
)


## R0: Regenerate the entire itinerary using verifier feedback.
class R0WholePlanRepair(BaseRepairStrategy):

    def repair(
        self,
        problem,
        raw_plan,
        verification_results,
        context,
        llm,
    ) -> RepairResult:

        failed_indices = failed_constraint_indices(verification_results["personal_constraints"])
        commonsense_errors = verification_results.get("commonsense_errors")
        feedback = verification_results["error_info"]
        # Shared verifier emits commonsense_errors verbatim in error_info. Count
        # actual supplied occurrences, preserving duplicates without guessing.
        feedback_commonsense_count = (sum((Counter(commonsense_errors) & Counter(feedback)).values())
                                      if isinstance(commonsense_errors, list) else None)

        ## Combine commonsense and personal constraint feedback.
        error_info_nl = "\n".join(
            verification_results["error_info"]
        )

        ## Construct the original ChinaTravel BACK_PROMPT.
        query_message = BACK_PROMPT.format(
            go_train_info=context["go_train_info"],
            go_flight_info=context["go_flight_info"],
            back_train_info=context["back_train_info"],
            back_flight_info=context["back_flight_info"],
            attraction_info=context["attraction_info"],
            restaurant_info=context["restaurant_info"],
            accommodation_info=context["accommodation_info"],
            innercity_transport_info=context["innercity_transport_info"],
            query=problem["nature_language"],
            ## Use the current raw itinerary rather than a separately stored response.
            plan=json.dumps(raw_plan, ensure_ascii=False),
            backprompt=error_info_nl,
        )

        ## Ask the LLM to regenerate the complete itinerary.
        start_time = time.time()

        response = llm(
            [{"role": "user", "content": query_message}],
            one_line=False,
        )

        inference_time = time.time() - start_time

        ## Preserve ChinaTravel's original response formatting.
        response = """[{"day": 1,""" + response
        nl_plan = repair_json(response)
        repaired_plan = json.loads(nl_plan)

        ## Return the raw revised itinerary and execution metadata.
        return RepairResult(
            repaired_plan=repaired_plan,
            metadata={
                "strategy": "R0",
                "target_constraint_indices": failed_indices,
                "target_provenance": "r0_failed_feedback",
                "editable_scope": "plan",
                "feedback_personal_constraint_indices": failed_indices.copy(),
                "feedback_commonsense_failure_count": feedback_commonsense_count,
                "prompt": query_message,
                "raw_response": response,
                "llm_inference_time": inference_time,
            },
        )
